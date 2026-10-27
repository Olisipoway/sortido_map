"""
Geocode Uber Eats delivery addresses via Nominatim (free, 1 req/sec).
Reads ubereats_orders_with_addresses.csv → outputs orders_geocoded.json

Output per order: [lat, lng, total_mins, hour, is_al, order_value, dow, prep_mins, wait_mins, ride_mins]
  total_mins    : placed → delivered (float or null)
  hour          : 0–23 (placed_at local hour)
  is_al         : 1 = Alojamento Local, 0 = residência
  order_value   : float EUR or null
  dow           : 0=Mon … 6=Sun
  prep_mins     : placed → ready_at (float or null)
  wait_mins     : ready_at → picked_up_at (float or null)
  ride_mins     : picked_up_at → delivered (float or null)
"""
import csv, json, time, os, re, math, urllib.request, urllib.parse
from datetime import datetime, timezone

INPUT_CSV   = "ubereats_orders_with_addresses.csv"
CACHE_FILE  = "geocache.json"
AIRBNB_FILE = "airbnb_lisbon.json"
OUTPUT_JSON = "orders_geocoded.json"

AL_RE = re.compile(
    r'\b(hotel|hostel|hostal|guest.?house|guesthouse|pens[aã]o|pousada|lodge|inn|suites?|'
    r'apartments?|apartamentos?|airbnb|milestone|lofts?|boutique|parque guest|'
    r'novotel|mercure|pestana|locke|acta moa|icons hotel|jam lisbon|olaias|apolonia|'
    r'beautique|cr7|dom pedro|raw culture|artroom|brown)\b',
    re.IGNORECASE
)
AL_RADIUS_M = 12.0  # metres — only flag proximity hits very close to a listing


def log(msg): print(msg, flush=True)


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


def nominatim_geocode(address, cache):
    if address in cache:
        return cache[address]
    query = f"{address}, Lisboa, Portugal"
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 1, "countrycodes": "pt",
        "viewbox": "-9.30,38.65,-9.05,38.82", "bounded": 1,
    })
    req = urllib.request.Request(url, headers={"User-Agent": "Sortido-analysis/1.0 vasco@olisipoway.com"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read())
        cache[address] = [float(results[0]["lat"]), float(results[0]["lon"])] if results else None
        time.sleep(1.1)
    except Exception as e:
        log(f"  geocode error: {e}")
        cache[address] = None
    return cache[address]


def parse_timing(row):
    """Returns (total_mins, prep_mins, wait_mins, ride_mins) — each float or None."""
    try:
        placed    = datetime.fromisoformat(row["placed_at"])
        delivered = datetime.fromisoformat(row["delivered_at"])
        total = (delivered - placed).total_seconds() / 60
        if not (5 < total < 120):
            return None, None, None, None
        total = round(total, 1)
    except Exception:
        return None, None, None, None

    prep = wait = ride = None
    try:
        ready   = datetime.fromisoformat(row["ready_at"])
        picked  = datetime.fromisoformat(row["picked_up_at"])
        p = (ready - placed).total_seconds() / 60
        w = (picked - ready).total_seconds() / 60
        r = (delivered - picked).total_seconds() / 60
        if 0 < p < 60 and 0 <= w < 30 and 0 < r < 60:
            prep, wait, ride = round(p, 1), round(w, 1), round(r, 1)
    except Exception:
        pass

    return total, prep, wait, ride


def parse_eur(v):
    if not v:
        return None
    try:
        return round(float(v.replace("€", "").strip()), 2)
    except Exception:
        return None


def parse_hour_dow(row):
    try:
        dt = datetime.fromisoformat(row["placed_at"])
        # Convert to Lisbon local time (UTC+1 winter / UTC+2 summer — approx +1)
        local = dt.utctimetuple()
        hour = (dt.hour + 1) % 24
        dow  = dt.weekday()  # 0=Mon … 6=Sun
        return hour, dow
    except Exception:
        return None, None


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


# Build spatial grid of Airbnb listings for fast proximity lookup
def build_airbnb_grid(airbnb_file, cell_deg=0.001):
    with open(airbnb_file) as f:
        d = json.load(f)
    cols = d["cols"]
    li = cols.index("lat")
    loi = cols.index("lon")
    grid = {}
    for row in d["rows"]:
        lat, lon = row[li], row[loi]
        key = (round(lat / cell_deg), round(lon / cell_deg))
        grid.setdefault(key, []).append((lat, lon))
    return grid, cell_deg


def is_near_airbnb(lat, lon, grid, cell_deg, radius_m=AL_RADIUS_M):
    cells_needed = math.ceil(radius_m / (cell_deg * 111320)) + 1
    for dlat in range(-cells_needed, cells_needed + 1):
        for dlon in range(-cells_needed, cells_needed + 1):
            key = (round(lat / cell_deg) + dlat, round(lon / cell_deg) + dlon)
            for alat, alon in grid.get(key, []):
                if haversine_m(lat, lon, alat, alon) <= radius_m:
                    return True
    return False


if __name__ == "__main__":
    cache = load_cache()

    log("Loading Airbnb grid…")
    ab_grid, ab_cell = build_airbnb_grid(AIRBNB_FILE)
    log(f"  {sum(len(v) for v in ab_grid.values())} listings indexed")

    rows = []
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            oid = row.get("order_id", "")
            if oid and oid != "order_id" and row.get("address"):
                rows.append(row)

    log(f"Orders with address: {len(rows)}")

    unique_addrs = sorted(set(r["address"] for r in rows))
    need = [a for a in unique_addrs if a not in cache]
    log(f"Unique addresses: {len(unique_addrs)}  —  need geocoding: {len(need)}")

    for i, addr in enumerate(need):
        log(f"[{i+1}/{len(need)}] {addr}")
        nominatim_geocode(addr, cache)
        if (i + 1) % 50 == 0:
            save_cache(cache)
            log("  (cache saved)")

    save_cache(cache)

    # AL keyword pre-check per address (fast)
    addr_kw_al = {a: bool(AL_RE.search(a)) for a in unique_addrs}

    # Build output: [lat, lng, total_mins, hour, is_al, order_value, dow, prep_mins, wait_mins, ride_mins]
    points = []
    skipped = 0
    al_count = 0
    for r in rows:
        coords = cache.get(r["address"])
        if not coords:
            skipped += 1
            continue
        lat, lng = coords

        hour, dow = parse_hour_dow(r)
        total, prep, wait, ride = parse_timing(r)
        val   = parse_eur(r.get("order_value"))

        kw_hit = addr_kw_al[r["address"]]
        prox_hit = is_near_airbnb(lat, lng, ab_grid, ab_cell)
        is_al = 1 if (kw_hit or prox_hit) else 0
        if is_al:
            al_count += 1

        points.append([lat, lng, total, hour, is_al, val, dow, prep, wait, ride])

    with open(OUTPUT_JSON, "w") as f:
        json.dump(points, f, separators=(",", ":"))

    hits  = sum(1 for a in unique_addrs if cache.get(a))
    total = len(unique_addrs)
    log(f"\nGeocoded: {hits}/{total} unique addresses ({round(hits/total*100)}%)")
    log(f"AL: {al_count}/{len(points)} ({round(al_count/len(points)*100)}%)")
    log(f"Output: {len(points)} orders → {OUTPUT_JSON}  (skipped {skipped} without coords)")
