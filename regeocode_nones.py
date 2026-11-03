"""Re-geocode addresses that returned None in geocache.json.
Drops bounded=1 restriction, validates result within 25km of Lisbon."""
import json, time, math, urllib.request, urllib.parse

CACHE_FILE = "geocache.json"
LISBON_LAT, LISBON_LNG = 38.7167, -9.1333
MAX_KM = 25

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def geocode(address):
    query = f"{address}, Lisboa, Portugal"
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 5, "countrycodes": "pt",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "Sortido-analysis/1.0 vasco@olisipoway.com"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read())
        time.sleep(1.1)
        # Pick first result within 25km of Lisbon
        for res in results:
            lat, lon = float(res["lat"]), float(res["lon"])
            if haversine_km(lat, lon, LISBON_LAT, LISBON_LNG) <= MAX_KM:
                return [lat, lon]
        return None
    except Exception as e:
        print(f"  error: {e}")
        return None

with open(CACHE_FILE) as f:
    cache = json.load(f)

nones = [a for a, v in cache.items() if v is None]
print(f"Retrying {len(nones)} failed addresses…")

recovered = 0
for i, addr in enumerate(nones):
    result = geocode(addr)
    if result:
        cache[addr] = result
        recovered += 1
        print(f"[{i+1}/{len(nones)}] ✓ {addr} → {result[0]:.4f},{result[1]:.4f}")
    else:
        print(f"[{i+1}/{len(nones)}] ✗ {addr}")
    if (i + 1) % 50 == 0:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
        print("  (cache saved)")

with open(CACHE_FILE, "w") as f:
    json.dump(cache, f)

print(f"\nRecovered {recovered}/{len(nones)} addresses")
print(f"Still None: {len(nones) - recovered}")
