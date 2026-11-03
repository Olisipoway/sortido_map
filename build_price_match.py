"""
Match Sortido products against Continente + Auchan catalogs.
Uses brand + size + product-type normalization for fuzzy matching.
Output: matched_prices.json  →  [{name, sortido, continente, auchan, glovo, category}]
"""
import json, re
from collections import defaultdict

# --- Pack info extraction: returns (pack_units, unit_size_liters) ---
def extract_pack_info(name):
    n = name.lower()
    # "NxVol/Weight" patterns
    for pat, unit_div in [
        (r'(\d+)\s*[x×]\s*(\d+[.,]?\d*)\s*lt?\b',  1),
        (r'(\d+)\s*[x×]\s*(\d+[.,]?\d*)\s*litros?\b', 1),
        (r'(\d+)\s*[x×]\s*(\d+[.,]?\d*)\s*cl\b', 100),
        (r'(\d+)\s*[x×]\s*(\d+[.,]?\d*)\s*ml\b', 1000),
        (r'(\d+)\s*[x×]\s*(\d+[.,]?\d*)\s*kg\b',  1),
        (r'(\d+)\s*[x×]\s*(\d+[.,]?\d*)\s*gr?\b',  1000),
    ]:
        m = re.search(pat, n)
        if m:
            pack = int(m.group(1))
            size = float(m.group(2).replace(',','.')) / unit_div
            return pack, round(size, 4)
    # "N unidades/embalagens ... Vol" — e.g. "Pack 6 unidades garrafa 20 cl"
    m_pack = re.search(r'(\d+)\s*(?:un(?:idades?)?\b|embalagens?\b)', n)
    if m_pack:
        for vol_pat, unit_div in [
            (r'(\d+[.,]?\d*)\s*litros?\b', 1),
            (r'(\d+[.,]?\d*)\s*lt?\b',     1),
            (r'(\d+[.,]?\d*)\s*cl\b',      100),
            (r'(\d+[.,]?\d*)\s*ml\b',      1000),
        ]:
            m_vol = re.search(vol_pat, n)
            if m_vol:
                return int(m_pack.group(1)), round(float(m_vol.group(1).replace(',','.')) / unit_div, 4)
    # Single unit
    for pat, unit_div in [
        (r'(\d+[.,]?\d*)\s*lt?\b',  1),
        (r'(\d+[.,]?\d*)\s*litros?\b', 1),
        (r'(\d+[.,]?\d*)\s*cl\b',   100),
        (r'(\d+[.,]?\d*)\s*ml\b',   1000),
    ]:
        m = re.search(pat, n)
        if m:
            return 1, round(float(m.group(1).replace(',','.')) / unit_div, 4)
    # Special cases
    if re.search(r'garraf[aã]o', n): return 1, 5.0
    for pat, val in [(r'meia d[uú]zia', 6), (r'\bd[uú]zia\b', 12)]:
        if re.search(pat, n): return val, None
    m = re.search(r'(\d+)\s*un\b', n)
    if m: return int(m.group(1)), None
    # weight
    m = re.search(r'(\d+[.,]?\d*)\s*kg\b', n)
    if m: return 1, float(m.group(1).replace(',','.'))
    m = re.search(r'(\d+[.,]?\d*)\s*gr?\b', n)
    if m: return 1, round(float(m.group(1).replace(',','.')) / 1000, 4)
    return 1, None

def extract_size(name):
    _, size = extract_pack_info(name)
    return size

