"""Re-geocode None addresses using Photon (Komoot) — no rate limits, Lisbon-biased."""
import json, time, math, re, urllib.request, urllib.parse

CACHE_FILE = "geocache.json"
LISBON_LAT, LISBON_LNG = 38.7167, -9.1333
MAX_KM = 25

SUFFIX_RE = re.compile(
    r'\s+\d*[a-zA-Z]{1,3}$|\s+\d+[oOºª°]\s*\w*$|\s+andar\s*\w*$'
    r'|\s+ap[to]*\s*\w*$|\s+lote\s*\w*$|\s+bloco\s*\w*$|\s+hab\s*\w*$',
    re.IGNORECASE
)
ABBREVS = [
    (r'\bAv\b\.?\s', 'Avenida '), (r'\bR\.\s', 'Rua '), (r'\bTv\b\.?\s', 'Travessa '),
    (r'\bCal\b\.?\s', 'Calçada '), (r'\bLg\b\.?\s', 'Largo '), (r'\bPç\b\.?\s', 'Praça '),
    (r'\bEstr\b\.?\s', 'Estrada '), (r'\bAl\b\.?\s', 'Alameda '),
]

def clean(addr):
    a = addr.strip()
    # Strip floor/door suffixes iteratively
    for _ in range(3):
        new = SUFFIX_RE.sub('', a).strip()
        if new == a:
            break
        a = new
    for pat, repl in ABBREVS:
        a = re.sub(pat, repl, a)
    return a.strip()

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def photon(query):
    url = 'https://photon.komoot.io/api/?q=' + urllib.parse.quote(query + ' Lisboa') + '&limit=5&lat=38.72&lon=-9.15'
    req = urllib.request.Request(url, headers={'User-Agent': 'Sortido-analysis/1.0 vasco@olisipoway.com'})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read())
        time.sleep(0.3)
        for feat in res.get('features', []):
            lon, lat = feat['geometry']['coordinates']
            if haversine_km(lat, lon, LISBON_LAT, LISBON_LNG) <= MAX_KM:
                return [lat, lon]
    except Exception as e:
        print(f"  error: {e}")
        time.sleep(1)
    return None

with open(CACHE_FILE) as f:
    cache = json.load(f)

nones = [a for a, v in cache.items() if v is None]
print(f"Geocoding {len(nones)} addresses via Photon…")

recovered = 0
for i, addr in enumerate(nones):
    cleaned = clean(addr)
    result = photon(cleaned)
    via = cleaned if cleaned != addr else addr

    if not result and cleaned != addr:
        result = photon(addr)
        via = addr

    if result:
        cache[addr] = result
        recovered += 1
        print(f"[{i+1}/{len(nones)}] ✓ {addr!r} → {result[0]:.4f},{result[1]:.4f}")
    else:
        print(f"[{i+1}/{len(nones)}] ✗ {addr}")

    if (i + 1) % 100 == 0:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
        print("  (cache saved)")

with open(CACHE_FILE, "w") as f:
    json.dump(cache, f)

print(f"\nRecovered {recovered}/{len(nones)}")
print(f"Still None: {len(nones) - recovered}")
