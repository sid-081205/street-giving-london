"""
Fetch + cache every *mapped* (real-data) layer used by the model.

Each function caches its tidy output under ``data/processed`` so the pipeline is
fast and reproducible offline after the first run.  Raw downloads land in
``data/raw`` with their provenance.

Layers
------
- MSOA 2021 boundaries (ONS Open Geography Portal)          -> geography
- TfL station footfall, 2024 daily by day-of-week           -> flow level
- TfL RODS 2017 quarter-hourly entries/exits                -> flow hourly shape
- TfL StopPoint coordinates                                 -> station -> MSOA
- BRES 2024 employment by MSOA x SIC section (nomis)        -> sector anchors + income
- MHCLG rough-sleeping snapshot by borough                  -> validation
"""
from __future__ import annotations

import io
import os
import re
import zipfile

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

import config as C

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}


def _get(url, **kw):
    kw.setdefault("headers", HEADERS)
    kw.setdefault("timeout", 120)
    r = requests.get(url, **kw)
    r.raise_for_status()
    return r


def norm_station(name: str) -> str:
    """Normalise a station name so the three TfL sources can be joined."""
    s = str(name).lower()
    s = re.sub(r"\((?:h&c|h and c|inner|outer|platforms?[^)]*)\)", " ", s)
    s = re.sub(r"\b(underground|overground|dlr|national rail|rail|tube|"
               r"elizabeth line|tram|ell)\b", " ", s)
    s = re.sub(r"\bstations?\b", " ", s)
    s = re.sub(r"\(.*?\)", " ", s)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


# --------------------------------------------------------------------------
# 1. Geography
# --------------------------------------------------------------------------
def fetch_boundaries() -> gpd.GeoDataFrame:
    """Central-London small-area boundaries at the configured granularity.

    The area code/name are stored generically as ``msoa`` / ``msoa_name`` so the
    rest of the pipeline is granularity-agnostic (the value may be an LSOA).
    """
    g = C.GEO[C.GRANULARITY]
    cache = os.path.join(C.PROCESSED, f"areas_{C.GRANULARITY.lower()}.gpkg")
    if os.path.exists(cache):
        return gpd.read_file(cache)

    where = " OR ".join(f"{g['name']} LIKE '{b} %'" for b in C.CENTRAL_BOROUGHS)
    print(f"  - downloading {C.GRANULARITY} 2021 boundaries from ONS ...")
    # ArcGIS caps each response at maxRecordCount (2000) -> page with resultOffset.
    page, frames, offset = 2000, [], 0
    while True:
        params = {"where": where, "outFields": f"{g['code']},{g['name']}",
                  "outSR": "4326", "f": "geojson",
                  "resultRecordCount": page, "resultOffset": offset}
        part = gpd.read_file(io.StringIO(_get(g["service"], params=params).text))
        if len(part) == 0:
            break
        frames.append(part)
        if len(part) < page:
            break
        offset += page
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    gdf["borough"] = gdf[g["name"]].str.replace(g["strip"], "", regex=True)
    gdf = gdf[gdf["borough"].isin(C.CENTRAL_BOROUGHS)].copy()
    gdf = gdf.rename(columns={g["code"]: "msoa", g["name"]: "msoa_name"})
    gdf = gdf[["msoa", "msoa_name", "borough", "geometry"]].set_crs(C.CRS_WGS84)
    gdf.to_file(cache, driver="GPKG")
    print(f"    {len(gdf)} {C.GRANULARITY}s across {gdf.borough.nunique()} boroughs")
    return gdf


# Back-compat alias.
fetch_msoa_boundaries = fetch_boundaries


