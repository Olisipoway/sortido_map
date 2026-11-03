"""
enrich_routes.py
Compute actual road distance + travel time from Sortido to every delivery point
using the OSRM public table service. Works on unique coordinates to minimise
requests, then maps results back to all orders.

Output: orders_routed.json — same structure as orders_geocoded.json but with
two extra fields appended to each row:
  [lat, lng, mins, hour, is_al, val, dow, ..., road_km, road_mins]
"""

import json, time, urllib.request, urllib.parse

SORTIDO_LAT = 38.7255
SORTIDO_LNG = -9.1480
OSRM        = "https://router.project-osrm.org/table/v1/driving"
BATCH       = 90   # safe under OSRM URL length limit
SLEEP       = 0.5  # seconds between requests — be polite to the public server

def osrm_table(source_lng, source_lat, destinations):
    """
    destinations: list of (lng, lat) tuples
    Returns (distances_m, durations_s) lists, one per destination.
    Returns (None, None) on failure.
    """
    coords = f"{source_lng},{source_lat};" + ";".join(f"{ln},{la}" for la, ln in destinations)
    url = f"{OSRM}/{coords}?sources=0&annotations=duration,distance"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Sortido/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        if data.get("code") != "Ok":
            print(f"  OSRM error: {data.get('code')} {data.get('message','')}")
            return None, None
        dists = data["distances"][0][1:]   # skip source→source (0)
        durs  = data["durations"][0][1:]
        return dists, durs
    except Exception as e:
        print(f"  Request failed: {e}")
        return None, None

def main():
    with open("orders_geocoded.json") as f:
        orders = json.load(f)

    # Collect unique (lat, lng) pairs
    unique_pts = list({(round(o[0], 6), round(o[1], 6)) for o in orders})
    print(f"Orders: {len(orders)}  |  Unique points: {len(unique_pts)}")

    # Route unique points
    route_cache = {}  # (lat, lng) → (road_km, road_mins)
    n_batches = (len(unique_pts) + BATCH - 1) // BATCH

    for i in range(n_batches):
        batch = unique_pts[i * BATCH:(i + 1) * BATCH]
        print(f"  Batch {i+1}/{n_batches}  ({len(batch)} pts)…", end=" ", flush=True)

        dists, durs = osrm_table(SORTIDO_LNG, SORTIDO_LAT, batch)

        if dists is None:
            print("FAILED — storing nulls")
            for pt in batch:
                route_cache[pt] = (None, None)
        else:
            for j, pt in enumerate(batch):
                road_km   = round(dists[j] / 1000, 3) if dists[j] is not None else None
                road_mins = round(durs[j]  / 60,   2) if durs[j]  is not None else None
                route_cache[pt] = (road_km, road_mins)
            ok = sum(1 for d in dists if d is not None)
            print(f"ok ({ok}/{len(batch)})")

        time.sleep(SLEEP)

    # Map back to all orders
    enriched = []
    missing  = 0
    for o in orders:
        key = (round(o[0], 6), round(o[1], 6))
        road_km, road_mins = route_cache.get(key, (None, None))
        if road_km is None:
            missing += 1
        enriched.append(list(o) + [road_km, road_mins])

    with open("orders_routed.json", "w") as f:
        json.dump(enriched, f, separators=(",", ":"))

    print(f"\nDone. {len(enriched)} orders saved → orders_routed.json")
    print(f"Missing road data: {missing} orders")

    # Quick stats
    kms = [o[-2] for o in enriched if o[-2] is not None]
    kms.sort()
    if kms:
        p = lambda pct: kms[int(len(kms) * pct)]
        print(f"Road distance — P50: {p(0.50):.2f} km  P90: {p(0.90):.2f} km  P95: {p(0.95):.2f} km  max: {kms[-1]:.2f} km")

if __name__ == "__main__":
    main()