BRANDS = [
    "super bock", "sagres", "heineken", "corona", "carlsberg", "estrella", "guinness",
    "1664", "budweiser", "bandida", "imperial",
    "luso", "pedras salgadas", "san pellegrino", "perrier", "monchique", "evian", "vitalis",
    "carvalhelhos", "fastio", "contrex", "penacova", "nascente", "volvic",
    "coca.cola", "coca cola", "pepsi", "sprite", "fanta", "7up", "schweppes",
    "monster", "red bull", "ice tea",
    "compal", "sumol", "tropicana", "bom dia",
    "porto cruz", "planalto", "monte velho", "herdade do peso", "herdade dos grous",
    "casal garcia", "mateus",
    # Porto wine brands — must come before generic terms; "porto" and "vinho verde" removed (too generic)
    "velhotes", "ferreira", "ramos pinto", "sandeman", "calem", "graham", "niepoort",
    "quinta do crasto", "quinta dos quatro ventos", "palácio da brejoeira", "deu la deu",
    "muralhas",
    # spirits — actual brand names only (not the spirit type itself)
    "baileys", "absolut", "smirnoff", "bacardi", "havana", "captain morgan",
    "hendricks", "tanqueray", "gordons", "gordon", "bombay", "beefeater",
    "jameson", "jack daniel", "johnnie walker", "chivas", "ballantines", "glen",
    "eristoff", "ciroc", "grey goose", "rodanov", "moskovskaya", "ketel one",
    "bosford", "sharish", "bulldog", "g'vine", "gin mare", "monkey 47",
    "jose cuervo", "sierra tequila", "patron",
    "bushmills", "grants", "grant", "famous grouse", "cutty sark", "william lawson", "old parr", "buchanan",
    "nestlé", "nestle", "danone", "activia", "president", "lurpak", "anchor",
    "mimosa", "baldio", "campina", "philadelphia",
    "castello",                                   # Agua Castello brand
    "durex", "renova", "tempo", "scottex",
    "magnum", "häagen", "ben & jerry",
    "gourmet ice", "kitkat", "kit kat",
    "maltesers", "m&m", "twix", "snickers", "bounty", "milky way",
]

# Generic product types: brand is irrelevant, lower matching threshold applies.
# Two tiers: 50 for fully commoditized (eggs, ice), 55 for differentiated-but-generic (queijo).
# NOTE: "leite" and "iogurte" are intentionally excluded — they're usually branded (Mimosa,
# Danone, etc.) and "leite" also appears in "chocolate de leite", causing false positives.
GENERIC_TYPES_50 = {"ovos", "gelo"}
GENERIC_TYPES_55 = {"queijo", "manteiga"}

# Product types — spirits use the type name, not a brand
SPIRIT_TYPES = {"gin", "vodka", "rum", "whisky", "tequila"}

def extract_brand(name):
    n = name.lower()
    for brand in BRANDS:
        if brand in n:
            return brand.replace(".", "")
    return None

PRODUCT_TYPES = [
    ("cerveja",      r'\bcerve[jg]'),
    ("agua",         r'\bágua|agua\b'),
    ("refrigerante", r'\brefrigerante|coca.cola|pepsi|sprite|fanta|7up'),
    ("vinho",        r'\bvinho\b'),
    ("gin",          r'\bgin\b'),
    ("vodka",        r'\bvodka\b'),
    ("rum",          r'\brum\b'),
    ("whisky",       r'\bwhisk[ye]\b'),
    ("tequila",      r'\btequila\b'),
    ("sumo",         r'\bnéctar|nectar|sumo|compal|sumol\b'),
    ("leite",        r'\bleite\b'),
    ("queijo",       r'\bqueijo\b'),
    ("iogurte",      r'\biogurte\b'),
    ("ovos",         r'\bovos?\b'),
    ("manteiga",     r'\bmanteiga\b'),
    ("gelado",       r'\bgelado\b'),
    ("chocolate",    r'\bchocolate\b'),
    ("batatas",      r'\bbatatas fritas\b'),
    ("preservativo", r'\bpreservativ'),
    ("papel",        r'\bpapel.higi'),
    ("gelo",         r'\bgelo\b'),
]

def extract_type(name):
    n = name.lower()
    for ptype, pattern in PRODUCT_TYPES:
        if re.search(pattern, n, re.IGNORECASE):
            return ptype
    return "outro"

def is_zero_alcohol(name):
    n = name.lower()
    return bool(re.search(r'sem [aá]lcool|0[,\.]0\s*%|s/[aá]lcool|alcohol.free|non.alc', n))

def normalize(name):
    brand = extract_brand(name)
    size  = extract_size(name)
    ptype = extract_type(name)
    return brand, size, ptype

