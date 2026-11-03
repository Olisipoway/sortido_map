"""
Live per-product search on Continente (curl, no JS needed).
Unlike the keyword catalogs, this queries the competitor site for each Sortido
product, and keeps the pack size ("emb. 16 un") + availability from the tile.

Usage:
    python3 live_search.py "<query>" ["<query2>" ...]        # print results
    from live_search import search_continente, queries_for   # use in scripts
Cache: live_search_cache.json  {query: [ {name, price, brand, category, qty, unit_price, available} ]}
"""
import json, os, re, sys, time, random, urllib.parse
from html import unescape
from scrape_supermarkets import fetch_html

CACHE_FILE = os.environ.get("LIVE_CACHE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_search_cache.json")
_cache = json.load(open(CACHE_FILE)) if os.path.exists(CACHE_FILE) else {}


def _save():
    json.dump(_cache, open(CACHE_FILE, "w"), ensure_ascii=False)


def parse_tiles(html):
    out = []
    for m in re.finditer(r'data-product-tile-impression=\'(\{.*?\})\'', html):
        try:
            d = json.loads(unescape(m.group(1)))
        except Exception:
            continue
        tail = html[m.end(): m.end() + 9000]
        q = re.search(r'pwc-tile--quantity[^>]*>\s*(.*?)\s*<', tail, re.S)
        qty = re.sub(r'\s+', ' ', unescape(q.group(1))).strip() if q else ""
        up = re.search(r'([\d.,]+)\s*€\s*/\s*([a-zA-Z]+)', re.sub(r'<[^>]+>', ' ', tail)[:3000])
        out.append({
            "name": d.get("name", "").strip(),
            "price": float(d["price"]) if d.get("price") not in (None, "") else None,
            "brand": d.get("brand", ""),
            "category": d.get("category", ""),
            "qty": qty,
            "unit_price": f"{up.group(1)}€/{up.group(2)}" if up else "",
            "available": "Indisponível" not in tail[:4000],
            "source": "continente",
        })
    return out


def search_continente(query, use_cache=True):
    if use_cache and query in _cache:
        return _cache[query]
    url = "https://www.continente.pt/pesquisa/?q=" + urllib.parse.quote_plus(query) + "&sz=36"
    res = parse_tiles(fetch_html(url))
    _cache[query] = res
    _save()
    time.sleep(random.uniform(0.6, 1.2))
    return res


_NOISE = re.compile(r'\b(emb\.?|embalagem|pack|un|uni|unid|unidades?|pcs)\b|\(.*?\)|\d+[.,]?\d*\s*(x\s*\d+[.,]?\d*)?\s*(ml|cl|lt|l|gr|g|kg|m|mm|cm|u|un)\b|\b\d{5,}\b', re.I)


def queries_for(name):
    """A few progressively looser queries from a Sortido product name."""
    n = _NOISE.sub(' ', name)
    n = re.sub(r'[^\w\sÀ-ÿ&+-]', ' ', n)
    words = [w for w in n.split() if len(w) > 1]
    qs = []
    if words:
        qs.append(' '.join(words[:6]))
        if len(words) > 3:
            qs.append(' '.join(words[:3]))
    seen, out = set(), []
    for q in qs:
        if q.lower() not in seen:
            seen.add(q.lower()); out.append(q)
    return out


# ---------------- Auchan (curl; tile data in data-gtm JSON, size in name) ----------------
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

def _get(url):
    import subprocess
    return subprocess.run(["curl", "-sL", "-A", _UA, url], capture_output=True, text=True).stdout


def search_auchan(query, use_cache=True):
    key = "auchan::" + query
    if use_cache and key in _cache:
        return _cache[key]
    html = _get("https://www.auchan.pt/pt/pesquisa?q=" + urllib.parse.quote_plus(query) + "&sz=24")
    out = []
    for m in re.finditer(r'data-gtm="(\{.*?\})"\s+data-gtm-new', html):
        try:
            d = json.loads(unescape(m.group(1)))
        except Exception:
            continue
        tail = html[m.end(): m.end() + 6000]
        out.append({"name": d.get("name", "").strip().title() if d.get("name", "").isupper() else d.get("name", "").strip(),
                    "price": float(d["price"]) if d.get("price") else None, "brand": d.get("brand", ""),
                    "category": d.get("category", ""), "qty": "", "unit_price": "",
                    "available": "indispon" not in tail.lower()[:3000], "source": "auchan"})
    _cache[key] = out; _save(); time.sleep(random.uniform(0.6, 1.2))
    return out


# ---------------- Pingo Doce (curl; gtm JSON + weight text in tile) ----------------
def search_pingodoce(query, use_cache=True):
    key = "pingodoce::" + query
    if use_cache and key in _cache:
        return _cache[key]
    html = _get("https://www.pingodoce.pt/on/demandware.store/Sites-pingo-doce-Site/default/Search-Show?q=" + urllib.parse.quote_plus(query))
    items = []
    for blk in re.findall(r'data-gtm-info="(\{.*?\})"', html, re.S):
        try:
            items += json.loads(unescape(blk)).get("items", [])
        except Exception:
            pass
    text = re.sub(r'<script.*?</script>|<svg.*?</svg>|<style.*?</style>', '', html, flags=re.S)
    text = unescape(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' | ', text)))
    out = []
    for it in items:
        nm = it.get("item_name", "").strip()
        qty = ""
        i = text.find(nm + " | ")
        if i < 0:
            i = text.find(nm)
        if i >= 0:
            q = re.search(r'([\d.,]+)\s*\|?\s*(Kg|kg|L|l|Un|un)\b', text[i + len(nm): i + len(nm) + 160])
            if q:
                qty = f"{q.group(1)} {q.group(2)}"
        out.append({"name": nm, "price": it.get("price"), "brand": it.get("item_brand", ""),
                    "category": it.get("item_category2", ""), "qty": qty, "unit_price": "",
                    "available": True, "source": "pingodoce"})
    _cache[key] = out; _save(); time.sleep(random.uniform(0.6, 1.2))
    return out


if __name__ == '__main__':
    for q in sys.argv[1:]:
        print('##', q)
        for r in search_continente(q)+search_auchan(q)+search_pingodoce(q):
            print(f"  {r['source'][:4]} {r['price']!s:>6} {r['qty']:<12} {r['unit_price']:<12} {'' if r['available'] else '[indisp] '}{r['name']}")
