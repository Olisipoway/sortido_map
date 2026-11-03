"""
Builds a no-go mask for the scoring grid by fetching land-use data from the
OSM map API (tiled to stay within API limits), extracting forest / woodland /
water / nature-reserve polygons, and rasterising them onto the 100×130 GEO grid.

Output: no_go_mask.json  {"rows":100,"cols":130,"data":[0|1,...]}
  data[r*130+c] = 1  →  no-go cell
"""

import json, time, urllib.request, xml.etree.ElementTree as ET
from shapely.geometry import Polygon, MultiPolygon, Point
from shapely.prepared import prep
from shapely.ops import unary_union

# ── GEO grid ─────────────────────────────────────────────────────────────────
LAT0, LAT1 = 38.640, 38.830
LON0, LON1 = -9.320, -9.050
ROWS, COLS  = 100, 130
CELL_LAT = (LAT1 - LAT0) / (ROWS - 1)
CELL_LON = (LON1 - LON0) / (COLS - 1)

NO_GO_TAGS = {
    "natural":  {"wood", "water", "wetland", "scrub"},
    "landuse":  {"forest", "nature_reserve", "reservoir", "basin"},
    "leisure":  {"nature_reserve"},
    "boundary": {"national_park", "protected_area"},
    "waterway": {"riverbank"},
}

def is_no_go(tags):
    for k, good_vals in NO_GO_TAGS.items():
        if tags.get(k) in good_vals:
            return True
    return False

def fetch_tile(west, south, east, north, retry=3):
    url = (f"https://api.openstreetmap.org/api/0.6/map"
           f"?bbox={west},{south},{east},{north}")
    for attempt in range(retry):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sortido-no-go/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:
            print(f"    attempt {attempt+1} failed: {e}")
            if attempt < retry - 1:
                time.sleep(3)
    return None

def parse_polygons(xml_bytes):
    """Extract no-go polygons from an OSM XML tile."""
    root = ET.fromstring(xml_bytes)

    # Index nodes by id
    nodes = {}
    for n in root.findall("node"):
        nodes[n.get("id")] = (float(n.get("lat")), float(n.get("lon")))

    polys = []
    for way in root.findall("way"):
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        if not is_no_go(tags):
            continue
        coords = []
        for nd in way.findall("nd"):
            ref = nd.get("ref")
            if ref in nodes:
                lat, lon = nodes[ref]
                coords.append((lon, lat))
        if len(coords) >= 3:
            try:
                p = Polygon(coords)
                if p.is_valid and not p.is_empty:
                    polys.append(p)
            except Exception:
                pass
    return polys

# ── tile the area (0.14 lon × 0.10 lat tiles) ────────────────────────────────
# Adds a small overlap so polygons on tile borders aren't missed.
OVERLAP   = 0.001

def fetch_area(west, south, east, north, depth=0):
    """Recursively subdivide if a tile is too large for the OSM API."""
    xml_bytes = fetch_tile(west - OVERLAP, south - OVERLAP,
                           east  + OVERLAP, north + OVERLAP)
    if xml_bytes is not None:
        return parse_polygons(xml_bytes)
    if depth >= 3:
        return []   # give up after 3 levels of subdivision
    # Split into 4 sub-tiles
    mlat = (south + north) / 2
    mlon = (west  + east)  / 2
    polys = []
    for (s, n, w, e) in [(south, mlat, west, mlon), (mlat, north, west, mlon),
                          (south, mlat, mlon, east), (mlat, north, mlon, east)]:
        polys.extend(fetch_area(w, s, e, n, depth + 1))
        time.sleep(0.3)
    return polys

# Initial 0.05° × 0.05° tiles, auto-subdivide on 400
TILE = 0.05
tile_bboxes = []
w = LON0
while w < LON1:
    e = min(w + TILE, LON1)
    s = LAT0
    while s < LAT1:
        n = min(s + TILE, LAT1)
        tile_bboxes.append((w, s, e, n))
        s = n
    w = e

print(f"Fetching up to {len(tile_bboxes)} OSM tiles (auto-subdividing dense areas)…")
all_polys = []
for i, (w, s, e, n) in enumerate(tile_bboxes):
    print(f"  [{i+1}/{len(tile_bboxes)}] bbox={s:.3f},{w:.3f},{n:.3f},{e:.3f}", end=" ", flush=True)
    polys = fetch_area(w, s, e, n)
    all_polys.extend(polys)
    print(f"→ {len(polys)} polygons  (total {len(all_polys)})")
    time.sleep(0.4)

print(f"\nTotal polygons before union: {len(all_polys)}")
if not all_polys:
    print("No polygons found – writing empty mask")
    out = {"rows": ROWS, "cols": COLS, "data": [0] * (ROWS * COLS)}
    with open("no_go_mask.json", "w") as f:
        json.dump(out, f, separators=(",", ":"))
    exit(0)

merged  = unary_union(all_polys)
prepped = prep(merged)
print("Union done – rasterising…")

data         = [0] * (ROWS * COLS)
total_marked = 0
for r in range(ROWS):
    clat = LAT1 - r * CELL_LAT
    for c in range(COLS):
        clng = LON0 + c * CELL_LON
        if prepped.contains(Point(clng, clat)):
            data[r * COLS + c] = 1
            total_marked += 1

pct = 100 * total_marked / (ROWS * COLS)
print(f"Marked {total_marked}/{ROWS*COLS} cells as no-go ({pct:.1f}%)")

out = {"rows": ROWS, "cols": COLS, "data": data}
with open("no_go_mask.json", "w") as f:
    json.dump(out, f, separators=(",", ":"))
print("Saved no_go_mask.json")
