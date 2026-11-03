"""
Regenerates zone_data.json from zone_snapshots.jsonl.

Groups entries by (platform, time-slot) and unions cells per slot.
Quality filter rejects failed sweeps and known-bogus entries.

Cell formats in snapshots (both supported):
  Old: [lat, lon, ["sortido"]]         — presence in list, no metrics
  New: [lat, lon, eta_min, fee_eur]    — floats or null

Output cell format in zone_data.json:
  [lat, lon]                           — no metrics available
  [lat, lon, eta_min, fee_eur]         — when at least one metric is non-null

Slots:
  manha  07–12  (morning, before lunch)
  almoco 12–15
  tarde  15–19
  jantar 19–23
  late   23–07
  all    union of all valid entries for the platform
"""

import json, statistics
from datetime import datetime
from collections import defaultdict

SNAPS = "zone_snapshots.jsonl"
OUT   = "zone_data.json"

BOUNDS = {
    "bolt":     (300, 700),
    "glovo":    (300, 700),
    "ubereats": (150, 700),
}

def hour_to_slot(h):
    if 12 <= h < 15: return "almoco"
    if 15 <= h < 19: return "tarde"
    if 19 <= h < 23: return "jantar"
    if h >= 23 or h < 7: return "late"
    return "manha"

def parse_cell(cell):
    lat, lon = cell[0], cell[1]
    if len(cell) > 2 and isinstance(cell[2], list):
        return lat, lon, None, None
    eta = cell[2] if len(cell) > 2 else None
    fee = cell[3] if len(cell) > 3 else None
    return lat, lon, eta, fee

def median_or_none(vals):
    vs = [v for v in vals if v is not None]
    return round(statistics.median(vs), 2) if vs else None

def build_slot_data(es):
    """
    Given a list of snapshot entries for one (platform, slot), union cells
    and compute median ETA/fee per cell across sweeps.
    Returns (ts, n_sweeps, cells_out, eta_p50, fee_p50).
    cells_out: [[lat, lon, eta, fee]] with eta/fee as float or None.
    """
    cell_etas: dict[tuple, list] = defaultdict(list)
    cell_fees: dict[tuple, list] = defaultdict(list)
    all_keys: set[tuple] = set()

    for e in es:
        for cell in e["cells"]:
            lat, lon, eta, fee = parse_cell(cell)
            k = (lat, lon)
            all_keys.add(k)
            if eta is not None:
                cell_etas[k].append(eta)
            if fee is not None:
                cell_fees[k].append(fee)

    cells_out = []
    for k in sorted(all_keys):
        lat, lon = k
        eta = median_or_none(cell_etas[k])
        fee = median_or_none(cell_fees[k])
        if eta is not None or fee is not None:
            cells_out.append([lat, lon, eta, fee])
        else:
            cells_out.append([lat, lon])

    all_etas = [median_or_none(v) for v in cell_etas.values()]
    all_fees = [median_or_none(v) for v in cell_fees.values()]
    ts = max(e["ts"] for e in es)
    return ts, len(es), cells_out, median_or_none(all_etas), median_or_none(all_fees)

# ── Read and filter ───────────────────────────────────────────────────────────

entries = []
with open(SNAPS) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        p = e["platform"]
        lo, hi = BOUNDS.get(p, (100, 2000))
        n = len(e["cells"])
        if not (lo <= n <= hi):
            print(f"  skip  {e['ts']}  {p}: {n} cells (outside [{lo},{hi}])")
            continue
        h = datetime.fromisoformat(e["ts"]).hour
        entries.append({**e, "slot": hour_to_slot(h)})
        print(f"  keep  {e['ts']}  {p}: {n} cells → {hour_to_slot(h)}")

by_ps = defaultdict(lambda: defaultdict(list))
for e in entries:
    by_ps[e["platform"]][e["slot"]].append(e)

# ── Build output ──────────────────────────────────────────────────────────────

SLOT_ORDER = ["all", "manha", "almoco", "tarde", "jantar", "late"]

result = {}
for platform in sorted(by_ps):
    slots = by_ps[platform]
    result[platform] = {}

    for slot, es in slots.items():
        ts, n_sweeps, cells_out, eta_p50, fee_p50 = build_slot_data(es)
        result[platform][slot] = {
            "ts":       ts,
            "n_sweeps": n_sweeps,
            "cells":    cells_out,
            "eta_p50":  eta_p50,
            "fee_p50":  fee_p50,
        }

    # "all" = union across all slots
    ts_all, n_all, cells_all, eta_all, fee_all = build_slot_data(
        [e for es in slots.values() for e in es]
    )
    result[platform]["all"] = {
        "ts":       ts_all,
        "n_sweeps": n_all,
        "cells":    cells_all,
        "eta_p50":  eta_all,
        "fee_p50":  fee_all,
    }

with open(OUT, "w") as f:
    json.dump(result, f, separators=(",", ":"))

print()
print(f"Wrote {OUT}")
for platform in sorted(result):
    for slot in SLOT_ORDER:
        if slot in result[platform]:
            v = result[platform][slot]
            eta_s = f"  eta={v['eta_p50']}min" if v["eta_p50"] is not None else ""
            fee_s = f"  fee=€{v['fee_p50']}" if v["fee_p50"] is not None else ""
            print(f"  {platform}/{slot:7s}: {v['n_sweeps']:2d} sweep(s) → {len(v['cells'])} cells{eta_s}{fee_s}")
