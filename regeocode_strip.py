"""Retry still-None addresses by stripping apartment/floor suffixes and expanding abbreviations."""
import json, time, math, re, urllib.request, urllib.parse

CACHE_FILE = "geocache.json"
LISBON_LAT, LISBON_LNG = 38.7167, -9.1333
MAX_KM = 25

ABBREVS = [
    (r'\bAv\b\.?', 'Avenida'), (r'\bR\b\.', 'Rua'), (r'\bTv\b\.?', 'Travessa'),
    (r'\bCal\b\.?', 'Calçada'), (r'\bLg\b\.?', 'Largo'), (r'\bPç\b\.?', 'Praça'),
    (r'\bEstr\b\.?', 'Estrada'), (r'\bBeco\b', 'Beco'), (r'\bAl\b\.?', 'Alameda'),
]

# Tokens that look like floor/door/apartment markers
SUFFIX_RE = re.compile(r'\s+\d*[a-zA-Z]{1,3}$|\s+\d+[oOºª]\s*\w*$|\s+andar\s*\w*$|\s+apt?\s*\w*$|\s+lote\s*\w*$', re.IGNORECASE)

def clean(addr):
    """Strip floor/door suffix and expand abbreviations."""
    a = addr.strip()
    a = SUFFIX_RE.sub('', a)
    for pat, repl in ABBREVS:
        a = re.sub(pat, repl, a)
    return a.strip()

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1); dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def nominatim(query):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query + ", Lisboa, Portugal", "format": "json", "limit": 5, "countrycodes": "pt",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "Sortido-analysis/1.0 vasco@olisipoway.com"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read())
        time.sleep(1.1)
        for res in results:
            lat, lon = float(res["lat"]), float(res["lon"])
            if haversine_km(lat, lon, LISBON_LAT, LISBON_LNG) <= MAX_KM:
                return [lat, lon]
    except Exception as e:
        print(f"  error: {e}")
        time.sleep(1.1)
    return None

with open(CACHE_FILE) as f:
    cache = json.load(f)

nones = [a for a, v in cache.items() if v is None]
print(f"Retrying {len(nones)} still-None addresses with suffix stripping…")

recovered = 0
for i, addr in enumerate(nones):
    cleaned = clean(addr)
    tried = [addr]
    result = None

    if cleaned != addr:
        result = nominatim(cleaned)
        tried.append(cleaned)

    # Also try just the first 2-3 words (street name + number)
    if not result:
        parts = cleaned.split()
        if len(parts) > 3:
            short = ' '.join(parts[:3])
            if short not in tried:
                result = nominatim(short)
                tried.append(short)

    if result:
        cache[addr] = result
        recovered += 1
        print(f"[{i+1}/{len(nones)}] ✓ {addr!r} → {result[0]:.4f},{result[1]:.4f}  (via {tried[-1]!r})")
    else:
        print(f"[{i+1}/{len(nones)}] ✗ {addr}")

    if (i + 1) % 50 == 0:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
        print("  (cache saved)")

with open(CACHE_FILE, "w") as f:
    json.dump(cache, f)

print(f"\nRecovered {recovered}/{len(nones)}")
print(f"Still None: {len(nones) - recovered}")
