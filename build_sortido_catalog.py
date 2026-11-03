"""
Build sortido_catalog.json from order_items.json.
Normalizes deal bundles ("Leve 2 Poupe X%") and deduplicates by clean name.
Output: [{name, price, orders, category}]
"""
import json, re, statistics
from collections import defaultdict

DEAL_RE = re.compile(
    r'^(?:leve\s+(\d+)\s+(?:pague\s+\d+|poupe\s+\d+%?)\s*[-–]\s*)',
    re.IGNORECASE
)

def parse_name(raw_name):
    """Strip deal prefix and return (clean_name, deal_units)."""
    m = DEAL_RE.match(raw_name.strip())
    if m:
        deal_units = int(m.group(1))
        clean = raw_name[m.end():].strip()
    else:
        deal_units = 1
        clean = raw_name.strip()
    # Normalise trailing " sdr" (abreviação de "sem desconto recorrente")
    clean = re.sub(r'\s+sdr$', '', clean, flags=re.IGNORECASE).strip()
    return clean, deal_units

CATEGORIES = [
    ("Álcool — Cerveja",   r'\b(cerve[jg]a?|super bock|sagres|heineken|stella|corona|imperial|nos lata|nossas|1664|budweiser|cider)\b'),
    ("Álcool — Vinho",     r'\bvinho\b|vinho\s+(tinto|branco|rosé|rose|verde)|\b(prosecco|cava|champagne|espumante)\b'),
    ("Álcool — Spirits",   r'\b(gin|vodka|rum|whisky|whiskey|tequila|brandy|cognac|porto|moscatel|licor|shots?|baileys|amaretto)\b'),
    ("Bebidas s/ álcool",  r'\b(água|agua|sumo|néctar|nectar|juice|refrigerante|coca.cola|pepsi|limonada|ice tea|iced tea|kombucha|7up|sprite|fanta|tónico|tonico|gatorade|monster|red bull)\b'),
    ("Fruta & Legumes",    r'\b(banana|limão|limao|laranja|maçã|maca|tomate|pepino|alface|cenoura|batata|cebola|alho|pimento|morango|uva|melancia|manga|abacaxi|courgette|beterraba|espinafre|rucula)\b'),
    ("Laticínios & Ovos",  r'\b(leite|queijo|iogurte|manteiga|nata|ovos?|ovo|cream cheese|requeijão)\b'),
    ("Charcutaria",        r'\b(presunto|fiambre|salame|chouriço|mortadela|bacon|salpicão|paio|alheira|morcela)\b'),
    ("Snacks / Salgados",  r'\b(snack|batatas fritas|nachos|chips|amendoim|pipocas|rissol|croquete|tosta)\b'),
    ("Sobremesas / Doces", r'\b(chocolate|gelado|brownie|cheesecake|mousse|crepe|bolo|biscoito|bolacha|rebuçado|gomas|candy)\b'),
    ("Mercearia",          r'\b(massa|arroz|feijão|grão|azeite|óleo|vinagre|molho|ketchup|maionese|mostarda|sal|açúcar|farinha|café|chá|mel|compota|atum|sardinha|conserva)\b'),
    ("Higiene / Beleza",   r'\b(preservativo|durex|shampoo|gel|desodorizante|creme|pasta.*dentes|escova|sabonete|papel.*higiénico|absorvente)\b'),
    ("Gelo & Outros",      r'\b(gelo|ice cubers)\b'),
]

def categorise(name):
    n = name.lower()
    for cat, pat in CATEGORIES:
        if re.search(pat, n, re.IGNORECASE):
            return cat
    return "Outros"


orders = json.load(open("order_items.json"))

# Aggregate by clean name
agg = defaultdict(list)
for order in orders:
    for item in order.get("items", []):
        raw = item.get("name", "").strip()
        qty = item.get("qty", 1) or 1
        price_total = item.get("price", 0) or 0
        if not raw or price_total <= 0:
            continue
        clean, deal_units = parse_name(raw)
        unit_price = round(price_total / (qty * deal_units), 2)
        agg[clean].append(unit_price)

catalog = []
for name, prices in agg.items():
    catalog.append({
        "name": name,
        "price": round(statistics.median(prices), 2),
        "orders": len(prices),
        "category": categorise(name),
    })

catalog.sort(key=lambda x: -x["orders"])

with open("sortido_catalog.json", "w", encoding="utf-8") as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)

print(f"Total produtos únicos: {len(catalog)}")
print("\nTop 30 mais pedidos:")
for c in catalog[:30]:
    print(f"  {c['name']:<50} €{c['price']:.2f}  [{c['category']}]  ({c['orders']} pedidos)")

print("\nPor categoria:")
from collections import Counter
cats = Counter(c["category"] for c in catalog)
for cat, n in cats.most_common():
    print(f"  {cat:<30} {n} produtos")

print(f"\n→ sortido_catalog.json")
