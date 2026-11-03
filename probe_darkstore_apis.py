"""
Probe Bolt and Getir APIs with stealth Playwright.
Intercepts XHR/fetch requests to find catalog endpoints.
"""
import json, time
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

BOLT_STORES = [
    ("Avenidas Novas", 38.7356349, -9.1508527),
    ("Benfica",        38.7500742, -9.1924728),
]
GETIR_STORES = [
    ("Avenidas Novas",  38.742458, -9.157631),
    ("Parque Nações",   38.763529, -9.104281),
]

captured = {"bolt": [], "getir": []}

def probe_bolt(page, lat, lng, label):
    print(f"\n=== BOLT {label} ===")
    api_calls = []

    def on_request(req):
        url = req.url
        if any(k in url for k in ["bolt.eu", "bolt.food", "boltfood"]):
            if any(k in url for k in ["menu", "catalog", "product", "item", "store", "restaurant"]):
                api_calls.append(("REQ", req.method, url[:120]))

    def on_response(resp):
        url = resp.url
        if any(k in url for k in ["bolt.eu", "bolt.food"]):
            if any(k in url for k in ["menu", "catalog", "product", "item", "store", "restaurant"]):
                try:
                    body = resp.body()
                    if b'"price"' in body or b'"items"' in body:
                        data = json.loads(body)
                        api_calls.append(("RESP+DATA", resp.status, url[:120]))
                        captured["bolt"].append({"label": label, "url": url, "data": data})
                except:
                    pass

    page.on("request", on_request)
    page.on("response", on_response)

    # Try the restaurant list API directly
    endpoints = [
        f"https://node.bolt.eu/foodDelivery/V2/restaurant/list?lat={lat}&lng={lng}&language=pt&deviceType=web&version=CI.27.0",
        f"https://food.bolt.eu/api/restaurants?lat={lat}&lng={lng}&language=pt",
        "https://food.bolt.eu/pt-pt/",
    ]
    for url in endpoints:
        try:
            r = page.goto(url, wait_until="networkidle", timeout=15000)
            print(f"  {url[:80]} → {r.status if r else '?'}")
            time.sleep(2)
            # Try to get page content
            body = page.content()
            if "CloudFlare" in body or "cloudflare" in body.lower():
                print("  !! Cloudflare detected")
            elif "menu" in body.lower() or "price" in body.lower():
                print(f"  Content has menu/price data ({len(body)} bytes)")
        except Exception as e:
            print(f"  Error: {e}")

    for c in api_calls:
        print(f"  API: {c}")


def probe_getir(page, lat, lng, label):
    print(f"\n=== GETIR {label} ===")
    api_calls = []

    def on_response(resp):
        url = resp.url
        if any(k in url for k in ["getir.com", "getirapi"]):
            if any(k in url for k in ["product", "item", "catalog", "categor", "store", "slot", "basket"]):
                try:
                    body = resp.body()
                    if b'"price"' in body or b'"items"' in body or b'"data"' in body:
                        data = json.loads(body)
                        api_calls.append(("RESP+DATA", resp.status, url[:120]))
                        captured["getir"].append({"label": label, "url": url, "data": data})
                except:
                    pass

    page.on("response", on_response)

    endpoints = [
        f"https://getirfood.com/api/categories?latitude={lat}&longitude={lng}",
        f"https://getir.com/api/availability?lat={lat}&lng={lng}",
        f"https://getir.com/pt/groceries/",
        "https://getir.com/pt/",
    ]
    for url in endpoints:
        try:
            r = page.goto(url, wait_until="networkidle", timeout=15000)
            st = r.status if r else "?"
            print(f"  {url[:80]} → {st}")
            time.sleep(2)
            body = page.content()
            if "DataDome" in body or "datadome" in body.lower():
                print("  !! DataDome detected")
            elif "Human Verification" in body:
                print("  !! Human Verification page")
            elif "product" in body.lower() or "price" in body.lower():
                print(f"  Content has product/price data ({len(body)} bytes)")
        except Exception as e:
            print(f"  Error: {e}")

    for c in api_calls:
        print(f"  API: {c}")


if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
                "--lang=pt-PT",
            ]
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            viewport={"width": 390, "height": 844},
            locale="pt-PT",
            timezone_id="Europe/Lisbon",
            geolocation={"latitude": 38.7356, "longitude": -9.1509},
            permissions=["geolocation"],
        )
        page = ctx.new_page()
        stealth_sync(page)

        for label, lat, lng in BOLT_STORES[:1]:
            probe_bolt(page, lat, lng, label)

        for label, lat, lng in GETIR_STORES[:1]:
            probe_getir(page, lat, lng, label)

        browser.close()

    if captured["bolt"]:
        with open("bolt_api_captured.json", "w") as f:
            json.dump(captured["bolt"], f, ensure_ascii=False, indent=2)
        print(f"\n→ Bolt: {len(captured['bolt'])} API responses captured")
    if captured["getir"]:
        with open("getir_api_captured.json", "w") as f:
            json.dump(captured["getir"], f, ensure_ascii=False, indent=2)
        print(f"\n→ Getir: {len(captured['getir'])} API responses captured")
