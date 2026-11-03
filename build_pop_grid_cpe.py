"""
Rebuild pop_grid_2025.json with CPE-based sub-municipal population redistribution.

Steps:
1. Load BGRI 2021 polygons → centroid lat/lon + DTMNFR21 + N_INDIVIDUOS
2. Load E-REDES Aug 2026 CPEs per freguesia (Lisbon district only)
3. Load pop_grid_2025.json (250m cells, already scaled to 2025 municipal totals)
4. Assign each pop_grid cell to a freguesia via spatial join
5. Compute CPE share per freguesia within each municipality
6. Compute redistribution factor = cpe_share / census_share (per freguesia)
7. Rescale each cell's population columns by that factor
8. Write pop_grid_2025_cpe.json
"""

import json, csv
from collections import defaultdict
import geopandas as gpd
from shapely.geometry import Point

BGRI_FILE    = "/tmp/bgri_lisboa/BGRI21_LISBOA.gpkg"
EREDES_FILE  = "/Users/vasco/Desktop/eredes_meters.csv"
POP_IN       = "/Users/vasco/olisipoway/Sortido/pop_grid_2025.json"
POP_OUT      = "/Users/vasco/olisipoway/Sortido/pop_grid_2025_cpe.json"

EREDES_DATE  = "2026-08"
LISBOA_DT    = "11"

print("Loading BGRI…")
bgri = gpd.read_file(BGRI_FILE)
bgri = bgri[["DTMNFR21", "DTMN21", "N_INDIVIDUOS", "geometry"]].copy()
bgri["N_INDIVIDUOS"] = bgri["N_INDIVIDUOS"].fillna(0)

# Reproject to WGS84 if needed
if bgri.crs and bgri.crs.to_epsg() != 4326:
    bgri = bgri.to_crs(epsg=4326)

print(f"  {len(bgri)} BGRI subsections")

# --- E-REDES: CPEs per freguesia (Lisbon district, Aug 2026) ---
print("Loading E-REDES…")
cpe_freg = {}   # coddistritoconcelhofreguesia → CPEs
cpe_conc = defaultdict(int)  # coddistritoconcelho → total CPEs

with open(EREDES_FILE, encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        if row["coddistrito"] != LISBOA_DT or row["data"] != EREDES_DATE:
            continue
        try:
            cpes = int(row["cpes_com_leituras"])
        except (ValueError, KeyError):
            continue
        code_freg = row["coddistritoconcelhofreguesia"]
        code_conc = row["coddistritoconcelho"]
        cpe_freg[code_freg] = cpes
        cpe_conc[code_conc] += cpes

print(f"  {len(cpe_freg)} freguesias, {len(cpe_conc)} concelhos")

# --- Census share: N_INDIVIDUOS per freguesia / per município ---
census_conc = defaultdict(float)
census_freg = defaultdict(float)
for _, row in bgri.iterrows():
    census_freg[row["DTMNFR21"]] += row["N_INDIVIDUOS"]
    census_conc[row["DTMN21"]]   += row["N_INDIVIDUOS"]

# --- Redistribution factors ---
# factor_F = (cpe_F / cpe_M) / (census_F / census_M)
# If CPE data missing for a freguesia, factor = 1.0 (no change)
redist = {}
for code_freg, pop_freg in census_freg.items():
    code_conc = code_freg[:4]  # first 4 chars = district+municipality
    pop_conc  = census_conc.get(code_conc, 0)
    if pop_conc == 0:
        redist[code_freg] = 1.0
        continue
    census_share = pop_freg / pop_conc

    # E-REDES codes use 6-char coddistritoconcelho; DTMN21 is 4-char
    # Map: DTMN21 "1106" → coddistritoconcelho "1106"
    cpe_total = cpe_conc.get(code_conc, 0)
    cpe_f     = cpe_freg.get(code_freg, None)

    if cpe_f is None or cpe_total == 0 or census_share == 0:
        redist[code_freg] = 1.0
    else:
        cpe_share = cpe_f / cpe_total
        redist[code_freg] = cpe_share / census_share

factors = list(redist.values())
print(f"  Redistribution factors: min={min(factors):.2f} max={max(factors):.2f} "
      f"mean={sum(factors)/len(factors):.2f}")

# --- Load pop grid ---
print("Loading pop_grid_2025.json…")
with open(POP_IN) as f:
    grid = json.load(f)

cols = grid["cols"]
li   = cols.index("lat")
loi  = cols.index("lon")
pi   = cols.index("pop")
a1i  = cols.index("age15_24")
a2i  = cols.index("age25_64")
ri   = cols.index("rented_homes")

rows = grid["rows"]
print(f"  {len(rows)} cells")

# --- Spatial join: assign each cell to a BGRI polygon → DTMNFR21 ---
print("Spatial join (this may take a minute)…")

# Build a GeoDataFrame from pop_grid points
from shapely.geometry import Point
import pandas as pd

pts = gpd.GeoDataFrame(
    {"idx": range(len(rows))},
    geometry=[Point(rows[i][loi], rows[i][li]) for i in range(len(rows))],
    crs="EPSG:4326"
)

joined = gpd.sjoin(pts, bgri[["DTMNFR21", "geometry"]], how="left", predicate="within")
# Some points may fall outside all polygons (border cells); use nearest fallback
missing = joined["DTMNFR21"].isna().sum()
if missing:
    print(f"  {missing} cells outside BGRI polygons — using nearest")
    missing_idx = joined[joined["DTMNFR21"].isna()].index
    missing_pts = pts.loc[missing_idx]
    nearest = gpd.sjoin_nearest(missing_pts, bgri[["DTMNFR21", "geometry"]], how="left")
    joined.loc[missing_idx, "DTMNFR21"] = nearest["DTMNFR21"].values

cell_freg = dict(zip(joined["idx"], joined["DTMNFR21"]))

# --- Apply redistribution ---
print("Applying redistribution factors…")
new_rows = []
adjusted = 0
for i, row in enumerate(rows):
    freg = cell_freg.get(i)
    factor = redist.get(freg, 1.0) if freg else 1.0
    if abs(factor - 1.0) > 0.001:
        adjusted += 1
    r = list(row)
    r[pi]  = round(row[pi]  * factor)
    r[a1i] = round(row[a1i] * factor)
    r[a2i] = round(row[a2i] * factor)
    r[ri]  = round(row[ri]  * factor)
    new_rows.append(r)

print(f"  {adjusted} cells had factor != 1.0")

out = {"cell_m": grid["cell_m"], "cols": cols, "rows": new_rows}
with open(POP_OUT, "w") as f:
    json.dump(out, f, separators=(",", ":"))

print(f"Done → {POP_OUT}")
orig_pop = sum(r[pi] for r in rows)
new_pop  = sum(r[pi] for r in new_rows)
print(f"  Total pop: {orig_pop:,} → {new_pop:,} (delta {new_pop - orig_pop:+,})")
