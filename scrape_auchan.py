"""
Scrape Auchan Portugal for products matching Sortido's catalog.
Uses Playwright (site requires JS). Paginates via start=N&sz=100.
Output: auchan_catalog.json  →  [{name, price, source}]
"""
import json, re, time, random
from playwright.sync_api import sync_playwright
from scrape_supermarkets import KEYWORDS

PAGE_SIZE = 100
DELAY = (2.0, 4.0)

def parse_price(text):
    text = text.replace("\xa0", "").replace(" ", "").replace("€", "").replace(",", ".").strip()
    try:
        return float(text)
    except:
        return None

def scrape_auchan_query(page, query):
    all_products = []
    start = 0
    total = None

    while True:
        url = f"https://www.auchan.pt/pt/pesquisa?q={query.replace(' ', '+')}&sz={PAGE_SIZE}&start={start}"
        try:
            page.goto(url, wait_until="networkidle", timeout=20000)
            page.wait_for_timeout(1500)
        except:
            break

        tiles = page.query_selector_all(".product-tile")
        if not tiles:
            break

        for tile in tiles:
            name_el = tile.query_selector(".pdp-link .link")
            price_el = tile.query_selector(".price .value, .sales .value")
            if not name_el:
                continue
            name = name_el.inner_text().strip()
            price_text = price_el.inner_text().strip() if price_el else ""
            price = parse_price(price_text)
            if name and price:
                all_products.append({
                    "name": name,
                    "price": price,
                    "brand": "",
                    "category": "",
                    "source": "auchan",
                })

        if total is None:
            body = page.inner_text("body")
            m = re.search(r'(\d+)\s+resultado', body)
            total = int(m.group(1)) if m else None

        start += PAGE_SIZE
        if total and start >= total:
            break
        if len(tiles) < PAGE_SIZE:
            break
        time.sleep(random.uniform(*DELAY))

    return all_products


if __name__ == "__main__":
    print(f"Keywords: {len(KEYWORDS)}")

    all_products = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        for i, kw in enumerate(KEYWORDS):
            print(f"[{i+1}/{len(KEYWORDS)}] {kw!r}", end=" ", flush=True)
            products = scrape_auchan_query(page, kw)
            new = 0
            for pr in products:
                key = pr["name"].lower().strip()
                if key not in all_products:
                    all_products[key] = pr
                    new += 1
            print(f"→ {len(products)} resultados, {new} novos (total: {len(all_products)})")
            time.sleep(random.uniform(*DELAY))

        browser.close()

    result = sorted(all_products.values(), key=lambda x: x["name"])
    with open("auchan_catalog.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n→ {len(result)} produtos → auchan_catalog.json")
