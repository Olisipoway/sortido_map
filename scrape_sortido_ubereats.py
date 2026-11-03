"""
Scrape Sortido's complete catalog from UberEats by intercepting API responses
while browsing each category section's full item list.

Uses Playwright to navigate the customer-facing UberEats store and intercepts
getStoreV1 JSON responses to extract all catalog items without the 15-item cap.

Output: sortido_catalog_full.json  →  [{name, price, uuid, category, available}]
        sortido_catalog.json       →  union with existing (preserves order history)

Run with: /usr/bin/python3 scrape_sortido_ubereats.py
"""
import json, time
from playwright.sync_api import sync_playwright
from collections import Counter

STORE_UUID = "755282a8-7d8f-51aa-a570-86867606e6c4"
STORE_URL  = f"https://www.ubereats.com/pt/store/sortido/{STORE_UUID}"

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


def extract_items_from_response(body, fallback_category="?"):
    items = {}
    try:
        data = json.loads(body).get("data", {})
    except Exception:
        return items
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


def scrape_section(page, section_uuid, cat_name, all_items):
    """Navigate to a category section's full listing and collect all items."""
    section_url = f"{STORE_URL}?mod=storeSectionHeader&storeSection={section_uuid}"
    collected = {}

    def on_response(response):
        if "getStoreV1" in response.url and response.status == 200:
            try:
                body = response.body()
                batch = extract_items_from_response(body, cat_name)
                collected.update(batch)
            except Exception:
                pass

    page.on("response", on_response)
    try:
        page.goto(section_url, wait_until="networkidle", timeout=20000)
        time.sleep(1)

        # Scroll to load all items (lazy loading)
        prev_count = 0
        for _ in range(30):
            page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            time.sleep(0.5)
            if len(collected) == prev_count:
                break  # no new items after scroll
            prev_count = len(collected)

        page.evaluate("window.scrollTo(0, 0)")
        time.sleep(0.5)
    except Exception as e:
        print(f"    ⚠ Error loading section: {e}")

    page.remove_listener("response", on_response)
    new = sum(1 for u in collected if u not in all_items)
    all_items.update(collected)
    print(f"  {cat_name:<20} {len(collected):3d} items this section ({new} new, total={len(all_items)})")


def main():
    all_items = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
            locale="pt-PT",
        )
        page = ctx.new_page()

        # Load store front — may hit Cloudflare challenge first
        print("Loading store front…")
        page.goto(STORE_URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Wait for CAPTCHA/challenge to be solved if needed
        if "challenge" in page.url or "def.uber.com" in page.url:
            print("\n🔒 CAPTCHA detected — solve it in the browser window, then press Enter here…")
            input()
            # Wait for redirect back to the store
            page.wait_for_url("**/store/**", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)
            print("✓ Challenge passed, continuing…")

        time.sleep(2)

        print("Scraping category sections…")
        for cat_name, section_uuid in CATEGORY_SECTIONS.items():
            scrape_section(page, section_uuid, cat_name, all_items)
            time.sleep(0.5)

        browser.close()

    print(f"\n✓ {len(all_items)} unique items found")
    return list(all_items.values())


def save(items):
    with open("sortido_catalog_full.json", "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print("→ sortido_catalog_full.json")

    existing_by_key = {}
    try:
        for rec in json.load(open("sortido_catalog.json")):
            existing_by_key[rec["name"].lower().strip()] = rec
    except FileNotFoundError:
        pass

    import datetime
    today = datetime.date.today().isoformat()
    seen = {i["name"].lower().strip() for i in items}

    # Products that are NOT in today's menu become inactive (they used to keep their old flag forever).
    merged_map = {}
    for key, rec in existing_by_key.items():
        rec = dict(rec)
        if key not in seen:
            rec["available"] = False
            rec["on_menu"] = False
        merged_map[key] = rec

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
            "on_menu":   True,          # seen in the latest scrape of the live menu
            "last_seen": today,
        }

    merged = sorted(merged_map.values(), key=lambda x: -x["orders"])
    with open("sortido_catalog.json", "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    api_keys = {i["name"].lower().strip() for i in items}
    kept_old = sum(1 for k in existing_by_key if k not in api_keys)
    print(f"→ sortido_catalog.json updated ({len(merged)} items, "
          f"{sum(1 for m in merged if m.get('orders', 0) > 0)} with order history, "
          f"{kept_old} kept from order history only)")

    print("\nBy category:")
    for cat, n in Counter(i["category"] for i in items).most_common():
        print(f"  {cat:<35} {n} items")


if __name__ == "__main__":
    items = main()
    # Safety: a partial scrape (e.g. blocked by CAPTCHA) must not wipe the menu.
    if len(items) < 300:
        print(f"⚠ only {len(items)} items found — looks like a partial scrape, catalog NOT updated.")
    else:
        save(items)
