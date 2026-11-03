"""
Fetch supermarket locations in Lisbon via Overpass API (OSM).
Outputs competitors_supermarkets.json for the map.
"""
import json, urllib.request, urllib.parse, time

BBOX = "(38.65,-9.30,38.82,-9.05)"  # Lisbon bounding box

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

QUERY = f"""
[out:json][timeout:30];
(
  node["shop"~"supermarket|convenience|grocery"]{BBOX};
  way["shop"~"supermarket|convenience|grocery"]{BBOX};
);
out center tags;
"""

# Brand normalisation → display name + colour
BRAND_MAP = {
    "pingo doce":       ("Pingo Doce",    "#e2001a"),
    "continente":       ("Continente",    "#f97316"),
    "continente modelo":("Continente",    "#f97316"),
    "continente bom dia":("Continente",   "#f97316"),
    "auchan":           ("Auchan",        "#006db7"),
    "jumbo":            ("Auchan",        "#006db7"),
    "lidl":             ("Lidl",          "#f7d117"),
    "mercadona":        ("Mercadona",     "#28a745"),
    "minipreço":        ("Minipreço",     "#9b59b6"),
    "intermarché":      ("Intermarché",   "#c0392b"),
    "intermarch":       ("Intermarché",   "#c0392b"),
    "el corte inglés":  ("El Corte Inglés","#1a1a1a"),
    "el corte ingles":  ("El Corte Inglés","#1a1a1a"),
    "froiz":            ("Froiz",         "#2ecc71"),
    "dia":              ("DIA",           "#e74c3c"),
    "spar":             ("SPAR",          "#007d40"),
    "pão de açúcar":    ("Pão de Açúcar", "#e67e22"),
    "pao de acucar":    ("Pão de Açúcar", "#e67e22"),
    "glovo market":     ("Glovo Market",  "#ffc244"),
    "bolt market":      ("Bolt Market",   "#34d186"),
    "aldi":             ("Aldi",          "#005ca9"),
    "meu super":        ("Meu Super",     "#e8a000"),
    "celeiro":          ("Celeiro",       "#5a8a3c"),
    "supercor":         ("Supercor",      "#1a1a1a"),
}
OTHER_COLOR = "#6b7280"


def normalise_brand(tags):
    for field in ("brand", "name", "operator"):
        val = tags.get(field, "").strip().lower()
        for key, (name, color) in BRAND_MAP.items():
            if key in val:
                return name, color
    return None, None  # not a tracked chain


def fetch_overpass():
    print("Querying Overpass API…")
    data = urllib.parse.urlencode({"data": QUERY}).encode()
    req  = urllib.request.Request(OVERPASS_URL, data=data,
                                  headers={"User-Agent": "Sortido/1.0"})
    with urllib.request.urlopen(req, timeout=35) as r:
        return json.loads(r.read())


if __name__ == "__main__":
    raw = fetch_overpass()
    elements = raw.get("elements", [])
    print(f"Raw elements: {len(elements)}")

    stores = []
    seen   = set()
    for el in elements:
        tags = el.get("tags", {})
        if el["type"] == "node":
            lat, lon = el["lat"], el["lon"]
        else:
            c = el.get("center", {})
            lat, lon = c.get("lat"), c.get("lon")
        if not lat or not lon:
            continue

        name, color = normalise_brand(tags)
        if not name:
            continue  # skip non-chain stores

        key = f"{round(lat,4)},{round(lon,4)}"
        if key in seen:
            continue
        seen.add(key)
        stores.append({
            "lat":   lat,
            "lon":   lon,
            "name":  name,
            "label": tags.get("name", name),
            "color": color,
        })

    # Sort by brand for cleaner legend
    stores.sort(key=lambda s: s["name"])

    # Summary
    from collections import Counter
    counts = Counter(s["name"] for s in stores)
    print("\nBrand counts:")
    for brand, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {brand:<22} {n}")

    with open("competitors_supermarkets.json", "w", encoding="utf-8") as f:
        json.dump(stores, f, ensure_ascii=False, separators=(",", ":"))

    print(f"\n→ {len(stores)} stores saved to competitors_supermarkets.json")