def token_overlap(a, b):
    """Fraction of tokens in a that also appear in b."""
    STOP = {"com", "de", "e", "em", "a", "o", "da", "do", "das", "dos", "sem", "para", "um", "uma"}
    def _norm(s):
        s = s.lower()
        # Split digit-letter and letter-digit boundaries so "2Kg" == "2 kg", "33cl" == "33 cl"
        s = re.sub(r'(\d)([a-z])', r'\1 \2', s)
        s = re.sub(r'([a-z])(\d)', r'\1 \2', s)
        return s
    ta = set(re.findall(r'\w+', _norm(a))) - STOP
    tb = set(re.findall(r'\w+', _norm(b))) - STOP
    if not ta:
        return 0
    return len(ta & tb) / len(ta)

# Hard-rejection keywords: competitor product contains these but sortido product doesn't
REJECT_WORDS = [
    "barril", "balde", "sidra", "cerveja artesanal", "sem glúten", "sem gluten",
    "caixa", "eco pack",
    "bohemia", "abadia", "mini",   # specific beer variants
    "fruta",                       # flavored water ≠ mineral water
    "júnior",                      # kids' bottle format
    "coruja", "sky",               # Super Bock craft sub-brands
    "mista", "preta",              # Sagres variants (blend, dark)
    "india pale ale", "stout",     # craft styles ≠ lager
    "1927", "weiss", "ruiva",              # Super Bock premium/craft sub-brands
    "açúcarado",                           # sweetened ≠ plain (e.g. Oikos)
    "zero", "light", "pink", "tropical",  # diet/flavored variants
    "hibiscus", "premium mix",            # flavored tonic variants
    "pull off",                            # Super Bock special can format
    # fruit flavors: reject flavored water/tonic when sortido product is plain
    "ananás", "limão", "lima", "açaí", "maracujá", "tangerina", "morango",
    "manga", "toranja", "melancia", "frutos vermelhos", "levíssima",
    "laranja", "pêssego", "pêra",  # additional fruit flavors
    # energy drink / soft drink variants
    "sem açúcar",                # sugar-free ≠ regular
    "edition",                   # limited-edition flavors (Red Bull, etc.)
    "radler",                    # beer+lemonade blend ≠ regular beer
    "re-hab",                    # Monster Re-Hab variant ≠ Monster Energy
    "uva",                       # grape Fanta ≠ orange Fanta
    "guaraná",                   # guaraná Fanta ≠ other Fanta
    "fuze",                      # Fuze Tea brand ≠ Lipton
    "hibisco",                   # hibiscus-flavor ice tea ≠ plain
    "côco",                      # coconut-blend Compal (Vital) ≠ plain nectar
    "alperce",                   # apricot nectar ≠ passion fruit / pineapple
    "espumante", "brut",         # sparkling wine ≠ still wine
    "meio gordo", "magro",       # semi-skimmed / skimmed milk ≠ full-fat or chocolate
    "gordo",                     # full-fat milk variant specifier
    "fitness",                   # Nestlé Fitness cereal bars ≠ KitKat (also in BIDIRECTIONAL_REJECT)
    "amanhecer",                 # Continente private label ≠ branded products
    "energetica", "energética",  # energy drinks ≠ sparkling water / other beverages
    "burn",                      # Burn energy drink brand ≠ sparkling water
    "proteico", "proteína",      # protein milk ≠ regular/chocolate milk
    "bolonhesa", "caril", "chili",  # prepared meal sauces ≠ plain canned legumes (Compal da Horta)
    "red label", "red soul",     # Johnnie Walker Red ≠ Black Label
    "double black",              # JW Double Black ≠ Black Label
    "no. ten", "no ten",         # Tanqueray No. Ten (premium) ≠ London Dry
    "descafeinado", "decaf",     # decaf ≠ regular coffee
    "pilsner", "brune", "dunkel",  # craft/specialty beer styles ≠ standard lager
    "blackberry", "framboesa",   # flavored cider/drinks ≠ plain
]

