"""
Fetch dark store locations in Lisbon via Google Places API.
Covers Glovo Market / Glovo Express and Bolt Market.
Outputs darkstores.json for the map.
"""
import json, urllib.request, urllib.parse, time

GPLACES_KEY = "AIzaSyCaizcuV7Mg7_-6rtS86vnHoShZUdi8Px8"
PLACES_URL  = "https://places.googleapis.com/v1/places:searchText"

LISBON_CENTER = {"latitude": 38.737, "longitude": -9.178}

DARK_BRANDS = {
    "glovo": ("Glovo Market", "#ffc244"),
    "bolt market": ("Bolt Market", "#34d186"),
    "getir": ("Getir", "#5c16c5"),
}

# Multiple queries to maximise coverage across the metro area
QUERIES = [
    "Glovo Market Lisboa",
    "Glovo Express Lisboa",
    "Glovo Express Almada",
    "Glovo Express Amadora",
    "Glovo Express Sacavém",
    "Bolt Market Lisboa",
    "Bolt Market Lisbon delivery store",
    "Getir Lisboa",
    "Getir Lisbon dark store",
]


def places_search(text_query):
    payload = json.dumps({
        "textQuery": text_query,
        "maxResultCount": 20,
        "locationBias": {
            "circle": {
                "center": LISBON_CENTER,
                "radius": 25000,
            }
        },
    }).encode()
    req = urllib.request.Request(
        PLACES_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GPLACES_KEY,
            "X-Goog-FieldMask": "places.displayName,places.location,places.formattedAddress",
            "User-Agent": "Sortido/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read()).get("places", [])


def classify(display_name):
    name_lower = display_name.lower()
    for key, (brand, color) in DARK_BRANDS.items():
        if key in name_lower:
            return brand, color
    return None, None


if __name__ == "__main__":
    seen = set()
    stores = []

    for q in QUERIES:
        print(f"Querying: {q}")
        try:
            places = places_search(q)
        except Exception as e:
            print(f"  Error: {e}")
            time.sleep(2)
            continue

        for p in places:
            addr = p.get("formattedAddress", "")
            disp = p.get("displayName", {}).get("text", "")
            loc  = p.get("location", {})
            lat  = loc.get("latitude")
            lng  = loc.get("longitude")
            if not lat or not lng:
                continue

            brand, color = classify(disp)
            if not brand:
                continue

            # Dedupe by rounded coords
            key = f"{round(lat, 4)},{round(lng, 4)}"
            if key in seen:
                continue
            seen.add(key)

            stores.append({
                "lat":   lat,
                "lon":   lng,
                "name":  brand,
                "label": disp,
                "color": color,
            })
            print(f"  + [{brand}] {disp} — {addr}")

        time.sleep(0.3)

    stores.sort(key=lambda s: s["name"])

    from collections import Counter
    counts = Counter(s["name"] for s in stores)
    print("\nDark store counts:")
    for brand, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {brand:<20} {n}")

    with open("darkstores.json", "w", encoding="utf-8") as f:
        json.dump(stores, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n→ {len(stores)} dark stores saved to darkstores.json")