# --------------------------------------------------------------------------
# 2. TfL footfall level (2024) + 3. RODS hourly shape + station coordinates
# --------------------------------------------------------------------------
def fetch_station_footfall() -> pd.DataFrame:
    cache = os.path.join(C.PROCESSED, "station_footfall.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache)
    print("  - downloading TfL StationFootfall_2024 ...")
    r = _get(C.TFL_FOOTFALL_CSV)
    df = pd.read_csv(io.StringIO(r.text))
    df["taps"] = df["EntryTapCount"].fillna(0) + df["ExitTapCount"].fillna(0)
    df["is_weekend"] = df["DayOfWeek"].isin(["Saturday", "Sunday"])
    # Mean daily taps for a typical weekday and weekend day, per station.
    g = (df.groupby(["Station", "is_weekend"])["taps"].mean()
           .unstack("is_weekend").rename(columns={False: "weekday", True: "weekend"}))
    g = g.reset_index().rename(columns={"Station": "station"})
    g["norm"] = g["station"].map(norm_station)
    g.to_csv(cache, index=False)
    print(f"    {len(g)} stations")
    return g


def fetch_rods_profiles() -> pd.DataFrame:
    """Per-station 24-hour entry+exit profile (shares summing to 1)."""
    cache = os.path.join(C.PROCESSED, "rods_profiles.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache)
    raw = os.path.join(C.RAW, "rods.zip")
    if not os.path.exists(raw):
        print("  - downloading TfL RODS 2017 ...")
        with open(raw, "wb") as f:
            f.write(_get(C.TFL_RODS_ZIP).content)
    with zipfile.ZipFile(raw) as z:
        with z.open(C.TFL_RODS_FLOWS) as fh:
            xls = pd.read_excel(fh, sheet_name="AEI Summary", header=2)
    xls = xls.rename(columns={c: str(c).strip() for c in xls.columns})
    xls = xls[xls["AEI"].isin(["A", "E"])]          # entries + exits hit the street; drop interchange
    qcols = [c for c in xls.columns if re.match(r"^\d{4}-\d{4}$", str(c))]

    def hour_of(col):
        return int(col[:2])

    rows = []
    for stn, sub in xls.groupby("start station"):
        prof = np.zeros(24)
        for c in qcols:
            prof[hour_of(c)] += pd.to_numeric(sub[c], errors="coerce").fillna(0).sum()
        tot = prof.sum()
        if tot <= 0:
            continue
        rows.append({"norm": norm_station(stn), **{f"h{h}": prof[h] / tot for h in range(24)}})
    out = pd.DataFrame(rows).groupby("norm", as_index=False).mean(numeric_only=True)
    out.to_csv(cache, index=False)
    print(f"    {len(out)} RODS station profiles")
    return out


def fetch_station_coords() -> pd.DataFrame:
    cache = os.path.join(C.PROCESSED, "station_coords.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache)
    rows = []
    for mode in C.TFL_STOPPOINT_MODES:
        print(f"  - TfL StopPoint coordinates: {mode}")
        try:
            d = _get(C.TFL_STOPPOINT_API.format(mode=mode), timeout=60).json()
        except Exception as e:                      # noqa: BLE001
            print(f"    (skipped {mode}: {e})")
            continue
        for sp in d.get("stopPoints", []):
            lat, lon = sp.get("lat"), sp.get("lon")
            if lat and lon:
                rows.append({"norm": norm_station(sp.get("commonName", "")),
                             "lat": lat, "lon": lon})
    out = (pd.DataFrame(rows).groupby("norm", as_index=False)[["lat", "lon"]].mean())
    out.to_csv(cache, index=False)
    print(f"    {len(out)} station coordinates")
    return out


# --------------------------------------------------------------------------
# 4. BRES employment by MSOA x SIC section  (sector anchors + worker income)
# --------------------------------------------------------------------------
def fetch_bres_by_section() -> pd.DataFrame:
    cache = os.path.join(C.PROCESSED, f"bres_section_{C.GRANULARITY.lower()}.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache, dtype={"msoa": str})

    print("  - resolving BRES SIC division codes from nomis ...")
    idef = _get(C.NOMIS_BRES + "/industry.def.sdmx.json").json()
    codes = idef["structure"]["codelists"]["codelist"][0]["code"]
    div_to_code = {}
    for c in codes:
        m = re.match(r"^(\d{2}) : ", c["description"]["value"])
        if m:
            div_to_code[int(m.group(1))] = str(c["value"])
    ind_list = ",".join(str(v) for v in div_to_code.values())

    geo = C.GEO[C.GRANULARITY]["bres_type"]
    print(f"  - downloading BRES 2024 employment for {len(div_to_code)} SIC divisions x London {C.GRANULARITY}s ...")
    base = (f"{C.NOMIS_BRES}.data.csv?geography={geo}"
            f"&date=latest&industry={ind_list}&employment_status=4&measure=1"
            f"&measures=20100&select=geography_code,industry_code,obs_value")
    # nomis caps each CSV page at 25k rows -> paginate until exhausted.
    page, frames, offset = 25000, [], 0
    while True:
        chunk = pd.read_csv(io.StringIO(_get(f"{base}&RecordLimit={page}&RecordOffset={offset}").text))
        if chunk.empty:
            break
        frames.append(chunk)
        if len(chunk) < page:
            break
        offset += page
    df = pd.concat(frames, ignore_index=True)
    df.columns = [c.lower() for c in df.columns]
    # nomis returns the SIC-2007 division string directly (e.g. "01", "41").
    df["division"] = pd.to_numeric(df["industry_code"], errors="coerce")
    df = df.dropna(subset=["division"])
    df["section"] = df["division"].astype(int).map(C.SIC_DIVISION_TO_SECTION)
    df["obs_value"] = pd.to_numeric(df["obs_value"], errors="coerce").fillna(0)

    wide = (df.groupby(["geography_code", "section"])["obs_value"].sum()
              .unstack("section").fillna(0).reset_index()
              .rename(columns={"geography_code": "msoa"}))
    wide.to_csv(cache, index=False)
    print(f"    {len(wide)} London MSOAs x {wide.shape[1]-1} sections")
    return wide


# --------------------------------------------------------------------------
# 5. Validation -- borough rough sleeping (MHCLG snapshot; CHAIN-adjacent)
# --------------------------------------------------------------------------
def fetch_validation() -> pd.DataFrame:
    cache = os.path.join(C.PROCESSED, "rough_sleeping_borough.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache)
    print("  - locating MHCLG rough-sleeping snapshot ...")
    page = _get(C.MHCLG_SNAPSHOT_PAGE).text
    m = re.search(r"https://assets\.publishing\.service\.gov\.uk/[^\"' ]+\.ods", page)
    if not m:
        raise RuntimeError("Could not find MHCLG snapshot .ods link")
    ods_url = m.group(0)
    raw = os.path.join(C.RAW, "rough_sleeping_snapshot.ods")
    with open(raw, "wb") as f:
        f.write(_get(ods_url).content)

    # Locate the per-local-authority "Total" table.
    book = pd.read_excel(raw, sheet_name=None, engine="odf", header=None)
    sheet_name = next(
        (n for n in book if "total" in n.lower()
         and book[n].astype(str).apply(lambda c: c.str.contains("Westminster", na=False)).any().any()),
        None,
    )
    if sheet_name is None:
        raise RuntimeError("No LA 'Total' sheet found in MHCLG snapshot")
    sheet = book[sheet_name]
    # Header row = the one naming the LA column, not the title (which also says
    # "local authority").  Anchor on the machine-readable 'organisation_name',
    # falling back to a row that carries several year columns.
    def _is_header(row):
        s = row.astype(str)
        if s.str.fullmatch(r"(?i)organisation_name").any():
            return True
        return s.str.fullmatch(r"20\d{2}(\.0)?").sum() >= 3
    hdr = next(i for i in range(min(15, len(sheet))) if _is_header(sheet.iloc[i]))
    df = pd.read_excel(raw, sheet_name=sheet_name, engine="odf", header=hdr)
    df.columns = [str(c).strip() for c in df.columns]
    la_col = next(c for c in df.columns
                  if "organisation_name" in c.lower() or "local authority" in c.lower())
    # Latest snapshot count = the most recent year column.
    year_cols = [(c, int(re.search(r"(20\d{2})", str(c)).group(1)))
                 for c in df.columns if re.search(r"20\d{2}", str(c))]
    count_col = max(year_cols, key=lambda t: t[1])[0]
    out = df[[la_col, count_col]].rename(columns={la_col: "borough", count_col: "rough_sleepers"})
    out["borough"] = out["borough"].astype(str).str.strip()
    out["rough_sleepers"] = pd.to_numeric(out["rough_sleepers"], errors="coerce")
    out = out.dropna(subset=["rough_sleepers"])
    out = out[out["borough"].isin(C.CENTRAL_BOROUGHS)]
    out.to_csv(cache, index=False)
    print(f"    {len(out)} central boroughs matched (col '{count_col}')")
    return out


if __name__ == "__main__":
    fetch_boundaries()
    fetch_station_footfall()
    fetch_rods_profiles()
    fetch_station_coords()
    fetch_bres_by_section()
    fetch_validation()
