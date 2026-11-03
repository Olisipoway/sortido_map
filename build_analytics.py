"""Build analytics.html from zone_data.json."""
import json, math
from collections import defaultdict

SORTIDO_LAT, SORTIDO_LON = 38.7201, -9.1376
LAT_KM = 111.0
LON_KM = 111.0 * math.cos(math.radians(SORTIDO_LAT))

def dist_km(lat, lon):
    return math.sqrt(((lat - SORTIDO_LAT) * LAT_KM)**2 + ((lon - SORTIDO_LON) * LON_KM)**2)

def median(vals):
    if not vals: return None
    s = sorted(vals)
    n = len(s)
    return round((s[n//2] + s[(n-1)//2]) / 2, 1)

with open("zone_data.json") as f:
    d = json.load(f)

platforms = ["bolt", "glovo", "ubereats"]
COLORS = {"bolt": "#3b82f6", "glovo": "#f97316", "ubereats": "#10b981"}
LABELS = {"bolt": "Bolt", "glovo": "Glovo", "ubereats": "UberEats"}
SLOTS = ["manha", "almoco", "tarde", "jantar", "late"]
SLOT_LABELS = {"manha": "Manhã", "almoco": "Almoço", "tarde": "Tarde", "jantar": "Jantar", "late": "Late"}

# ── Coverage sets ──────────────────────────────────────────────────────────────
cells_by_platform = {}
eta_by_cell = defaultdict(dict)

for p in platforms:
    slot = d[p]["all"]
    s = set()
    for c in slot["cells"]:
        k = (c[0], c[1])
        s.add(k)
        if len(c) > 2 and c[2] is not None:
            eta_by_cell[k][p] = c[2]
    cells_by_platform[p] = s

b, g, u = cells_by_platform["bolt"], cells_by_platform["glovo"], cells_by_platform["ubereats"]

coverage = {
    "bolt":    len(b),
    "glovo":   len(g),
    "ubereats": len(u),
    "all3":    len(b & g & u),
    "bolt_glovo": len(b & g - u),
    "bolt_uber":  len(b & u - g),
    "glovo_uber": len(g & u - b),
    "bolt_only":  len(b - g - u),
    "glovo_only": len(g - b - u),
    "uber_only":  len(u - b - g),
    "any":     len(b | g | u),
}

# ── ETA by distance bucket (2km) ──────────────────────────────────────────────
dist_buckets = defaultdict(lambda: defaultdict(list))
for k, petas in eta_by_cell.items():
    dk = int(dist_km(k[0], k[1]) / 2) * 2
    for p, eta in petas.items():
        dist_buckets[dk][p].append(eta)

max_dist = max(dist_buckets) + 2
dist_labels = [f"{dk}-{dk+2}km" for dk in range(0, max_dist, 2)]
dist_data = {p: [] for p in platforms}
for dk in range(0, max_dist, 2):
    for p in platforms:
        vals = dist_buckets[dk][p]
        dist_data[p].append(median(vals))

# ── ETA by time slot ──────────────────────────────────────────────────────────
slot_eta = {p: [] for p in platforms}
slot_fee = {p: [] for p in platforms}
slot_cells = {p: [] for p in platforms}
for slot in SLOTS:
    for p in platforms:
        v = d[p].get(slot, {})
        slot_eta[p].append(v.get("eta_p50"))
        slot_fee[p].append(v.get("fee_p50"))
        slot_cells[p].append(len(v.get("cells", [])))

# ── Render ─────────────────────────────────────────────────────────────────────
def js(v):
    return json.dumps(v)

def _table_rows(d, platforms, slots, slot_labels):
    rows = []
    for s in slots:
        cells_cols = []
        for p in platforms:
            v = d[p].get(s, {})
            n = len(v.get("cells", []))
            eta = v.get("eta_p50")
            fee = v.get("fee_p50")
            eta_str = f"{eta}min" if eta else "—"
            fee_str = f"€{fee}" if fee else "—"
            cells_cols.append(f"<td>{n} cél &nbsp;·&nbsp; {eta_str} &nbsp;·&nbsp; {fee_str}</td>")
        rows.append(f'<tr><td class="hi">{slot_labels[s]}</td>{"".join(cells_cols)}</tr>')
    return "\n        ".join(rows)

html = f"""<!DOCTYPE html>
<html lang="pt">
<head>
<meta charset="UTF-8">
<title>Sortido · Analytics</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }}
header {{ padding: 20px 32px; border-bottom: 1px solid #1e293b; display: flex; align-items: baseline; gap: 16px; }}
header h1 {{ font-size: 18px; font-weight: 700; color: #f8fafc; }}
header span {{ font-size: 13px; color: #64748b; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 20px; padding: 24px 32px; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 20px; }}
.card h2 {{ font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: #64748b; margin-bottom: 16px; }}
.card.wide {{ grid-column: 1 / -1; }}
canvas {{ max-height: 260px; }}
.stat-row {{ display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 16px; }}
.stat {{ flex: 1; min-width: 120px; }}
.stat-val {{ font-size: 28px; font-weight: 700; color: #f8fafc; line-height: 1; }}
.stat-sub {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
.overlap-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 4px; }}
.ov {{ background: #0f172a; border-radius: 8px; padding: 10px 12px; text-align: center; }}
.ov-val {{ font-size: 20px; font-weight: 700; }}
.ov-lbl {{ font-size: 11px; color: #64748b; margin-top: 2px; }}
.legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; }}
.leg {{ display: flex; align-items: center; gap: 6px; font-size: 12px; }}
.leg-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th {{ text-align: left; color: #64748b; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: .04em; padding: 6px 8px; border-bottom: 1px solid #334155; }}
td {{ padding: 8px 8px; border-bottom: 1px solid #1e293b; color: #cbd5e1; }}
td.hi {{ color: #f8fafc; font-weight: 600; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
.insight {{ background: #0f172a; border-radius: 8px; padding: 12px 16px; margin-top: 8px; font-size: 13px; line-height: 1.6; color: #94a3b8; }}
.insight strong {{ color: #f8fafc; }}
</style>
</head>
<body>
<header>
  <h1>Sortido · Delivery Analytics</h1>
  <span>bolt={d["bolt"]["all"]["n_sweeps"]} sweeps · glovo={d["glovo"]["all"]["n_sweeps"]} sweeps · ubereats={d["ubereats"]["all"]["n_sweeps"]} sweeps</span>
</header>
<div class="grid">

  <!-- Coverage summary -->
  <div class="card">
    <h2>Zona de entrega (total)</h2>
    <div class="stat-row">
      <div class="stat">
        <div class="stat-val" style="color:#3b82f6">{coverage["bolt"]}</div>
        <div class="stat-sub">células Bolt</div>
      </div>
      <div class="stat">
        <div class="stat-val" style="color:#f97316">{coverage["glovo"]}</div>
        <div class="stat-sub">células Glovo</div>
      </div>
      <div class="stat">
        <div class="stat-val" style="color:#10b981">{coverage["ubereats"]}</div>
        <div class="stat-sub">células UberEats</div>
      </div>
    </div>
    <div class="insight">
      Cada célula ≈ 0.25 km². UberEats tem zona <strong>{round((1 - coverage["ubereats"]/coverage["glovo"])*100)}% mais pequena</strong> que Glovo.
      <strong>{coverage["all3"]} células</strong> são entregues pelas 3 plataformas em simultâneo.
    </div>
  </div>

  <!-- Overlap -->
  <div class="card">
    <h2>Sobreposição de zonas</h2>
    <div class="overlap-grid">
      <div class="ov"><div class="ov-val" style="color:#6366f1">{coverage["all3"]}</div><div class="ov-lbl">Bolt+Glovo+UberEats</div></div>
      <div class="ov"><div class="ov-val" style="color:#3b82f6">{coverage["bolt_glovo"]}</div><div class="ov-lbl">Bolt+Glovo</div></div>
      <div class="ov"><div class="ov-val" style="color:#10b981">{coverage["bolt_uber"]}</div><div class="ov-lbl">Bolt+UberEats</div></div>
      <div class="ov"><div class="ov-val" style="color:#f97316">{coverage["glovo_uber"]}</div><div class="ov-lbl">Glovo+UberEats</div></div>
      <div class="ov"><div class="ov-val" style="color:#3b82f6">{coverage["bolt_only"]}</div><div class="ov-lbl">Bolt exclusivo</div></div>
      <div class="ov"><div class="ov-val" style="color:#f97316">{coverage["glovo_only"]}</div><div class="ov-lbl">Glovo exclusivo</div></div>
    </div>
  </div>

  <!-- ETA by distance -->
  <div class="card wide">
    <h2>ETA mediana por distância ao darkstore</h2>
    <div class="legend">
      {"".join(f'<div class="leg"><div class="leg-dot" style="background:{COLORS[p]}"></div>{LABELS[p]}</div>' for p in platforms)}
    </div>
    <canvas id="distChart"></canvas>
    <div class="insight" style="margin-top:12px">
      A <strong>2-4km</strong> Bolt já é <strong>{round((dist_data["bolt"][1] or 0) / (dist_data["ubereats"][1] or 1), 1)}× mais lento</strong> que UberEats.
      Glovo tem zona exclusiva além de <strong>9km</strong> que as outras plataformas não cobrem.
    </div>
  </div>

  <!-- ETA by slot -->
  <div class="card">
    <h2>ETA mediana por período do dia</h2>
    <canvas id="slotEtaChart"></canvas>
  </div>

  <!-- Fee by slot -->
  <div class="card">
    <h2>Taxa de entrega por período do dia</h2>
    <canvas id="slotFeeChart"></canvas>
    <div class="insight" style="margin-top:12px">
      Glovo aplica <strong>surge pricing ao jantar/late</strong>: €3.99 vs €2.99 ao almoço.
      UberEats não cobra taxa de entrega.
    </div>
  </div>

  <!-- Detailed table -->
  <div class="card wide">
    <h2>Detalhe por plataforma e período</h2>
    <table>
      <thead>
        <tr>
          <th>Período</th>
          <th>Bolt — células / ETA / taxa</th>
          <th>Glovo — células / ETA / taxa</th>
          <th>UberEats — células / ETA</th>
        </tr>
      </thead>
      <tbody>
        {_table_rows(d, platforms, SLOTS, SLOT_LABELS)}
      </tbody>
    </table>
  </div>

</div>

<script>
const chartDefaults = {{
  responsive: true,
  plugins: {{ legend: {{ display: false }} }},
  scales: {{
    x: {{ ticks: {{ color: "#64748b", font: {{ size: 11 }} }}, grid: {{ color: "#1e293b" }} }},
    y: {{ ticks: {{ color: "#64748b", font: {{ size: 11 }} }}, grid: {{ color: "#1e293b" }} }}
  }}
}};

// ETA by distance
new Chart(document.getElementById("distChart"), {{
  type: "line",
  data: {{
    labels: {js(dist_labels)},
    datasets: [
      {{ label: "Bolt",     data: {js(dist_data["bolt"])},     borderColor: "#3b82f6", backgroundColor: "#3b82f620", tension: 0.3, pointRadius: 4, spanGaps: true }},
      {{ label: "Glovo",    data: {js(dist_data["glovo"])},    borderColor: "#f97316", backgroundColor: "#f9731620", tension: 0.3, pointRadius: 4, spanGaps: true }},
      {{ label: "UberEats", data: {js(dist_data["ubereats"])}, borderColor: "#10b981", backgroundColor: "#10b98120", tension: 0.3, pointRadius: 4, spanGaps: true }},
    ]
  }},
  options: {{ ...chartDefaults, plugins: {{ legend: {{ display: true, labels: {{ color: "#94a3b8", font: {{ size: 12 }} }} }} }},
    scales: {{ ...chartDefaults.scales, y: {{ ...chartDefaults.scales.y, title: {{ display: true, text: "minutos", color: "#64748b" }} }} }} }}
}});

// ETA by slot
const slotLabels = {js([SLOT_LABELS[s] for s in SLOTS])};
new Chart(document.getElementById("slotEtaChart"), {{
  type: "bar",
  data: {{
    labels: slotLabels,
    datasets: [
      {{ label: "Bolt",     data: {js(slot_eta["bolt"])},     backgroundColor: "#3b82f6aa" }},
      {{ label: "Glovo",    data: {js(slot_eta["glovo"])},    backgroundColor: "#f97316aa" }},
      {{ label: "UberEats", data: {js(slot_eta["ubereats"])}, backgroundColor: "#10b981aa" }},
    ]
  }},
  options: {{ ...chartDefaults, plugins: {{ legend: {{ display: true, labels: {{ color: "#94a3b8", font: {{ size: 12 }} }} }} }},
    scales: {{ ...chartDefaults.scales, y: {{ ...chartDefaults.scales.y, title: {{ display: true, text: "minutos", color: "#64748b" }} }} }} }}
}});

// Fee by slot
new Chart(document.getElementById("slotFeeChart"), {{
  type: "bar",
  data: {{
    labels: slotLabels,
    datasets: [
      {{ label: "Bolt",     data: {js(slot_fee["bolt"])},     backgroundColor: "#3b82f6aa" }},
      {{ label: "Glovo",    data: {js(slot_fee["glovo"])},    backgroundColor: "#f97316aa" }},
      {{ label: "UberEats", data: {js(slot_fee["ubereats"])}, backgroundColor: "#10b981aa" }},
    ]
  }},
  options: {{ ...chartDefaults, plugins: {{ legend: {{ display: true, labels: {{ color: "#94a3b8", font: {{ size: 12 }} }} }} }},
    scales: {{ ...chartDefaults.scales, y: {{ ...chartDefaults.scales.y, title: {{ display: true, text: "€", color: "#64748b" }} }} }} }}
}});
</script>
</body>
</html>"""

with open("analytics.html", "w", encoding="utf-8") as f:
    f.write(html)
print("→ analytics.html")
