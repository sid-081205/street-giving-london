#!/usr/bin/env python3
"""Fetch the real input datasets used by analysis.ipynb."""
from __future__ import annotations

import json
import os
import sys
import zipfile

import geopandas as gpd
import pandas as pd
import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import config as C  # noqa: E402
import fetch_data as F  # noqa: E402


GEofABRIK_LONDON_SHP = "https://download.geofabrik.de/europe/united-kingdom/england/greater-london-latest-free.shp.zip"

POI_GROUPS = {
    "leisure": {"restaurant", "pub", "bar", "cafe", "fast_food", "nightclub"},
    "shoppers": {"supermarket", "mall", "department_store", "convenience", "market_place", "clothes", "bakery", "butcher", "kiosk"},
    "tourists": {"hotel", "hostel", "guesthouse", "attraction", "museum", "viewpoint", "artwork"},
    "events": {"theatre", "cinema", "nightclub", "stadium", "arts_centre"},
    "students": {"university", "college", "school"},
}


def fetch_osm_pois(areas: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    cache = os.path.join(C.PROCESSED, "osm_pois.geojson")
    if os.path.exists(cache):
        return gpd.read_file(cache)

    raw_zip = os.path.join(C.RAW, "greater-london-latest-free.shp.zip")
    if not os.path.exists(raw_zip):
        r = requests.get(GEofABRIK_LONDON_SHP, timeout=300)
        r.raise_for_status()
        with open(raw_zip, "wb") as f:
            f.write(r.content)

    with zipfile.ZipFile(raw_zip) as z:
        shp = next(n for n in z.namelist() if n.endswith("gis_osm_pois_free_1.shp"))
    pois = gpd.read_file(f"zip://{raw_zip}!{shp}").to_crs(C.CRS_WGS84)
    pois = gpd.clip(pois, areas.to_crs(C.CRS_WGS84))
    group_by_class = {klass: group for group, classes in POI_GROUPS.items() for klass in classes}
    pois["poi_group"] = pois["fclass"].map(group_by_class)
    pois = pois.dropna(subset=["poi_group"])[["poi_group", "fclass", "name", "geometry"]]
    if pois.empty:
        raise RuntimeError("geofabrik osm extract contained no matching central london pois")
    pois.to_file(cache, driver="GeoJSON")
    return pois


def write_ashe_table() -> None:
    out = os.path.join(C.PROCESSED, "ashe_section_pay.csv")
    pd.Series(C.ASHE_SECTION_ANNUAL_PAY, name="annual_pay").rename_axis("section").reset_index().to_csv(out, index=False)


def main() -> None:
    areas = F.fetch_boundaries()
    F.fetch_station_footfall()
    F.fetch_rods_profiles()
    F.fetch_station_coords()
    F.fetch_bres_by_section()
    F.fetch_validation()
    write_ashe_table()
    pois = fetch_osm_pois(areas)

    manifest = {
        "granularity": C.GRANULARITY,
        "areas": len(areas),
        "osm_pois": len(pois),
        "files": sorted(os.listdir(C.PROCESSED)),
    }
    with open(os.path.join(C.PROCESSED, "data_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
