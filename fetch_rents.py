"""
Fetch commercial rental listings (lojas) in Lisbon from Imovirtual.
Geocodes each unique parish via Nominatim.
Outputs rents_by_parish.json  →  [{parish, lat, lon, median_eur_m2, count}]
"""
import json, re, time, urllib.request, urllib.parse
from collections import defaultdict
from statistics import median

BASE_URL = "https://www.imovirtual.com/arrendar/loja/lisboa/?page={page}"
HEADERS  = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
             "Accept-Language": "pt-PT,pt;q=0.9"}
NOMINATIM = "https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1&countrycodes=pt"

geo_cache = {}

def geocode_parish(name: str) -> tuple | None:
    if name in geo_cache:
        return geo_cache[name]
    q = urllib.parse.quote(f"{name}, Lisboa, Portugal")
    req = urllib.request.Request(NOMINATIM.format(q=q),
                                  headers={"User-Agent": "Sortido/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read())
        if results:
            lat = float(results[0]["lat"])
            lon = float(results[0]["lon"])
            geo_cache[name] = (lat, lon)
            return lat, lon
    except Exception as e:
        print(f"    geocode error for {name}: {e}")
    geo_cache[name] = None
    return None

def fetch_page(page: int) -> str:
    url = BASE_URL.format(page=page)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")

def parse_listings(html: str) -> list:
    m = re.search(r'"items":\[(\{"id".*?)\],"pagination"', html, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads("[" + m.group(1) + "]")
    except json.JSONDecodeError:
        return []

def get_total_pages(html: str) -> int:
    m = re.search(r'"totalPages":(\d+)', html)
    return int(m.group(1)) if m else 1

def extract_record(item: dict) -> dict | None:
    price_obj = item.get("totalPrice") or item.get("rentPrice")
    area       = item.get("areaInSquareMeters")
    if not price_obj or not area or area <= 0:
        return None
    price = price_obj.get("value")
    if not price or price <= 0:
        return None

    eur_m2 = price / area
    if not (3 <= eur_m2 <= 150):
        return None

    locs   = (item.get("location") or {}) \
                  .get("reverseGeocoding", {}) \
                  .get("locations", [])

    # Use parish (level 3) — more granular than council, less noisy than neighbourhood
    parish = None
    for loc in locs:
        if loc.get("locationLevel") == "parish":
            parish = loc.get("name", "").strip()
            break

    if not parish:
        return None

    return {"parish": parish, "eur_m2": eur_m2}

def main():
    print("Fetching page 1…")
    html1       = fetch_page(1)
    total_pages = min(get_total_pages(html1), 25)
    print(f"Total pages: {total_pages}")

    records_by_parish = defaultdict(list)

    def process(html):
        for item in parse_listings(html):
            rec = extract_record(item)
            if rec:
                records_by_parish[rec["parish"]].append(rec["eur_m2"])

    process(html1)
    for page in range(2, total_pages + 1):
        print(f"  page {page}/{total_pages}…", end=" ", flush=True)
        try:
            html = fetch_page(page)
            process(html)
            print(f"{sum(len(v) for v in records_by_parish.values())} records")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(0.8)

    print(f"\nGeocoding {len(records_by_parish)} unique parishes…")
    output = []
    for parish, values in sorted(records_by_parish.items(), key=lambda x: -len(x[1])):
        time.sleep(1.1)  # Nominatim rate limit: 1 req/s
        coords = geocode_parish(parish)
        med = round(median(values), 1)
        print(f"  {parish:<35} n={len(values):3d}  median={med:5.1f} €/m²  coords={coords}")
        output.append({
            "parish":        parish,
            "lat":           coords[0] if coords else None,
            "lon":           coords[1] if coords else None,
            "median_eur_m2": med,
            "mean_eur_m2":   round(sum(values) / len(values), 1),
            "count":         len(values),
        })

    with open("rents_by_parish.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    total = sum(len(v) for v in records_by_parish.values())
    print(f"\n→ {total} valid listings, {len(output)} parishes → rents_by_parish.json")

if __name__ == "__main__":
    main()
