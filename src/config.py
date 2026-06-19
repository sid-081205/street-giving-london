"""
Central configuration for the street-giving-potential model.

Everything that is *literature-set* (the "swept" terms p_d, a_d tiers, the
segment time-of-day curves) lives here so it is auditable in one place and
trivial to vary in sensitivity analysis. Everything that is *mapped* (footfall,
job/sector composition, worker income, validation) is fetched from real data
by ``fetch_data.py``.
"""
from __future__ import annotations

import os

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
PROCESSED = os.path.join(ROOT, "data", "processed")
OUTPUTS = os.path.join(ROOT, "outputs")
for _d in (RAW, PROCESSED, OUTPUTS):
    os.makedirs(_d, exist_ok=True)

# --------------------------------------------------------------------------
# Geography  (Section 5: common geography = MSOA, clipped to central London)
# --------------------------------------------------------------------------
# Inner London (statutory) + Newham + City of London -- "CAZ plus surrounding
# high-demand boroughs".  MSOA 2021 names are exactly "<Borough> 001" etc.
CENTRAL_BOROUGHS = [
    "City of London",
    "Westminster",
    "Camden",
    "Islington",
    "Hackney",
    "Tower Hamlets",
    "Southwark",
    "Lambeth",
    "Wandsworth",
    "Kensington and Chelsea",
    "Hammersmith and Fulham",
    "Newham",
    "Greenwich",
    "Lewisham",
    "Haringey",
]

# ONS Open Geography Portal -- (Dec 2021) Generalised Clipped (coastline /
# tidal-Thames clipped, which is what gives the river its gap on the map).
_ARCGIS = "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/{svc}/FeatureServer/0/query"
MSOA_SERVICE = _ARCGIS.format(svc="Middle_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V3")
LSOA_SERVICE = _ARCGIS.format(svc="Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BGC_V5")

# Spatial granularity of the surface.  LSOA (~3x finer, ~1.6k areas centrally)
# matches the reference's fine texture; MSOA is coarser but faster.
GRANULARITY = "LSOA"          # "LSOA" or "MSOA"
GEO = {
    "MSOA": {"service": MSOA_SERVICE, "code": "MSOA21CD", "name": "MSOA21NM",
             "bres_type": "2013265927TYPE152", "strip": r"\s\d{3}$"},
    "LSOA": {"service": LSOA_SERVICE, "code": "LSOA21CD", "name": "LSOA21NM",
             "bres_type": "2013265927TYPE151", "strip": r"\s\d{3}[A-Z]$"},
}

# Coordinate systems
CRS_WGS84 = "EPSG:4326"
CRS_BNG = "EPSG:27700"      # British National Grid -- metric, for distance work
CRS_WEB = "EPSG:3857"       # Web Mercator -- for contextily basemap tiles

# --------------------------------------------------------------------------
# TfL footfall  (Section 4.1: f_d -- the primary mapped driver)
# --------------------------------------------------------------------------
TFL_BUCKET = "https://s3-eu-west-1.amazonaws.com/crowding.data.tfl.gov.uk"
TFL_FOOTFALL_CSV = TFL_BUCKET + "/Network%20Demand/StationFootfall_2024.csv"
TFL_RODS_ZIP = TFL_BUCKET + "/RODS/rods.zip"
TFL_RODS_FLOWS = "RODS_2017/Misc/Station flows by station-time of day 2017.xls"
TFL_STOPPOINT_MODES = ["tube", "dlr", "overground", "elizabeth-line"]
TFL_STOPPOINT_API = "https://api.tfl.gov.uk/StopPoint/Mode/{mode}"

# A station's footfall is felt over a short walk, not just its centroid.
STATION_CATCHMENT_M = 400.0

# --------------------------------------------------------------------------
# BRES employment  (Section 4.1 sector anchors + 4.2 worker income)
# --------------------------------------------------------------------------
NOMIS_BRES = "https://www.nomisweb.co.uk/api/v01/dataset/NM_189_1"
NOMIS_LONDON_MSOA21 = "2013265927TYPE152"   # all 2021 MSOAs within London

# SIC-2007 2-digit division -> section letter (used to roll BRES up to sections)
SIC_DIVISION_TO_SECTION = {
    **{d: "A" for d in range(1, 4)},
    **{d: "B" for d in range(5, 10)},
    **{d: "C" for d in range(10, 34)},
    35: "D",
    **{d: "E" for d in range(36, 40)},
    **{d: "F" for d in range(41, 44)},
    **{d: "G" for d in range(45, 48)},
    **{d: "H" for d in range(49, 54)},
    **{d: "I" for d in range(55, 57)},
    **{d: "J" for d in range(58, 64)},
    **{d: "K" for d in range(64, 67)},
    68: "L",
    **{d: "M" for d in range(69, 76)},
    **{d: "N" for d in range(77, 83)},
    84: "O",
    85: "P",
    **{d: "Q" for d in range(86, 89)},
    **{d: "R" for d in range(90, 94)},
    **{d: "S" for d in range(94, 97)},
    **{d: "T" for d in range(97, 99)},
    99: "U",
}

# ASHE 2023 -- median gross ANNUAL pay (full-time) by SIC section, UK (GBP).
# Source: ONS Annual Survey of Hours and Earnings 2023, industry (SIC 2007)
# section table.  Used only as relative weights, so the worker-income proxy is
# an *index*; absolute level is irrelevant to where the surface peaks.
ASHE_SECTION_ANNUAL_PAY = {
    "A": 26000, "B": 45000, "C": 34500, "D": 50000, "E": 33000,
    "F": 35500, "G": 28000, "H": 33000, "I": 22000, "J": 50000,
    "K": 55000, "L": 36000, "M": 44000, "N": 28000, "O": 38000,
    "P": 35000, "Q": 31000, "R": 30000, "S": 28000, "T": 20000, "U": 40000,
}