# Words that must match symmetrically: reject if one product has the word and the other doesn't.
BIDIRECTIONAL_REJECT = {
    "fitness",  # Fitness cereal bars ≠ regular chocolate bars (e.g. Nestlé Fitness vs Choco Trio)
    "noite",    # night cream ≠ day cream
}

def match_score(s_brand, s_size, s_type, c_brand, c_size, c_type, s_name="", c_name=""):
    """Returns score 0-100, or -1 for hard rejection."""
    s_lower = s_name.lower()
    c_lower = c_name.lower()

    # Hard reject: beer alcohol-free vs regular mismatch
    if s_type == "cerveja" or c_type == "cerveja":
        if is_zero_alcohol(s_name) != is_zero_alcohol(c_name):
            return -1

    # Hard reject: competitor contains disqualifying keywords sortido doesn't
    for word in REJECT_WORDS:
        if word in c_lower and word not in s_lower:
            return -1

    # Hard reject: words that must appear on both sides or neither (bidirectional)
    for word in BIDIRECTIONAL_REJECT:
        if (word in s_lower) != (word in c_lower):
            return -1

    # Hard reject: bundle product with " & " separator (e.g. "Heineken 6x25cl & KitKat")
    if " & " in c_name and " & " not in s_name:
        return -1

    # Hard reject: water brand mismatch (Castello ≠ San Pellegrino ≠ Luso — very different price tiers)
    if s_type == "agua" and c_type == "agua" and s_brand and c_brand and s_brand != c_brand:
        return -1

    # Hard reject: gluten-free / varietal mismatch (don't match Daura to regular Estrella)
    if re.search(r'sem glút|gluten.free|daura\b', c_lower) and not re.search(r'sem glút|gluten.free|daura\b', s_lower):
        return -1

    # Hard reject: spirit types require brand match
    if s_type in SPIRIT_TYPES or c_type in SPIRIT_TYPES:
        if s_brand != c_brand:
            return -1
        # Hard reject: spirit age mismatch (e.g. Havana 3 Anos vs Havana 7 Anos)
        s_age = re.search(r'(\d+)\s*anos?\b', s_lower)
        c_age = re.search(r'(\d+)\s*anos?\b', c_lower)
        if s_age and c_age and s_age.group(1) != c_age.group(1):
            return -1

    # Hard reject: salt / lactose content mismatch (sem sal ≠ com sal; sem lactose ≠ regular)
    for attr_pat in [r'\bsem sal\b', r'\bsem lactose\b']:
        if bool(re.search(attr_pat, s_lower)) != bool(re.search(attr_pat, c_lower)):
            return -1

    # Hard reject: cheese variety mismatch (manchego ≠ azeitão ≠ brie ≠ mistura)
    if s_type == "queijo" and c_type == "queijo":
        CHEESE_VARIETIES = [
            "manchego", "azeitão", "brie", "camembert", "gouda", "edam", "parmesão",
            "emmental", "gorgonzola", "roquefort", "cheddar", "ricotta",
            "mozzarella", "mozarella", "flamengo", "mistura", "creme",
        ]
        s_var = next((v for v in CHEESE_VARIETIES if v in s_lower), None)
        c_var = next((v for v in CHEESE_VARIETIES if v in c_lower), None)
        if s_var and c_var and s_var != c_var:
            # mozzarella / mozarella spelling variants are the same cheese
            moz_variants = {"mozzarella", "mozarella"}
            if not (s_var in moz_variants and c_var in moz_variants):
                return -1

    # Hard reject: wine color mismatch (tinto / branco / rosé)
    if s_type == "vinho" and c_type == "vinho":
        wine_colors = ["tinto", "branco", "rosé", "rosado"]
        s_color = next((c for c in wine_colors if c in s_lower), None)
        c_color = next((c for c in wine_colors if c in c_lower), None)
        if s_color and c_color and s_color != c_color:
            return -1
        # Hard reject: different "herdade" estate names (e.g. Herdade do Peso ≠ Herdade dos Grous)
        s_est = re.search(r'\bherdade\s+\w+\s+(\w+)', s_lower)
        c_est = re.search(r'\bherdade\s+\w+\s+(\w+)', c_lower)
        if s_est and c_est and s_est.group(1) != c_est.group(1):
            return -1

    # Hard reject: bundle product (contains "+") but sortido product is single
    if "+" in c_name and "+" not in s_name:
        return -1

    # Hard reject: size too different (ratio < 0.80)
    if s_size and c_size:
        ratio = min(s_size, c_size) / max(s_size, c_size)
        if ratio < 0.80:
            return -1

    score = 0
    if s_brand and s_brand == c_brand:
        score += 40
    elif s_brand and c_brand and (s_brand in c_brand or c_brand in s_brand):
        score += 25
    if s_type == c_type:
        score += 25
    if s_size and c_size:
        ratio = min(s_size, c_size) / max(s_size, c_size)
        if ratio > 0.97:
            score += 20
        elif ratio > 0.87:
            score += 8
    if s_name and c_name:
        score += int(token_overlap(s_name, c_name) * 15)
    return score


