"""
Extend pop_grid to include Setúbal metro municipalities (Almada, Seixal, Barreiro,
Moita, Montijo, Palmela, Setúbal) using BGRI21_170.gpkg (AML file).

Steps:
1. Load AML BGRI (covers both Lisboa + Setúbal metro municipalities)
2. Filter to Setúbal municipalities only (Lisboa already in existing grid)
3. Scale 2021 census pop to 2025 estimates per municipality
4. Generate 250m grid cells by aggregating BGRI blocks to cell centroids
5. Apply CPE redistribution (E-REDES, distrito 15 = Setúbal)
6. Apply income weights using municipal medians (no parish rent for Setúbal)
7. Merge with existing pop_grid_2025_income.json
8. Output pop_grid_2025_full.json
"""

import json, csv, math
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from collections import defaultdict

BGRI_AML     = "/tmp/bgri_setubal/BGRI21_170.gpkg"
EREDES_FILE  = "/Users/vasco/Desktop/eredes_meters.csv"
INCOME_FILE  = "/Users/vasco/olisipoway/Sortido/ERendimentoNL2024.xlsx"
POP_IN       = "/Users/vasco/olisipoway/Sortido/pop_grid_2025_income.json"
POP_OUT      = "/Users/vasco/olisipoway/Sortido/pop_grid_2025_full.json"

NATIONAL_MEDIAN = 12316

# 2025 population estimates (Pordata)
POP_2025 = {
    "1503": 202896,  # Almada
    "1504": 91766,   # Barreiro
    "1506": 78541,   # Moita
    "1507": 68064,   # Montijo
    "1508": 77044,   # Palmela
    "1510": 198254,  # Seixal
    "1512": 141266,  # Setúbal
}

# Municipal income 2024 (INE IRS) — load from Excel
import openpyxl
wb = openpyxl.load_workbook(INCOME_FILE, read_only=True)
ws = wb['Sujeitos Passivos_2024']
mun_income = {}
for r in ws.iter_rows(values_only=True):
    if r[1] == 'Município' and r[28]:
        try:
            mun_income[str(r[0])] = float(r[28])
        except (ValueError, TypeError):
            pass

print(f"Income data: {len(mun_income)} municipalities")

# --- Load BGRI for Setúbal municipalities ---
print("Loading AML BGRI…")
bgri = gpd.read_file(BGRI_AML)
if bgri.crs and bgri.crs.to_epsg() != 4326:
    bgri = bgri.to_crs(epsg=4326)

# Keep only Setúbal municipalities
setubal_codes = set(POP_2025.keys())
bgri_st = bgri[bgri["DTMN21"].isin(setubal_codes)].copy()
print(f"  {len(bgri_st)} BGRI blocks in Setúbal municipalities")

# --- Scale to 2025 ---
# Sum 2021 census pop per municipality
bgri_st["N_INDIVIDUOS"] = bgri_st["N_INDIVIDUOS"].fillna(0)
bgri_st["N_INDIVIDUOS_15_24"] = bgri_st["N_INDIVIDUOS_15_24"].fillna(0)
bgri_st["N_INDIVIDUOS_25_64"] = bgri_st["N_INDIVIDUOS_25_64"].fillna(0)
bgri_st["N_RHABITUAL_ARRENDADOS"] = bgri_st["N_RHABITUAL_ARRENDADOS"].fillna(0)

pop_2021 = bgri_st.groupby("DTMN21")["N_INDIVIDUOS"].sum().to_dict()
scale = {code: POP_2025[code] / pop_2021[code] for code in setubal_codes if pop_2021.get(code, 0) > 0}
print("  Scale factors:", {k: round(v, 3) for k, v in scale.items()})

# Apply scale to each block
bgri_st = bgri_st.copy()
for col in ["N_INDIVIDUOS", "N_INDIVIDUOS_15_24", "N_INDIVIDUOS_25_64", "N_RHABITUAL_ARRENDADOS"]:
    bgri_st[col] = bgri_st.apply(
        lambda r: r[col] * scale.get(r["DTMN21"], 1.0), axis=1
    )

# --- E-REDES CPE redistribution for Setúbal ---
print("Loading E-REDES for Setúbal…")
cpe_freg = {}
cpe_conc = defaultdict(int)
with open(EREDES_FILE, encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        if row["coddistrito"] != "15" or row["data"] != "2026-08":
            continue
        try:
            cpes = int(row["cpes_com_leituras"])
        except (ValueError, KeyError):
            continue
        cpe_freg[row["coddistritoconcelhofreguesia"]] = cpes
        cpe_conc[row["coddistritoconcelho"]] += cpes

print(f"  {len(cpe_freg)} Setúbal parishes in E-REDES")

# Census share per freguesia
census_freg = bgri_st.groupby("DTMNFR21")["N_INDIVIDUOS"].sum().to_dict()
census_conc = bgri_st.groupby("DTMN21")["N_INDIVIDUOS"].sum().to_dict()

def cpe_factor(dtmnfr21, dtmn21):
    cs = census_freg.get(dtmnfr21, 0)
    cm = census_conc.get(dtmn21, 0)
    if cm == 0 or cs == 0:
        return 1.0
    census_share = cs / cm
    ct = cpe_conc.get(dtmn21, 0)
    cf = cpe_freg.get(dtmnfr21, None)
    if cf is None or ct == 0:
        return 1.0
    return (cf / ct) / census_share

# --- Generate 250m grid cells ---
print("Generating 250m grid cells…")
CELL_DEG = 250 / 111320  # ~0.002245 degrees

def snap(v):
    return round(round(v / CELL_DEG) * CELL_DEG, 6)

cells = defaultdict(lambda: [0, 0, 0, 0, 0.0])  # (lat,lon) -> [pop,a1,a2,rent,income_sum]

bgri_st["centroid"] = bgri_st.geometry.centroid
for _, row in bgri_st.iterrows():
    clat = snap(row.centroid.y)
    clon = snap(row.centroid.x)
    factor = cpe_factor(row["DTMNFR21"], row["DTMN21"])
    income = mun_income.get(row["DTMN21"], NATIONAL_MEDIAN)
    income_idx = income / NATIONAL_MEDIAN
    pop = row["N_INDIVIDUOS"] * factor
    cells[(clat, clon)][0] += pop
    cells[(clat, clon)][1] += row["N_INDIVIDUOS_15_24"] * factor
    cells[(clat, clon)][2] += row["N_INDIVIDUOS_25_64"] * factor
    cells[(clat, clon)][3] += row["N_RHABITUAL_ARRENDADOS"] * factor
    cells[(clat, clon)][4] += pop * income_idx

print(f"  {len(cells)} new cells")

new_rows = []
for (lat, lon), vals in cells.items():
    pop = round(vals[0])
    if pop == 0:
        continue
    income_idx = round(vals[4] / vals[0], 4) if vals[0] > 0 else 1.0
    new_rows.append([lat, lon, pop, round(vals[1]), round(vals[2]), round(vals[3]), income_idx])

print(f"  {len(new_rows)} non-empty cells, total pop {sum(r[2] for r in new_rows):,}")

# --- Merge with existing grid ---
print("Merging with existing grid…")
with open(POP_IN) as f:
    existing = json.load(f)

all_rows = existing["rows"] + new_rows
out = {"cell_m": 250, "cols": existing["cols"], "rows": all_rows}

with open(POP_OUT, "w") as f:
    json.dump(out, f, separators=(",", ":"))

print(f"Done → {POP_OUT}")
print(f"  Total cells: {len(all_rows):,}, total pop: {sum(r[2] for r in all_rows):,}")
