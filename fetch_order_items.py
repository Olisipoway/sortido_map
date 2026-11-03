"""
Fetch item-level data for a sample of UberEats orders.
Outputs order_items.json  →  [{orderId, items:[{name,price,qty}]}]
Then builds item_categories.json  →  [{category, count, revenue, pct}]
"""
import subprocess, json, time, random, os, re

# --- import from ubereats_orders.py ---
from ubereats_orders import COOKIES, STORE_UUID, ORDER_DETAIL_QUERY
API_URL = "https://merchants.ubereats.com/manager/graphql"

ITEMS_FILE  = "order_items.json"
SAMPLE_SIZE = 500

CATEGORIES = [
    ("Álcool — Cerveja",    r'\bcerve[jg]|super bock|sagres|heineken|stella|corona|imperial|NOS\b'),
    ("Álcool — Vinho",      r'\bvinho|wine|tinto|branco|rosé|rose\b'),
    ("Álcool — Cocktails",  r'\bcocktail|gin|vodka|rum|whisky|caipirinha|tónico|aperol|spritz\b'),
    ("Álcool — Shots",      r'\bshot|licor|porto|moscatel\b'),
    ("Bebidas s/ álcool",   r'\bágua|agua|sumo|juice|refrigerante|coca.cola|pepsi|limonada|ice tea|iced tea|kombucha|7up|sprite\b'),
    ("Pizza",               r'\bpizza\b'),
    ("Hambúrgueres",        r'\bburger|hambúrguer|hamburger\b'),
    ("Snacks / Entradas",   r'\bsnack|batatas|fritas|nachos|bruschetta|entrada|tostas?|tosta\b'),
    ("Sobremesas",          r'\bsobremes|gelado|brownie|cheesecake|mousse|tiramisu|crepe\b'),
    ("Outros pratos",       r'.*'),  # catch-all
]

def gql(operation, query, variables):
    payload = json.dumps({"operationName": operation, "query": query, "variables": variables})
    r = subprocess.run(
        ["curl", "--silent", API_URL + f"?op={operation}",
         "-H", "accept: */*", "-H", "content-type: application/json",
         "-H", "origin: https://merchants.ubereats.com",
         "-H", f"referer: https://merchants.ubereats.com/manager/orders?restaurantUUID={STORE_UUID}",
         "-H", "x-csrf-token: x",
         "-b", COOKIES, "--data-raw", payload],
        capture_output=True, text=True
    )
    try: return json.loads(r.stdout)
    except: return None

def get_items(workflow_uuid):
    while True:
        data = gql("OrderDetails", ORDER_DETAIL_QUERY, {
            "workflowUUID": workflow_uuid,
            "detailsRequestedByRestaurantUUID": STORE_UUID,
            "metadata": {"isEatsPassSubscriber": False, "locale": "en"},
            "shouldEnableChargebackComms": True,
        })
        if not data: return None
        if "errors" in data:
            msg = data["errors"][0].get("message", "")
            if "rate" in msg.lower():
                print(" [rate limit 60s]", end="", flush=True)
                time.sleep(60); continue
            return None
        detail = (data.get("data") or {}).get("orderDetails")
        if not detail: return None
        return detail.get("items", [])

def categorise(name):
    n = name.lower()
    for cat, pattern in CATEGORIES:
        if re.search(pattern, n, re.IGNORECASE):
            return cat
    return "Outros pratos"

if __name__ == "__main__":
    # Load order list
    orders = json.load(open("ubereats_orders_list.json"))
    print(f"Total orders: {len(orders)}")

    # Load existing results
    done = {}
    if os.path.exists(ITEMS_FILE):
        done = {r["orderId"]: r for r in json.load(open(ITEMS_FILE))}
        print(f"Already fetched: {len(done)}")

    # Sample
    remaining = [o for o in orders if o["orderId"] not in done]
    sample = random.sample(remaining, min(SAMPLE_SIZE - len(done), len(remaining)))
    print(f"Fetching {len(sample)} orders…")

    results = list(done.values())
    for i, order in enumerate(sample):
        oid = order["orderId"]
        wid = order.get("workflowUuid")
        print(f"[{i+1}/{len(sample)}] {oid}", end=" ", flush=True)
        items = get_items(wid)
        if items is None:
            print("— skip"); continue
        def parse_price(p):
            try: return float(str(p).replace("€","").strip())
            except: return 0.0
        parsed = [{"name": it["name"], "price": parse_price(it.get("price",0)), "qty": it.get("quantity",1)}
                  for it in items if it.get("name")]
        results.append({"orderId": oid, "items": parsed})
        print(f"— {len(parsed)} items: {', '.join(p['name'] for p in parsed[:3])}")
        with open(ITEMS_FILE, "w") as f:
            json.dump(results, f, ensure_ascii=False)
        if (i + 1) % 25 == 0:
            pause = random.uniform(30, 60)
            print(f"  [pause {pause:.0f}s]")
            time.sleep(pause)
        else:
            time.sleep(random.uniform(3, 6))

    # --- Build category summary ---
    print(f"\nBuilding category summary from {len(results)} orders…")
    cat_count, cat_rev = {}, {}
    total_items = 0
    for order in results:
        for item in order.get("items", []):
            cat = categorise(item["name"])
            qty = item.get("qty", 1)
            rev = item.get("price", 0) * qty
            cat_count[cat] = cat_count.get(cat, 0) + qty
            cat_rev[cat]   = cat_rev.get(cat, 0) + rev
            total_items   += qty

    summary = sorted([
        {"category": c, "count": cat_count[c], "revenue": round(cat_rev[c], 2),
         "pct": round(cat_count[c] / total_items * 100, 1)}
        for c in cat_count
    ], key=lambda x: -x["count"])

    with open("item_categories.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\nCategory breakdown:")
    for row in summary:
        print(f"  {row['category']:<30} {row['pct']:5.1f}%  {row['count']:4d} items  €{row['revenue']:.0f}")
    print(f"\n→ item_categories.json")