def find_best_match(sortido_item, catalog, threshold=70):
    s_brand, s_size, s_type = normalize(sortido_item["name"])
    s_pack, s_unit_size = extract_pack_info(sortido_item["name"])
    best_score = 0
    best = None
    best_equiv_price = None
    best_c_pack = None
    best_c_unit_size = None

    for item in catalog:
        c_brand, c_size, c_type = normalize(item["name"])
        c_pack, c_unit_size = extract_pack_info(item["name"])

        sc = match_score(s_brand, s_unit_size, s_type, c_brand, c_unit_size, c_type,
                         sortido_item["name"], item["name"])
        if sc < 0:
            continue  # hard rejection

        # Bonus for exact pack count match (prefers 6×33cl vs 6×33cl over 6×33cl vs single 33cl)
        if s_pack > 1 and c_pack == s_pack:
            sc += 15

        # For multi-pack sortido, skip competitor single-unit prices that are implausibly cheap
        # (catches "Heineken single can €1.39" matching against "Heineken 6x25cl €8.19")
        if s_pack > 1 and c_unit_size is None and c_pack <= 1:
            if item["price"] < sortido_item["price"] * 0.3:
                continue

        if sc > best_score:
            best_score = sc
            best = item
            best_c_pack = c_pack
            best_c_unit_size = c_unit_size
            if c_unit_size is not None:
                # Volume confirmed — divide by competitor pack count, scale to sortido pack count
                c_unit_price = item["price"] / c_pack if c_pack > 1 else item["price"]
                best_equiv_price = round(c_unit_price * s_pack, 2)
            elif c_pack > 1:
                # Explicit pack count but no volume (e.g. condoms "10 un") — scale by count
                best_equiv_price = round((item["price"] / c_pack) * s_pack, 2)
            else:
                # No unit info on competitor side — show raw, don't inflate
                best_equiv_price = round(item["price"], 2)

    # For commodity types, brand is not a differentiator — lower threshold.
    effective_threshold = threshold
    if s_type in GENERIC_TYPES_50:
        effective_threshold = 50
    elif s_type in GENERIC_TYPES_55:
        effective_threshold = 55

    # When sortido has no size but competitor does, reject if price ratio is implausible.
    # (Prevents e.g. matching Maltesers unknown-size vs Bolt 300g 8.29€ at 4.9x ratio.)
    if best_equiv_price is not None and s_unit_size is None and best_c_unit_size is not None:
        ratio_check = best_equiv_price / sortido_item["price"]
        if ratio_check < 0.30 or ratio_check > 2.5:
            return None, best_score, None

    if best_score >= effective_threshold:
        ratio = best_equiv_price / sortido_item["price"]
        # When no volume info on competitor side, require price to be in a plausible range
        if best_c_unit_size is None:
            if ratio < 0.40 or ratio > 2.0:
                return None, best_score, None
        # Universal backstop for extreme cases regardless of unit info
        if ratio < 0.15:
            return None, best_score, None
        return best, best_score, best_equiv_price
    return None, best_score, None


