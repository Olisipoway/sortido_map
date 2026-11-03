"""
Fetch Sortido's product catalog from the UberEats customer API.
Endpoint: POST https://www.ubereats.com/api/getStoreV1  (public, no auth needed)

Strategy: first do a global pagination pass, then fetch each known category
section by UUID to pick up items that global pagination misses. Each API
response paginates through ALL catalog sections, so fetching from different
section entry points expands coverage.

Output: sortido_catalog_full.json  →  [{name, price, uuid, category, available}]
        sortido_catalog.json       →  merged with order history, sorted by orders desc

Note: each section is capped at ~15 items per page by the API. True full
coverage (including all items in each category) would require Playwright to
click "See all" for each category section on ubereats.com.
"""
import subprocess, json, time
from collections import Counter

STORE_UUID = "755282a8-7d8f-51aa-a570-86867606e6c4"
API_URL = "https://www.ubereats.com/api/getStoreV1"
HEADERS = [
    "-H", "accept: */*",
    "-H", "content-type: application/json",
    "-H", "x-csrf-token: x",
    "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "-H", "referer: https://www.ubereats.com/",
]

# Top-level category section UUIDs (from the store's aisles/category list)
CATEGORY_SECTIONS = {
    "Deals":             "7831870f-bd8a-4a2d-8db9-d1c7942d26c0",
    "Beverages":         "b5765cc2-778d-475d-be33-ca2902c21c6c",
    "Candy & Chocolate": "dd28811a-7869-4ba8-930a-e2ff9a8cb346",
    "Snacks":            "a55c3b71-5fdf-4906-b557-da26c17db393",
    "Electronics":       "b76d4c76-3341-453d-89b9-5fc2ba23c9f3",
    "Ice Cream":         "a00d0feb-1c7e-4786-a21f-bb5006b32da6",
    "Pantry":            "2c25f3b5-30c6-4f03-bbec-89409472489d",
    "Personal Care":     "06d425e2-f080-4131-86d9-6833f8f7fee8",
    "Miscellaneous":     "55be439b-a2b5-4b92-9f7a-b1627b063ed8",
    "Alcohol":           "668d350b-8eb1-44a4-863b-04c14149c536",
    "Household":         "a03b1872-3043-45c4-a859-b0801cb2191e",
    "Frozen":            "47288bf2-e63d-4d4d-8638-00c5b8b1dd07",
    "Health":            "72a63b56-e44e-4164-a77a-5120605bc458",
    "Prepared Food":     "08c6ec48-e7a0-44ae-b553-ccde5b936dfb",
    "Fresh Food":        "17d9a1f4-e937-4079-9818-b27e5acc0fa7",
    "Bakery":            "8d265cd0-931c-4adb-992e-323d008c1c73",
    "Pet":               "b2e9dedb-c3de-4f65-9ad4-17f7a593a291",
}


def _fetch(payload):
    r = subprocess.run(
        ["curl", "--silent", "--compressed", API_URL,
         "-X", "POST", *HEADERS, "--data-raw", json.dumps(payload)],
        capture_output=True, text=True
    )
    return json.loads(r.stdout).get("data", {})


def _collect_items(data, fallback_category="?"):
    items = {}
    for section in data.get("catalogSectionsMap", {}).get(STORE_UUID, []):
        if section.get("type") != "HORIZONTAL_GRID":
            continue
        sp = section.get("payload", {}).get("standardItemsPayload", {})
        t = sp.get("title", {})
        category = (t.get("text") if isinstance(t, dict) else str(t)) or fallback_category
        for item in sp.get("catalogItems", []):
            uuid = item.get("uuid", "")
            if uuid:
                items[uuid] = {
                    "name":      item.get("title", ""),
                    "uuid":      uuid,
                    "price":     round(item.get("price", 0) / 100, 2),
                    "category":  category,
                    "available": not item.get("isSoldOut", False),
                }
    return items


def fetch_all_items():
    all_items = {}

    # Fetch by each known category section UUID to maximise coverage
    for cat_name, section_uuid in CATEGORY_SECTIONS.items():
        offset = None
        for _ in range(15):
            payload = {"diningMode": "DELIVERY", "storeUuid": STORE_UUID,
                       "sectionUuid": section_uuid}
            if offset is not None:
                payload["catalogSectionOffset"] = offset
            data = _fetch(payload)
            batch = _collect_items(data, cat_name)
            new = sum(1 for u in batch if u not in all_items)
            all_items.update(batch)
            paging = data.get("catalogSectionPagingInfo", {})
            nxt = paging.get("offset")
            if not nxt or nxt == offset:
                break
            offset = nxt
            time.sleep(0.35)
        print(f"  {cat_name:<20} total={len(all_items)}")
        time.sleep(0.3)

    return list(all_items.values())


if __name__ == "__main__":
    print("Fetching Sortido catalog from UberEats customer API…")
    items = fetch_all_items()

    if not items:
        print("\n⚠ No items found.")
    else:
        print(f"\n✓ {len(items)} unique items found")

        with open("sortido_catalog_full.json", "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print("→ sortido_catalog_full.json")

        # Load existing catalog (preserves order history and items not in current API)
        existing_by_key = {}
        try:
            for rec in json.load(open("sortido_catalog.json")):
                existing_by_key[rec["name"].lower().strip()] = rec
        except FileNotFoundError:
            pass

        # Build merged catalog: start from existing, update/add API items
        api_keys = {item["name"].lower().strip() for item in items}
        merged_map = {}

        # Keep all existing items; update price/uuid/category for those in new API
        for key, rec in existing_by_key.items():
            merged_map[key] = dict(rec)  # preserve name, orders, etc.

        # Update from API: refresh price, uuid, availability; add new items
        for item in items:
            key = item["name"].lower().strip()
            prev = merged_map.get(key, {})
            merged_map[key] = {
                "name":      item["name"],
                "price":     item["price"],
                "uuid":      item["uuid"],
                "category":  item["category"],
                "orders":    prev.get("orders", 0),
                "available": item["available"],
            }

        merged = sorted(merged_map.values(), key=lambda x: -x["orders"])
        api_only = sum(1 for k in api_keys if k not in existing_by_key)
        kept_old = sum(1 for k in existing_by_key if k not in api_keys)
        print(f"  ({api_only} new from API, {kept_old} kept from order history only)")

        with open("sortido_catalog.json", "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"→ sortido_catalog.json updated ({len(merged)} items, "
              f"{sum(1 for m in merged if m['orders'] > 0)} with order history)")

        print("\nSample (first 20, sorted by orders):")
        for it in merged[:20]:
            avail = "" if it.get("available", True) else " [UNAVAIL]"
            print(f"  {it['name']:<55} €{it['price']:.2f}  [{it['category']}]{avail}")

        print("\nBy category:")
        for cat, n in Counter(it["category"] for it in items).most_common():
            print(f"  {cat:<40} {n} items")
