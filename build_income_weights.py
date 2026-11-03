"""
Build income weight per pop_grid cell.

Method:
1. Municipal income (median 2024) from ERendimentoNL2024.xlsx
2. Lisboa parish rent (Q2 2026) from Destaque_RENDAS_2026_2T_PT.xlsx
   → rent share splits Lisboa's municipal income across its parishes
3. All other municipalities: uniform municipal income
4. Assign each pop_grid cell its parish via BGRI spatial join (already done
   in build_pop_grid_cpe.py — reuse that mapping)
5. Output: income_weights.json  { DTMNFR21 -> income_index (PT=1.0) }
   and pop_grid_2025_income.json with an extra 'income_idx' column
"""

import json, openpyxl
from collections import defaultdict
import geopandas as gpd
from shapely.geometry import Point

BGRI_FILE    = "/tmp/bgri_lisboa/BGRI21_LISBOA.gpkg"
INCOME_FILE  = "/Users/vasco/olisipoway/Sortido/ERendimentoNL2024.xlsx"
RENT_FILE    = "/Users/vasco/olisipoway/Sortido/Destaque_RENDAS_2026_2T_PT.xlsx"
POP_IN       = "/Users/vasco/olisipoway/Sortido/pop_grid_2025_cpe.json"
POP_OUT      = "/Users/vasco/olisipoway/Sortido/pop_grid_2025_income.json"
WEIGHTS_OUT  = "/Users/vasco/olisipoway/Sortido/income_weights.json"

NATIONAL_MEDIAN = 12316  # 2024

# --- 1. Municipal income ---
print("Loading municipal income…")
wb = openpyxl.load_workbook(INCOME_FILE, read_only=True)
ws = wb['Sujeitos Passivos_2024']
rows = list(ws.iter_rows(values_only=True))

mun_income = {}  # DTMN21 (4-char) -> median income
for r in rows[5:]:
    code  = str(r[0]) if r[0] else ''
    level = r[1]
    med   = r[28]  # P50 rendimento bruto deduzido IRS liquidado
    if level == 'Município' and med:
        try:
            mun_income[code] = float(med)
        except (ValueError, TypeError):
            pass

print(f"  {len(mun_income)} municipalities")

# --- 2. Lisboa parish rent ---
print("Loading Lisboa parish rent…")
wb2 = openpyxl.load_workbook(RENT_FILE, read_only=True)
ws2 = wb2['Lisboa_Freguesias']
rows2 = list(ws2.iter_rows(values_only=True))

# Lisboa municipal rent (row with code '1A01106')
lisbon_mun_rent = None
parish_rent = {}  # INE freguesia code (last 6 digits) -> rent €/m²

for r in rows2[3:]:
    code = str(r[0]).strip() if r[0] else ''
    rent = r[2]
    if not rent:
        continue
    if code == '1A01106':
        lisbon_mun_rent = float(rent)
    elif code.startswith('1A0110'):
        # e.g. '1A0110601' -> DICOFRE '110601'
        dicofre = code.replace('1A0', '')  # '110601'
        parish_rent[dicofre] = float(rent)

print(f"  Lisboa municipal rent: {lisbon_mun_rent} €/m²")
print(f"  {len(parish_rent)} Lisboa parishes with rent data")

# Income for each Lisboa parish = Lisboa_income * (parish_rent / lisboa_mun_rent)
lisbon_income = mun_income.get('1106', 15188)
parish_income = {}
for dicofre, rent in parish_rent.items():
    parish_income[dicofre] = lisbon_income * (rent / lisbon_mun_rent)

# --- 3. Spatial join: assign pop_grid cells to DTMNFR21 ---
print("Loading BGRI and pop_grid…")
bgri = gpd.read_file(BGRI_FILE)
bgri = bgri[["DTMNFR21", "DTMN21", "geometry"]].copy()
if bgri.crs and bgri.crs.to_epsg() != 4326:
    bgri = bgri.to_crs(epsg=4326)

with open(POP_IN) as f:
    grid = json.load(f)

cols = grid["cols"]
li  = cols.index("lat")
loi = cols.index("lon")
rows_grid = grid["rows"]

print("Spatial join…")
pts = gpd.GeoDataFrame(
    {"idx": range(len(rows_grid))},
    geometry=[Point(rows_grid[i][loi], rows_grid[i][li]) for i in range(len(rows_grid))],
    crs="EPSG:4326"
)
joined = gpd.sjoin(pts, bgri[["DTMNFR21", "DTMN21", "geometry"]], how="left", predicate="within")
missing = joined["DTMNFR21"].isna().sum()
if missing:
    nearest = gpd.sjoin_nearest(
        pts.loc[joined[joined["DTMNFR21"].isna()].index],
        bgri[["DTMNFR21", "DTMN21", "geometry"]], how="left"
    )
    joined.loc[joined["DTMNFR21"].isna(), ["DTMNFR21","DTMN21"]] = \
        nearest[["DTMNFR21","DTMN21"]].values

cell_freg = dict(zip(joined["idx"], joined["DTMNFR21"]))
cell_conc = dict(zip(joined["idx"], joined["DTMN21"]))

# --- 4. Assign income per cell ---
print("Assigning income weights…")
new_cols = cols + ["income_idx"]
new_rows = []

for i, row in enumerate(rows_grid):
    freg = cell_freg.get(i, '')
    conc = cell_conc.get(i, '')
    freg_str = str(freg) if freg else ''

    if freg_str.startswith('1106') and freg_str in parish_income:
        income = parish_income[freg_str]
    elif conc and str(conc) in mun_income:
        income = mun_income[str(conc)]
    else:
        income = NATIONAL_MEDIAN

    idx = round(income / NATIONAL_MEDIAN, 4)
    new_rows.append(list(row) + [idx])

# --- 5. Output ---
out = {"cell_m": grid["cell_m"], "cols": new_cols, "rows": new_rows}
with open(POP_OUT, "w") as f:
    json.dump(out, f, separators=(",", ":"))

# Also write a simple lookup for the map
weights = {}
for i, row in enumerate(new_rows):
    freg = cell_freg.get(i, '')
    if freg:
        weights[str(freg)] = row[-1]

with open(WEIGHTS_OUT, "w") as f:
    json.dump(weights, f, separators=(",", ":"))

print(f"Done → {POP_OUT}")
idxs = [r[-1] for r in new_rows]
print(f"  Income index range: {min(idxs):.2f} – {max(idxs):.2f}, mean {sum(idxs)/len(idxs):.2f}")