if __name__ == "__main__":
    sortido   = json.load(open("sortido_catalog.json"))
    continente = json.load(open("continente_catalog.json"))

    auchan = []
    try:
        auchan = json.load(open("auchan_catalog.json"))
    except:
        print("auchan_catalog.json not ready yet - skipping")

    glovo = json.load(open("glovo_lis1_catalog.json"))
    for g in glovo:
        g["source"] = "glovo"

    bolt = []
    try:
        bolt = json.load(open("bolt_catalog.json"))
    except:
        print("bolt_catalog.json not ready yet - skipping")

    print(f"Sortido: {len(sortido)} | Continente: {len(continente)} | Auchan: {len(auchan)} | Glovo: {len(glovo)} | Bolt: {len(bolt)}")

    def _match_and_append(match_item, row, results):
        cont_match, cont_score, cont_unit = find_best_match(match_item, continente)
        if cont_match:
            p = cont_unit or cont_match["price"]
            if p >= 0.10:
                row["continente"] = p
                row["continente_name"] = cont_match["name"]
        if auchan:
            auch_match, auch_score, auch_unit = find_best_match(match_item, auchan)
            if auch_match:
                p = auch_unit or auch_match["price"]
                if p >= 0.10:
                    row["auchan"] = p
                    row["auchan_name"] = auch_match["name"]
        glovo_match, glovo_score, glovo_unit = find_best_match(match_item, glovo)
        if glovo_match:
            p = glovo_unit or glovo_match.get("price") or glovo_match.get("unit_price")
            if p and p >= 0.10:
                row["glovo"] = p
                row["glovo_name"] = glovo_match.get("name")
        if bolt:
            bolt_match, bolt_score, bolt_unit = find_best_match(match_item, bolt)
            if bolt_match:
                p = bolt_unit or bolt_match["price"]
                if p >= 0.10:
                    row["bolt"] = p
                    row["bolt_name"] = bolt_match.get("name")
        if row["continente"] or row["auchan"] or row["glovo"] or row["bolt"]:
            results.append(row)

    results = []
    processed_names = set()

    # --- Pass 1: regular (non-promo) products ---
    for item in sortido:
        if not item.get("available", True) or item.get("price", 0) <= 0:
            continue
        if re.search(r'\bleve\s+\d', item["name"], re.IGNORECASE):
            continue
        if re.search(r'\bcombo\b', item["name"], re.IGNORECASE):
            continue
        processed_names.add(item["name"])
        row = {
            "name": item["name"],
            "category": item["category"],
            "orders": item["orders"],
            "sortido": item["price"],
            "continente": None,
            "auchan": None,
            "glovo": None,
            "bolt": None,
        }
        _match_and_append(item, row, results)

    # --- Pass 2: "Leve N Poupe X%" multi-buy promotions ---
    # The catalog price for these is the TOTAL for N units; per-unit = price / N.
    # We strip the prefix, match using the base product name, and compare per-unit prices.
    for item in sortido:
        if not item.get("available", True) or item.get("price", 0) <= 0:
            continue
        leve_m = re.match(r'Leve (\d+) Poupe (\d+)%\s*[-–]\s*(.+)', item["name"], re.IGNORECASE)
        if not leve_m:
            continue
        leve_n   = int(leve_m.group(1))
        leve_pct = int(leve_m.group(2))
        base_name = leve_m.group(3).strip()
        if base_name in processed_names:
            continue  # already covered by a regular or earlier promo entry
        processed_names.add(base_name)
        match_item = {**item, "name": base_name}
        row = {
            "name": base_name,
            "category": item["category"],
            "orders": item["orders"],
            "sortido": round(item["price"] / leve_n, 2),
            "leve_n": leve_n,
            "leve_pct": leve_pct,
            "continente": None,
            "auchan": None,
            "glovo": None,
            "bolt": None,
        }
        _match_and_append(match_item, row, results)

    # --- Merge manually confirmed commodity matches ---
    fuzzy_names = {r["name"] for r in results}
    sortido_index = {p["name"]: p for p in sortido}
    try:
        confirmed_commodity = json.load(open("commodity_confirmed.json"))
        for c in confirmed_commodity:
            sp = sortido_index.get(c["name"])
            if not sp or sp.get("price", 0) <= 0:
                continue
            lm = re.match(r'Leve (\d+) Poupe (\d+)%\s*[-–]\s*(.+)', c["name"], re.IGNORECASE)
            row_name = lm.group(3).strip() if lm else c["name"]
            if row_name in fuzzy_names:
                continue
            fuzzy_names.add(row_name)
            row = {
                "name": row_name,
                "category": sp.get("category", ""),
                "orders": sp.get("orders", 0) or 0,
                "sortido": round(sp["price"] / int(lm.group(1)), 2) if lm else sp["price"],
                **({"leve_n": int(lm.group(1)), "leve_pct": int(lm.group(2))} if lm else {}),
                "continente": c.get("continente"),
                "auchan": c.get("auchan"),
                "glovo": c.get("glovo"),
                "bolt": c.get("bolt"),
                "pingodoce": c.get("pingodoce"),
                "auchan_name": c.get("auchan_name", ""),
            }
            results.append(row)
    except FileNotFoundError:
        pass

    # --- Enrich matched results with markup and priority ---
    for r in results:
        comp_prices = [r[k] for k in ("continente", "auchan", "glovo", "bolt", "pingodoce") if r.get(k)]
        min_comp = min(comp_prices) if comp_prices else None
        markup = round((r["sortido"] - min_comp) / min_comp * 100, 1) if min_comp else 0.0
        r["min_competitor"] = min_comp
        r["markup_pct"] = markup
        r["priority"] = round(markup * r["orders"], 1)

    # Sort by priority descending (most painful overpricing first)
    results.sort(key=lambda x: -x["priority"])

    with open("matched_prices.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # --- Category benchmarks: average markup per category from matched products ---
    from collections import defaultdict
    cat_markups = defaultdict(list)
    cat_orders  = defaultdict(int)
    for r in results:
        if r["markup_pct"] > 0:
            cat_markups[r["category"]].append(r["markup_pct"])
        cat_orders[r["category"]] += r["orders"]

    cat_benchmarks = {}
    for cat, markups in cat_markups.items():
        cat_benchmarks[cat] = {
            "avg_markup_pct":  round(sum(markups) / len(markups), 1),
            "matched_products": len(markups),
            "total_orders":    cat_orders[cat],
        }

    # --- Category estimates: unmatched sortido products that have a category benchmark ---
    matched_names = {r["name"] for r in results}
    estimates = []
    for item in sortido:
        if not item.get("available", True) or item.get("price", 0) <= 0:
            continue
        if item["name"] in matched_names:
            continue
        bench = cat_benchmarks.get(item["category"])
        if not bench:
            continue
        estimates.append({
            "name":         item["name"],
            "category":     item["category"],
            "orders":       item["orders"],
            "sortido":      item["price"],
            "markup_pct":   bench["avg_markup_pct"],
            "priority":     round(bench["avg_markup_pct"] * item["orders"], 1),
            "is_estimate":  True,
        })
    estimates.sort(key=lambda x: -x["priority"])

    with open("category_benchmarks.json", "w", encoding="utf-8") as f:
        json.dump({"benchmarks": cat_benchmarks, "estimates": estimates}, f, ensure_ascii=False, indent=2)

    print(f"\n→ {len(results)} produtos com match → matched_prices.json")
    print(f"→ {len(estimates)} produtos sem match com estimativa de categoria → category_benchmarks.json")
    print(f"\nTop 20 por prioridade (markup × encomendas):")
    for r in results[:20]:
        c = f"Cont €{r['continente']:.2f}" if r['continente'] else "Cont —"
        a = f"Auch €{r['auchan']:.2f}" if r['auchan'] else "Auch —"
        g = f"Glovo €{r['glovo']:.2f}" if r['glovo'] else "Glovo —"
        b = f"Bolt €{r['bolt']:.2f}" if r['bolt'] else "Bolt —"
        print(f"  [{r['priority']:6.0f}] {r['name']:<48} Sort €{r['sortido']:.2f}  +{r['markup_pct']:.0f}%  {c}  {a}  {g}  {b}")
