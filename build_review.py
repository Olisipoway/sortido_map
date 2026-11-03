"""
Generate review.html with proposed commodity equivalences for manual review.

Differences from build_price_match.py:
  - Lower match threshold (45 vs 70) to surface imperfect-but-plausible candidates
  - Requires minimum token overlap (0.35) to avoid nonsense proposals
  - Rejects pack-count mismatches when no volume info to normalize
  - Excludes products already in matched_prices.json or commodity_confirmed.json
"""
import json, re, sys, os

sys.path.insert(0, os.path.dirname(__file__))
from build_price_match import (
    extract_pack_info, token_overlap, normalize, match_score, REJECT_WORDS
)

REVIEW_THRESHOLD = 45   # below 70 = not auto-matched; above 45 = plausible candidate
MIN_SEMANTIC_OVERLAP = 0.55  # on meaningful words only (no numbers, no unit abbreviations)

# Unit abbreviations and filler tokens that must not drive overlap scoring
_UNIT_TOKENS = {"x", "g", "gr", "l", "lt", "cl", "ml", "kg", "un", "sdr", "emb", "b", "s"}

def semantic_overlap(a, b):
    """Token overlap excluding numbers and unit abbreviations — prevents size-only false matches."""
    STOP = {"com", "de", "e", "em", "a", "o", "da", "do", "das", "dos", "sem", "para", "um", "uma"} | _UNIT_TOKENS
    def _norm(s):
        s = s.lower()
        s = re.sub(r'(\d)([a-z])', r'\1 \2', s)
        s = re.sub(r'([a-z])(\d)', r'\1 \2', s)
        return s
    ta = {t for t in re.findall(r'\w+', _norm(a)) if t not in STOP and not t.isdigit() and len(t) > 1}
    tb = {t for t in re.findall(r'\w+', _norm(b)) if t not in STOP and not t.isdigit() and len(t) > 1}
    if not ta:
        return 0
    return len(ta & tb) / len(ta)


def find_review_candidate(sortido_item, catalog, source_label):
    """Like find_best_match but with lower threshold and stricter plausibility filters."""
    s_brand, s_size, s_type = normalize(sortido_item["name"])
    s_pack, s_unit_size = extract_pack_info(sortido_item["name"])

    best_score = 0
    best = None
    best_price = None

    for item in catalog:
        c_brand, c_size, c_type = normalize(item["name"])
        c_pack, c_unit_size = extract_pack_info(item["name"])

        sc = match_score(s_brand, s_unit_size, s_type, c_brand, c_unit_size, c_type,
                         sortido_item["name"], item["name"])
        if sc < 0:
            continue

        # Reject: pack count differs — review page is for commodity equivalences, not pack-size normalization
        if s_pack != c_pack:
            continue

        # Require minimum semantic overlap — filters size-only false matches (e.g. "1.3kg" matching unrelated products)
        overlap = semantic_overlap(sortido_item["name"], item["name"])
        if overlap < MIN_SEMANTIC_OVERLAP:
            continue

        if sc > best_score:
            best_score = sc
            best = item
            # Normalize price to sortido pack count
            if c_unit_size is not None:
                c_unit_price = item["price"] / c_pack if c_pack > 1 else item["price"]
                best_price = round(c_unit_price * s_pack, 2)
            elif c_pack > 1 and s_pack > 1:
                best_price = round((item["price"] / c_pack) * s_pack, 2)
            else:
                best_price = round(item["price"], 2)

    if best_score >= REVIEW_THRESHOLD and best is not None:
        # Sanity check: price ratio must be plausible (0.2x–3x sortido price)
        ratio = best_price / sortido_item["price"]
        if ratio < 0.20 or ratio > 3.0:
            return None, 0, None
        return best, best_score, best_price
    return None, 0, None


def build_candidates(sortido, catalogs, already_matched, already_confirmed):
    rows = []
    for item in sortido:
        if not item.get("available", True) or item.get("price", 0) <= 0:
            continue
        if re.search(r'\bleve\s+\d', item["name"], re.IGNORECASE):
            continue
        if re.search(r'\bcombo\b', item["name"], re.IGNORECASE):
            continue
        if item["name"] in already_matched:
            continue
        if item["name"] in already_confirmed:
            continue

        best_match = None
        best_score = 0
        best_price = None
        best_source = None
        best_name = None

        for source_label, catalog in catalogs:
            m, sc, price = find_review_candidate(item, catalog, source_label)
            if m and sc > best_score:
                best_score = sc
                best_match = m
                best_price = price
                best_source = source_label
                best_name = m["name"]

        rows.append({
            "sortido": item["name"],
            "sortido_price": item["price"],
            "category": item["category"],
            "comp": best_name,
            "competitor": best_source,
            "comp_price": best_price,
            "score": best_score,
        })

    rows.sort(key=lambda r: (r["category"], r["sortido"]))
    return rows


