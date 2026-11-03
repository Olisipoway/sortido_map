"""
Scrape Bolt Market Portugal via deliveryuser.live.boltsvc.net API.
Discovers all Bolt Market stores in Lisbon and extracts their catalogs.
Output: bolt_catalogs.json  →  {store_id: {name, lat, lng, products: [{name, price, category}]}}
        bolt_catalog.json   →  [{name, price, source, store_id, store_name}]  (merged, deduped)
"""
import cloudscraper, json, uuid, time, re

BASE = "https://deliveryuser.live.boltsvc.net/deliveryClient"

def make_params():
    session_id = str(uuid.uuid4()) + "eater" + str(int(time.time()))
    distinct_id = "$device:" + str(uuid.uuid4())
    device_id = str(uuid.uuid4())
    return {
        "version": "FW.1.121", "language": "pt-PT", "session_id": session_id,
        "distinct_id": distinct_id, "deviceId": device_id, "deviceType": "iphone",
        "device_name": "web", "device_os_version": "17_0", "theme": "light",
    }

scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "darwin", "mobile": False})

# --- Discover Bolt Market stores across Lisbon ---
LISBON_GRID = [
    # (label, lat, lng)
    ("Centro",          38.7169, -9.1399),
    ("Avenidas Novas",  38.7356, -9.1509),
    ("Benfica",         38.7500, -9.1924),
    ("Arroios",         38.7201, -9.1376),
    ("Campo Ourique",   38.7149, -9.1684),
    ("Alcantara",       38.7048, -9.1727),
    ("Parque Nacoes",   38.7635, -9.1043),
    ("Odivelas",        38.7923, -9.1860),
    ("Oeiras",          38.6939, -9.3087),
    ("Setubal",         38.5244, -8.8933),
]

bolt_stores = {}

print("=== Discovering Bolt Market stores ===")
for label, lat, lng in LISBON_GRID:
    params = make_params()
    try:
        r = scraper.get(f"{BASE}/public/getScreenContent", params={
            **params, "delivery_lat": lat, "delivery_lng": lng, "screen_id": 120001,
        }, timeout=15)
        data = r.json().get("data", {})
        providers_wrap = data.get("providers", {})
        if isinstance(providers_wrap, dict) and "data" in providers_wrap:
            providers = providers_wrap["data"]
        else:
            providers = providers_wrap if isinstance(providers_wrap, dict) else {}

        for pid, prov in providers.items():
            if not isinstance(prov, dict):
                continue
            name = prov.get("name", "")
            if "bolt market" in name.lower():
                if pid not in bolt_stores:
                    contact = prov.get("contact", {}) or {}
                    bolt_stores[pid] = {
                        "id": pid, "name": name,
                        "lat": contact.get("lat"), "lng": contact.get("lng"),
                    }
                    print(f"  Found: [{pid}] {name} ({contact.get('lat')},{contact.get('lng')})")
        time.sleep(0.5)
    except Exception as e:
        print(f"  Error at {label}: {e}")

print(f"\nTotal Bolt Market stores: {len(bolt_stores)}")


def get_store_catalog(store_id, store_lat, store_lng):
    """Fetch all products and prices for a store."""
    params = make_params()
    products = []

    # Get menu categories
    r = scraper.get(f"{BASE}/public/getMenuCategories", params={
        **params, "delivery_lat": store_lat, "delivery_lng": store_lng,
        "provider_id": store_id,
    }, timeout=20)
    cats_data = r.json().get("data", {})
    items = cats_data.get("items", {})
    root_id = cats_data.get("root_id")

    # Get top-level categories from root
    root_item = items.get(str(root_id), {})
    top_cat_ids = root_item.get("child_ids", [])
    if not top_cat_ids:
        # Fallback: all items of type category whose parent is root
        top_cat_ids = [
            iid for iid, item in items.items()
            if item.get("type") == "category" and str(item.get("parent_id", "")) == str(root_id)
        ]

    # Get category name mapping from items
    cat_names = {}
    for iid, item in items.items():
        if item.get("type") == "category":
            cat_names[str(iid)] = item.get("name", {}).get("value", "?")

    print(f"  Categories: {len(top_cat_ids)}")

    for cat_id in top_cat_ids:
        cat_name = cat_names.get(str(cat_id), str(cat_id))
        try:
            r2 = scraper.get(f"{BASE}/public/getMenuDishes", params={
                **params, "delivery_lat": store_lat, "delivery_lng": store_lng,
                "provider_id": store_id, "category_id": cat_id,
            }, timeout=15)
            dishes_data = r2.json().get("data", {})
            dish_items = dishes_data.get("items", {})

            # Build subcategory name map
            sub_cat_names = {}
            for did, dish in dish_items.items():
                if dish.get("type") == "category":
                    sub_cat_names[str(did)] = dish.get("name", {}).get("value", cat_name)

            for did, dish in dish_items.items():
                if dish.get("type") != "dish":
                    continue
                name = dish.get("name", {}).get("value", "")
                price_data = dish.get("price")
                if not price_data or not name:
                    continue
                price = price_data.get("value")
                if price is None:
                    continue

                # Determine subcategory
                parent_id = str(dish.get("parent_id", ""))
                sub_cat = sub_cat_names.get(parent_id, cat_name)

                products.append({
                    "name": name,
                    "price": round(float(price), 2),
                    "category": sub_cat or cat_name,
                })
            time.sleep(0.3)
        except Exception as e:
            print(f"    Error getting dishes for cat {cat_id}: {e}")

    # Deduplicate by name (keep lowest price)
    by_name = {}
    for p in products:
        key = p["name"].strip().lower()
        if key not in by_name or p["price"] < by_name[key]["price"]:
            by_name[key] = p

    return list(by_name.values())


# --- Scrape each store ---
all_catalogs = {}
all_products_merged = {}

for store_id, store_info in bolt_stores.items():
    lat = store_info["lat"] or 38.72
    lng = store_info["lng"] or -9.14
    print(f"\n=== Scraping {store_info['name']} ({store_id}) ===")
    products = get_store_catalog(store_id, lat, lng)
    print(f"  Products: {len(products)}")
    store_info["products"] = products
    all_catalogs[store_id] = store_info

    # Merge into combined catalog (deduplicate by name, keep min price)
    for p in products:
        key = p["name"].strip().lower()
        if key not in all_products_merged or p["price"] < all_products_merged[key]["price"]:
            all_products_merged[key] = {
                "name": p["name"],
                "price": p["price"],
                "category": p["category"],
                "source": "bolt",
                "store_id": store_id,
                "store_name": store_info["name"],
            }

# --- Save outputs ---
with open("bolt_catalogs.json", "w", encoding="utf-8") as f:
    json.dump(all_catalogs, f, ensure_ascii=False, indent=2)
print(f"\n→ bolt_catalogs.json saved ({len(all_catalogs)} stores)")

merged = sorted(all_products_merged.values(), key=lambda x: x["name"])
with open("bolt_catalog.json", "w", encoding="utf-8") as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)
print(f"→ bolt_catalog.json saved ({len(merged)} unique products)")

# Show sample
print("\nSample products:")
for p in merged[:15]:
    print(f"  {p['name']:<55} €{p['price']:.2f} [{p['store_name']}]")