# --------------------------------------------------------------------------
# Validation  (Section 7)
# --------------------------------------------------------------------------
# CHAIN's London Datastore page blocks automated access (HTTP 403, WAF).  We
# therefore validate against the official MHCLG rough-sleeping snapshot, which
# is the national single-night count by local authority and is CHAIN-adjacent
# (CHAIN is the London multi-agency database; the snapshot is the headline
# count built from the same outreach).  This is documented in the README.
MHCLG_SNAPSHOT_PAGE = (
    "https://www.gov.uk/government/statistics/"
    "rough-sleeping-snapshot-in-england-autumn-2023"
)

# --------------------------------------------------------------------------
# The six segments  (Section 3)
# --------------------------------------------------------------------------
SEGMENTS = ["workers", "leisure", "shoppers", "tourists", "events", "students"]

# p_d -- probability a passer-by of segment d gives.  SWEPT (Section 4.3): no
# spatial data exists, so one constant per segment from the literature
# (ASU POP Center base rates; students unusually high; CAF UK Giving to bound).
# Absolute scale is arbitrary (it multiplies the whole surface); only the
# *ratios* between segments move the pattern.
P_GIVE = {
    "workers": 0.010,
    "leisure": 0.030,
    "shoppers": 0.012,
    "tourists": 0.020,
    "events": 0.030,
    "students": 0.045,
}

# a_d -- amount handed over per gift (relative £ tiers from the Section-3 table;
# Bose & Hwang calibrate the absolute baseline).  For WORKERS this is replaced
# per-MSOA by the BRES x ASHE income index (Section 4.2); the value here is the
# baseline that the index multiplies.
A_AMOUNT = {
    "workers": 1.20,   # multiplied by income_index(MSOA)
    "leisure": 1.00,
    "shoppers": 0.80,
    "tourists": 0.80,
    "events": 0.70,    # medium, "just spent"
    "students": 0.40,  # readiest to give but least cash
}

# Which BRES sector (employment, by MSOA) anchors each segment in *space*.
# These are the real spatial fingerprints of each crowd type.
SEGMENT_SECTOR_ANCHOR = {
    "workers": ["K", "M", "J", "O", "N", "L"],   # office economy (finance, prof, info, public)
    "leisure": ["I"],                            # accommodation & food service
    "shoppers": ["G"],                           # wholesale & retail
    "tourists": ["I", "R"],                      # hotels + arts/culture/recreation
    "events": ["R"],                             # arts, entertainment & recreation
    "students": ["P"],                           # education
}
# A floor so every segment can appear anywhere there is footfall, not only on
# top of its anchor sector (people pass through, not just work there).
ANCHOR_FLOOR = 0.08

# Hour-of-day weight (0..23) for each segment, multiplied by a day-type factor.
# Shapes encode the Section-3 "when dense" column.  Normalised per (MSOA, hour)
# downstream, so only the relative shape matters.
def _bell(hours, centres, width, base=0.0):
    import numpy as np
    h = np.arange(24)
    out = np.full(24, base, dtype=float)
    for c in centres:
        out += np.exp(-0.5 * ((h - c) / width) ** 2)
    return out

import numpy as _np
SEGMENT_HOUR_PROFILE = {
    "workers":  _bell(None, [8.0, 17.5], 1.4, base=0.05),   # AM + PM commute peaks
    "leisure":  _bell(None, [20.0], 2.6, base=0.05),         # evenings
    "shoppers": _bell(None, [14.0], 3.0, base=0.05),         # midday/afternoon
    "tourists": _bell(None, [13.0], 3.5, base=0.10),         # broad daytime
    "events":   _bell(None, [19.5, 22.5], 1.3, base=0.02),   # show start + turn-out
    "students": _bell(None, [10.0, 16.0], 2.2, base=0.05),   # campus daytime
}
# Normalise each profile to unit area so a segment's *shape* (when it is around)
# is what matters, not how broad/tall its curve happens to be drawn.  Without
# this, segments with wider curves would capture more crowd share everywhere.
SEGMENT_HOUR_PROFILE = {s: p / p.sum() for s, p in SEGMENT_HOUR_PROFILE.items()}

# Weekday vs weekend multiplier per segment (Section 3 "when").
SEGMENT_DAYTYPE = {
    #            weekday, weekend
    "workers":  (1.00, 0.20),
    "leisure":  (0.70, 1.00),
    "shoppers": (0.75, 1.00),
    "tourists": (0.90, 1.00),
    "events":   (0.75, 1.00),
    "students": (1.00, 0.25),
}

# --------------------------------------------------------------------------
# Competition  (Section 4.4) -- MAPPED, and independent of the validation data.
# --------------------------------------------------------------------------
# Endogenous congestion discount: more attractive places attract more people
# working the same crowd, splitting the take.  c saturates with relative
# footfall so it bites hardest exactly where gross is highest.  kappa is swept.
COMPETITION_KAPPA = 0.25

# --------------------------------------------------------------------------
# Visual style  (match the reference: fine MSOA choropleth, diverging palette,
# faint Positron basemap with the Thames, dashed borough edges)
# --------------------------------------------------------------------------
CMAP = "RdBu_r"          # blue (low) -> cream -> red (high)
N_CLASSES = 9            # quantile classes
EDGE_COLOR = "#3b3b3b"
EDGE_WIDTH = 0.15
BOROUGH_EDGE_COLOR = "#222222"
BOROUGH_EDGE_WIDTH = 0.7
FIG_DPI = 200