def render_html(rows):
    import json as _json
    data_json = _json.dumps(rows, ensure_ascii=False)
    with_comp = sum(1 for r in rows if r["comp"])
    without_comp = len(rows) - with_comp

    return f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<title>Revisão de Equivalências</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; background: #f8fafc; color: #0f172a; }}
  header {{ background: #0f172a; color: #fff; padding: 16px 24px; display: flex; align-items: center; gap: 16px; }}
  header h1 {{ font-size: 18px; font-weight: 600; }}
  .stats {{ margin-left: auto; font-size: 13px; color: #94a3b8; }}
  .controls {{ padding: 12px 24px; background: #fff; border-bottom: 1px solid #e2e8f0; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }}
  .controls select, .controls input[type=text] {{ padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 6px; font-size: 13px; }}
  .controls input[type=text] {{ width: 220px; }}
  .btn-export {{ margin-left: auto; background: #0f172a; color: #fff; border: none; padding: 7px 16px; border-radius: 6px; font-size: 13px; cursor: pointer; }}
  .btn-export:hover {{ background: #1e293b; }}
  .cat-header {{ padding: 8px 24px; background: #f1f5f9; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: #64748b; border-bottom: 1px solid #e2e8f0; }}
  .row {{ display: grid; grid-template-columns: 1fr 1fr 190px; border-bottom: 1px solid #e2e8f0; background: #fff; }}
  .row:hover {{ background: #fafbff; }}
  .row.confirmed {{ background: #f0fdf4; }}
  .row.denied {{ background: #fff5f5; }}
  .row.no-match {{ background: #fffbeb; }}
  .cell {{ padding: 12px 16px; }}
  .cell:first-child {{ padding-left: 24px; }}
  .prod-name {{ font-size: 13px; font-weight: 500; line-height: 1.3; }}
  .price-row {{ display: flex; align-items: baseline; gap: 8px; margin-top: 3px; }}
  .price-unit {{ font-size: 13px; font-weight: 600; color: #0f172a; }}
  .comp-name {{ font-size: 13px; line-height: 1.3; }}
  .comp-source {{ font-size: 12px; color: #64748b; margin-top: 3px; }}
  .no-match-label {{ font-size: 13px; color: #b45309; font-style: italic; }}
  .actions {{ display: flex; flex-direction: column; gap: 6px; padding: 10px 14px; justify-content: center; }}
  .btn-row {{ display: flex; gap: 6px; align-items: center; }}
  button.ok {{ background: #22c55e; color: #fff; border: none; padding: 5px 13px; border-radius: 5px; font-size: 12px; cursor: pointer; font-weight: 600; }}
  button.ok:hover {{ background: #16a34a; }}
  button.no {{ background: #ef4444; color: #fff; border: none; padding: 5px 13px; border-radius: 5px; font-size: 12px; cursor: pointer; font-weight: 600; }}
  button.no:hover {{ background: #dc2626; }}
  button.ok.active {{ outline: 3px solid #15803d; }}
  button.no.active {{ outline: 3px solid #b91c1c; }}
  button.clr {{ background: none; border: 1px solid #cbd5e1; color: #64748b; padding: 3px 8px; border-radius: 5px; font-size: 11px; cursor: pointer; }}
  textarea.note {{ width: 100%; border: 1px solid #e2e8f0; border-radius: 5px; padding: 4px 7px; font-size: 12px; resize: none; height: 34px; font-family: inherit; }}
  textarea.note:focus {{ outline: 2px solid #6366f1; border-color: transparent; }}
  #modal {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 100; align-items: center; justify-content: center; }}
  #modal.show {{ display: flex; }}
  .modal-box {{ background: #fff; border-radius: 10px; padding: 24px; width: 660px; max-height: 80vh; display: flex; flex-direction: column; gap: 12px; }}
  .modal-box h2 {{ font-size: 16px; }}
  .modal-box textarea {{ flex: 1; min-height: 300px; font-family: monospace; font-size: 12px; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; }}
  .modal-btns {{ display: flex; gap: 8px; }}
  .modal-btns button {{ background: #0f172a; color: #fff; border: none; padding: 8px 18px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
</style>
</head>
<body>
<header>
  <h1>Revisão de Equivalências · Sortido</h1>
  <span class="stats" id="stats"></span>
</header>
<div class="controls">
  <select id="fcat" onchange="render()"><option value="">Todas as categorias</option></select>
  <select id="fst" onchange="render()">
    <option value="">Todos</option>
    <option value="pending">Por rever</option>
    <option value="ok">Confirmados</option>
    <option value="no">Negados</option>
  </select>
  <select id="fmatch" onchange="render()">
    <option value="">Com e sem candidato</option>
    <option value="has">Com candidato</option>
    <option value="none">Sem candidato</option>
  </select>
  <input type="text" id="fsrch" placeholder="Pesquisar…" oninput="render()">
  <button class="btn-export" onclick="showExport()">Exportar JSON</button>
</div>
<div id="list"></div>

<div id="modal">
  <div class="modal-box">
    <h2>Exportar confirmados</h2>
    <textarea id="export-text" readonly></textarea>
    <div class="modal-btns">
      <button onclick="copyExport()">Copiar</button>
      <button onclick="document.getElementById('modal').classList.remove('show')">Fechar</button>
    </div>
  </div>
</div>

<script>
const RAW = {data_json};
const state = RAW.map(() => ({{verdict: null, note: ''}}));

// Populate category filter
const cats = [...new Set(RAW.map(r => r.category))].sort();
const catSel = document.getElementById('fcat');
cats.forEach(c => {{ const o = document.createElement('option'); o.value = c; o.textContent = c; catSel.appendChild(o); }});

function fmt(v) {{ return v != null ? '€' + Number(v).toFixed(2) : '—'; }}

function render() {{
  const fcat  = document.getElementById('fcat').value;
  const fst   = document.getElementById('fst').value;
  const fmatch = document.getElementById('fmatch').value;
  const fsrch = document.getElementById('fsrch').value.toLowerCase();
  const list  = document.getElementById('list');
  list.innerHTML = '';
  let lastCat = null;

  RAW.forEach((r, i) => {{
    const s = state[i];
    if (fcat && r.category !== fcat) return;
    if (fst === 'pending' && s.verdict !== null) return;
    if (fst === 'ok' && s.verdict !== 'ok') return;
    if (fst === 'no' && s.verdict !== 'no') return;
    if (fmatch === 'has' && !r.comp) return;
    if (fmatch === 'none' && r.comp) return;
    if (fsrch && !r.sortido.toLowerCase().includes(fsrch) && !(r.comp||'').toLowerCase().includes(fsrch)) return;

    if (r.category !== lastCat) {{
      lastCat = r.category;
      const h = document.createElement('div');
      h.className = 'cat-header';
      h.textContent = r.category;
      list.appendChild(h);
    }}

    const cls = s.verdict === 'ok' ? 'confirmed' : s.verdict === 'no' ? 'denied' : !r.comp ? 'no-match' : '';

    const div = document.createElement('div');
    div.className = 'row ' + cls;
    div.innerHTML = `
      <div class="cell">
        <div class="prod-name">${{r.sortido}}</div>
        <div class="price-row">
          <span class="price-unit">${{fmt(r.sortido_price)}}</span>
        </div>
      </div>
      <div class="cell">
        ${{r.comp
          ? `<div class="comp-name">${{r.comp}}</div><div class="comp-source">${{r.competitor}} · ${{fmt(r.comp_price)}}</div>`
          : `<div class="no-match-label">sem candidato</div>`}}
      </div>
      <div class="cell actions">
        <div class="btn-row">
          ${{r.comp ? `
            <button class="ok${{s.verdict==='ok'?' active':''}}" onclick="setV(${{i}},'ok')">✓ Ok</button>
            <button class="no${{s.verdict==='no'?' active':''}}" onclick="setV(${{i}},'no')">✗ Não</button>
            ${{s.verdict ? `<button class="clr" onclick="setV(${{i}},null)">×</button>` : ''}}
          ` : `<span style="font-size:11px;color:#b45309">sem candidato</span>`}}
        </div>
        <textarea class="note" placeholder="nota…" oninput="setNote(${{i}},this.value)">${{s.note}}</textarea>
      </div>`;
    list.appendChild(div);
  }});

  const done = Object.values(state).filter(s => s.verdict !== null).length;
  document.getElementById('stats').textContent = done + ' / ' + RAW.length + ' revistos';
}}

function setV(i, v) {{ state[i].verdict = v; render(); }}
function setNote(i, v) {{ state[i].note = v; }}

function showExport() {{
  const out = RAW
    .map((r,i) => ({{...r, verdict: state[i].verdict, note: state[i].note}}))
    .filter(r => r.verdict !== null);
  document.getElementById('export-text').value = JSON.stringify(out, null, 2);
  document.getElementById('modal').classList.add('show');
}}
function copyExport() {{
  navigator.clipboard.writeText(document.getElementById('export-text').value);
}}

render();
</script>
</body>
</html>"""


if __name__ == "__main__":
    sortido    = json.load(open("sortido_catalog.json"))
    continente = json.load(open("continente_catalog.json"))
    auchan     = json.load(open("auchan_catalog.json"))
    bolt       = json.load(open("bolt_catalog.json"))

    already_matched   = {r["name"] for r in json.load(open("matched_prices.json"))}
    already_confirmed = {c["name"] for c in json.load(open("commodity_confirmed.json"))}

    catalogs = [
        ("Continente", continente),
        ("Auchan", auchan),
        ("Bolt", bolt),
    ]

    print("A gerar candidatos...")
    rows = build_candidates(sortido, catalogs, already_matched, already_confirmed)

    with_comp = sum(1 for r in rows if r["comp"])
    print(f"{len(rows)} produtos por rever: {with_comp} com candidato, {len(rows)-with_comp} sem candidato")

    html = render_html(rows)
    with open("review.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("→ review.html gerado")
