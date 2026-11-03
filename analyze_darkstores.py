"""
Darkstore area-of-influence analysis.

Uses Sortido's empirical per-sector delivery reach as the influence polygon
for every darkstore — same city, same logistics constraints, same algorithm.
Polygon is translated (not rotated) to each darkstore's coordinates.
"""
import json, math
from collections import defaultdict

# ── constants ─────────────────────────────────────────────────────────────────

SORTIDO_LAT = 38.7255
SORTIDO_LNG = -9.1480
SECTORS     = 36
DEG         = 360 / SECTORS

# ── helpers ───────────────────────────────────────────────────────────────────

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat, dlon = math.radians(lat2-lat1), math.radians(lon2-lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def point_in_sector_polygon(plat, plon, origin_lat, origin_lon, sector_r):
    """True if (plat,plon) is inside the directional polygon centred on origin."""
    cosLat = math.cos(math.radians(origin_lat))
    dy = (plat - origin_lat) * 111.32
    dx = (plon - origin_lon) * 111.32 * cosLat
    dist = math.sqrt(dx*dx + dy*dy)
    if dist < 0.01:
        return True
    bearing = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    s = int(bearing / DEG) % SECTORS
    return dist <= sector_r[s]

# ── load data ─────────────────────────────────────────────────────────────────

with open("darkstores.json") as f:
    stores = json.load(f)

with open("pop_grid_2025_full.json") as f:
    pg = json.load(f)
grid = pg["rows"]  # [lat, lon, pop, age15_24, age25_64, rented_homes, income_idx]

with open("orders_by_address.json") as f:
    orders = json.load(f)  # [lat, lon, count, avg_val]

# ── build Sortido's directional reach template ────────────────────────────────

cosLat0 = math.cos(math.radians(SORTIDO_LAT))
buckets  = [[] for _ in range(SECTORS)]

for lat, lon, cnt, val in orders:
    dy = (lat - SORTIDO_LAT) * 111.32
    dx = (lon - SORTIDO_LNG) * 111.32 * cosLat0
    dist = math.sqrt(dx*dx + dy*dy)
    if dist < 0.05:
        continue
    bearing = (math.degrees(math.atan2(dx, dy)) + 360) % 360
    s = int(bearing / DEG) % SECTORS
    buckets[s].append(dist)

# Global P90 as fallback for data-sparse sectors
all_dists = sorted(d for b in buckets for d in b)
global_p90 = all_dists[int(len(all_dists) * 0.90)]

sector_r = []
for b in buckets:
    if len(b) >= 3:
        b_sorted = sorted(b)
        sector_r.append(b_sorted[int(len(b_sorted) * 0.90)])
    else:
        sector_r.append(global_p90)

# ── metro baseline ────────────────────────────────────────────────────────────

tot_pop=0; tot_a1=0; tot_a2=0; tot_rent=0; tot_inc=0
for r in grid:
    lat, lon, p, a1, a2, rent, inc = r
    tot_pop += p; tot_a1 += a1; tot_a2 += a2; tot_rent += rent; tot_inc += p*inc

metro = {
    "pct_rented":  100 * tot_rent / tot_pop,
    "pct_25_64":   100 * tot_a2   / tot_pop,
    "pct_15_24":   100 * tot_a1   / tot_pop,
    "income_idx":  tot_inc / tot_pop,
}

# ── catchment per darkstore ───────────────────────────────────────────────────

def catchment(slat, slon):
    pop=0; a1=0; a2=0; rent=0; inc_w=0
    for r in grid:
        lat, lon, p, age1, age2, rented, inc = r
        # Tight bbox reject before the polygon test
        if abs(lat-slat) > 0.15 or abs(lon-slon) > 0.20:
            continue
        if point_in_sector_polygon(lat, lon, slat, slon, sector_r):
            pop += p; a1 += age1; a2 += age2; rent += rented; inc_w += p*inc

    ord_count=0; ord_val=0
    for r in orders:
        lat, lon, cnt, val = r
        if point_in_sector_polygon(lat, lon, slat, slon, sector_r):
            ord_count += cnt
            ord_val   += cnt * (val or 0)

    return {
        "pop":            int(pop),
        "pct_rented":     100 * rent / pop if pop else 0,
        "pct_25_64":      100 * a2   / pop if pop else 0,
        "pct_15_24":      100 * a1   / pop if pop else 0,
        "income_idx":     inc_w / pop if pop else 1,
        "sortido_orders": ord_count,
        "sortido_avg_val": ord_val / ord_count if ord_count else 0,
    }

results = []
for s in stores:
    c = catchment(s["lat"], s["lon"])
    c["label"] = s["label"]
    c["brand"] = s["name"]
    results.append(c)

# ── print ─────────────────────────────────────────────────────────────────────

W = 110
print(f"\n{'─'*W}")
print(f"Area of influence derived from Sortido's empirical delivery shape (P90 per sector, translated to each darkstore)")
print(f"{'─'*W}")
print(f"{'Store':<40} {'Pop':>10} {'%rent':>7} {'%25-64':>7} {'%15-24':>7} {'inc_idx':>8} {'Sortido':>9} {'avg€':>6}")
print(f"{'─'*W}")
print(f"{'METRO BASELINE':<40} {'':>10} {metro['pct_rented']:>6.1f}% {metro['pct_25_64']:>6.1f}% {metro['pct_15_24']:>6.1f}% {metro['income_idx']:>8.3f}")
print(f"{'─'*W}")

for r in sorted(results, key=lambda x: (x["brand"], -x["pop"])):
    print(f"{r['label'][:39]:<40} {r['pop']:>10,} {r['pct_rented']:>6.1f}% {r['pct_25_64']:>6.1f}% {r['pct_15_24']:>6.1f}% {r['income_idx']:>8.3f} {r['sortido_orders']:>9,} {r['sortido_avg_val']:>5.1f}€")

# ── brand averages ────────────────────────────────────────────────────────────

def wmean(rs, key): return sum(r[key] for r in rs) / len(rs)

print(f"\n{'─'*W}")
print("Brand averages vs. metro\n")
for brand in sorted(set(r["brand"] for r in results)):
    rs = [r for r in results if r["brand"] == brand]
    print(f"{brand}  (n={len(rs)})")
    for key, lbl in [("pop","pop"), ("pct_rented","%rented"), ("pct_25_64","%25-64"), ("income_idx","inc_idx"), ("sortido_orders","sortido_orders")]:
        v = wmean(rs, key)
        base = metro.get(key)
        if base:
            arrow = "▲" if v > base else "▼"
            print(f"  {lbl:<20} {v:>9.1f}   metro {base:>7.1f}   {arrow}{abs(100*(v-base)/base):.1f}%")
        else:
            print(f"  {lbl:<20} {v:>9.0f}")
    print()
