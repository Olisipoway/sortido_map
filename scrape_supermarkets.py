"""
Scrape Continente (and others) for products matching Sortido's catalog.
Uses the search API — one request per keyword, paginated.
Output: continente_catalog.json  →  [{name, price, brand, category, source}]
"""
import subprocess, json, re, time, random
from html import unescape
from collections import defaultdict

PAGE_SIZE = 36
DELAY     = (1.5, 3.0)

# --- Continente helpers ---

def fetch_html(url):
    r = subprocess.run(
        ["curl", "-sL", url,
         "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
         "-H", "accept-language: pt-PT,pt;q=0.9",
         "-H", "accept: text/html,application/xhtml+xml"],
        capture_output=True, text=True
    )
    return r.stdout

def parse_products(html):
    matches = re.findall(r'data-product[^=]*=["\'](.*?)["\'](?:\s|>)', html)
    products = []
    for m in matches:
        try:
            obj = json.loads(unescape(m))
            if isinstance(obj, dict) and obj.get("name") and obj.get("price"):
                products.append({
                    "name":     obj["name"].strip(),
                    "price":    float(obj["price"]),
                    "brand":    obj.get("brand", ""),
                    "category": obj.get("category", ""),
                    "source":   "continente",
                })
        except:
            pass
    return products

def get_total(html):
    m = re.search(r'(\d+)\s+de\s+(\d+)', html)
    return int(m.group(2)) if m else None

def scrape_continente_query(query):
    """Fetch all pages for a search query."""
    base = f"https://www.continente.pt/pesquisa/?q={query.replace(' ', '+')}&sz={PAGE_SIZE}"
    all_products = []
    start = 0
    total = None

    while True:
        url = base + (f"&start={start}" if start else "")
        html = fetch_html(url)
        page_products = parse_products(html)
        all_products.extend(page_products)

        if total is None:
            total = get_total(html)
        if not page_products:
            break
        start += PAGE_SIZE
        if total and start >= total:
            break
        time.sleep(random.uniform(*DELAY))

    return all_products

# --- Build keyword list from Sortido catalog ---

def extract_keywords(catalog):
    """Extract searchable terms from Sortido product names."""
    seen = set()
    keywords = []

    BRAND_RE = re.compile(
        r'\b(super bock|sagres|heineken|corona|carlsberg|estrella|guinness|'
        r'coca.cola|pepsi|sprite|fanta|7up|schweppes|monster|red bull|'
        r'luso|pedras salgadas|san pellegrino|perrier|vitalis|monchique|'
        r'compal|sumol|tropicana|'
        r'porto cruz|casal garcia|quinta|herdade|'
        r'vinho verde|vinho tinto|vinho branco|'
        r'gin|vodka|rum|whisky|whiskey|tequila|baileys|'
        r'nestlé|danone|activia|president|lurpak|'
        r'durex|'
        r'renova|tempo|scottex)\b',
        re.IGNORECASE
    )

    SIZE_RE = re.compile(r'\b\d+[,.]?\d*\s*(?:l|lt|litro|ml|cl|g|gr|kg|un|x\s*\d+)\b', re.IGNORECASE)

    for item in catalog:
        name = item["name"]
        # Extract brand matches
        for m in BRAND_RE.finditer(name):
            brand = m.group(0).lower().strip()
            if brand not in seen:
                seen.add(brand)
                keywords.append(brand)
        # Also add first 2 meaningful words as fallback for uncategorised
        words = [w for w in re.split(r'\s+', name) if len(w) > 3 and not SIZE_RE.match(w)]
        key = " ".join(words[:2]).lower()
        if key and key not in seen:
            seen.add(key)
            keywords.append(key)

    return keywords


KEYWORDS = [
    # Cervejas
    "super bock", "sagres", "heineken", "corona cerveja", "carlsberg", "estrella damm",
    "guinness", "1664", "budweiser", "cider sidra",
    # Águas
    "agua luso", "pedras salgadas", "san pellegrino", "perrier", "monchique",
    "evian", "vitalis", "agua mineral",
    # Refrigerantes
    "coca-cola", "pepsi", "sprite", "fanta", "7up", "schweppes tonica",
    "monster energy", "red bull", "ice tea",
    # Sumos
    "compal", "sumol", "tropicana", "bom dia",
    # Vinhos
    "vinho tinto", "vinho branco", "vinho verde", "vinho rosé",
    # Spirits
    "gin", "vodka", "rum", "whisky", "tequila", "baileys",
    # Laticínios
    "leite", "queijo", "iogurte", "manteiga", "natas", "ovos",
    # Fruta & Legumes
    "banana", "limao", "laranja",
    # Snacks & Outros
    "batatas fritas snack", "chocolate tablete", "gelo cubos",
    "preservativos durex", "papel higienico renova",
]

if __name__ == "__main__":
    print(f"Keywords: {len(KEYWORDS)}")
    print()

    all_products = {}  # dedup by name

    for i, kw in enumerate(KEYWORDS):
        print(f"[{i+1}/{len(KEYWORDS)}] {kw!r}", end=" ", flush=True)
        products = scrape_continente_query(kw)
        new = 0
        for p in products:
            key = p["name"].lower().strip()
            if key not in all_products:
                all_products[key] = p
                new += 1
        print(f"→ {len(products)} resultados, {new} novos (total: {len(all_products)})")
        time.sleep(random.uniform(*DELAY))

    result = sorted(all_products.values(), key=lambda x: x["name"])
    with open("continente_catalog.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n→ {len(result)} produtos → continente_catalog.json")
