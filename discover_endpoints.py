"""
Open each platform in a real browser, set a Lisbon delivery address,
and intercept all API calls to find the store-listing / availability endpoints.
Run headful so you can complete any CAPTCHA or address selection manually.

Usage: python3 discover_endpoints.py [glovo|bolt|ubereats]
"""
import json, sys, time
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

TARGET_LAT = 38.7201
TARGET_LON = -9.1376  # Arroios — known to have darkstores nearby

PLATFORMS = {
    "glovo": {
        "url": "https://glovoapp.com/pt/pt/",
        "domains": ["glovoapp.com", "api.glovoapp.com"],
        "keywords": ["store", "restaurant", "catalog", "address", "zone", "delivery", "feed", "supermarket"],
    },
    "bolt": {
        "url": "https://food.bolt.eu/pt-pt/",
        "domains": ["bolt.eu", "boltsvc.net", "boltfood"],
        "keywords": ["restaurant", "store", "list", "menu", "catalog", "address", "zone"],
    },
    "ubereats": {
        "url": f"https://www.ubereats.com/pt/category/lisbon-pt/grocery?pl=JTdCJTIyYWRkcmVzcyUyMiUzQSUyMkFycm9pb3MlMjIlMkMlMjJyZWZlcmVuY2UlMjIlM0ElMjJDaEVJQ0RBQXhISkhLQUFSRXVFQ1FWZG11RTVJJTI0JTIyJTJDJTIycmVmZXJlbmNlVHlwZSUyMiUzQSUyMmdvb2dsZV9wbGFjZXMlMjIlMkMlMjJsYXRpdHVkZSUyMiUzQTM4LjcyMDElMkMlMjJsb25naXR1ZGUlMjIlM0EtOS4xMzc2JTdE",
        "domains": ["ubereats.com"],
        "keywords": ["feed", "store", "restaurant", "getFeed", "getStorefeed", "getFeedV1", "getStorefeedV1"],
    },
}

def intercept(platform_key):
    cfg = PLATFORMS[platform_key]
    captured = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--lang=pt-PT"],
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="pt-PT",
            timezone_id="Europe/Lisbon",
            geolocation={"latitude": TARGET_LAT, "longitude": TARGET_LON},
            permissions=["geolocation"],
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)

        def on_response(resp):
            url = resp.url
            if not any(d in url for d in cfg["domains"]):
                return
            # keyword filter only for noise reduction on bolt/ubereats; glovo captures all
            if platform_key != "glovo" and not any(k in url.lower() for k in cfg["keywords"]):
                return
            try:
                body = resp.body()
                if len(body) < 10:
                    return
                try:
                    data = json.loads(body)
                except Exception:
                    return
                entry = {
                    "status": resp.status,
                    "method": resp.request.method,
                    "url": url,
                    "body_keys": list(data.keys()) if isinstance(data, dict) else f"list[{len(data)}]",
                    "body_size": len(body),
                }
                captured.append({"url": url, "method": resp.request.method,
                                  "status": resp.status, "data": data})
                print(f"  [{resp.status}] {resp.request.method} {url[:100]}")
                if isinstance(data, dict):
                    print(f"    keys: {list(data.keys())[:8]}")
            except Exception:
                pass

        page.on("response", on_response)

        print(f"\n=== {platform_key.upper()} ===")
        print(f"Opening {cfg['url']}")
        print("Waiting for store list to load...\n")

        page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Dismiss cookie banners
        for sel in ["button[id*='accept']", "button[data-testid*='accept']",
                    "button:has-text('Aceitar')", "button:has-text('Accept')",
                    "button:has-text('OK')"]:
            try:
                page.locator(sel).first.click(timeout=2000)
                time.sleep(0.5)
                break
            except Exception:
                pass

        print("Browser is open.")
        print("→ Set your delivery address to Arroios, Lisboa")
        print("→ Wait for the store list to fully load")
        print("→ Then press Enter here to save and close.\n")
        input("  [Enter when store list is visible] ")
        time.sleep(3)  # capture any trailing calls

        # Save captured calls
        outfile = f"endpoints_{platform_key}.json"
        with open(outfile, "w") as f:
            json.dump(captured, f, ensure_ascii=False, indent=2)
        print(f"\n→ {len(captured)} API calls saved to {outfile}")

        # Print summary of interesting ones
        print("\nStore/availability related calls:")
        for c in captured:
            url = c["url"]
            if isinstance(c["data"], dict):
                keys = list(c["data"].keys())
                # Look for responses that might contain store lists
                if any(k in str(c["data"]).lower() for k in ["store", "restaurant", "vendor", "slug"]):
                    print(f"\n  {c['method']} {url}")
                    print(f"  keys: {keys[:8]}")
                    # Show a small sample
                    for k in keys[:3]:
                        v = c["data"][k]
                        if isinstance(v, list) and len(v) > 0:
                            print(f"  [{k}][0] = {str(v[0])[:120]}")
                        elif isinstance(v, dict):
                            print(f"  [{k}] = {str(v)[:120]}")

        browser.close()


if __name__ == "__main__":
    platform = sys.argv[1] if len(sys.argv) > 1 else None
    if platform and platform in PLATFORMS:
        intercept(platform)
    else:
        print(f"Usage: python3 discover_endpoints.py [{'/'.join(PLATFORMS.keys())}]")
        print("Runs one platform at a time — opens a browser for you to set the address.")
