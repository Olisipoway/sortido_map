"""
Build orders_by_month.json from UberEats + Glovo CSV exports.
Output: [{month, count, revenue, partial}]  — partial=true if month is incomplete
"""
import csv, json
from datetime import datetime, timezone
from collections import defaultdict

CURRENT_MONTH = "2026-10"  # last month has incomplete data

def parse_eur(v):
    try: return float(str(v).replace("€","").strip())
    except: return 0.0

def process_csv(path, date_col="placed_at", value_col="order_value"):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            placed = r.get(date_col, "")
            if not placed or placed == date_col:
                continue
            try:
                dt = datetime.fromisoformat(placed)
                month = dt.strftime("%Y-%m")
                val = parse_eur(r.get(value_col, 0))
                rows.append((month, val))
            except Exception:
                continue
    return rows

data = defaultdict(lambda: {"count": 0, "revenue": 0.0})

for month, val in process_csv("ubereats_orders_with_addresses.csv"):
    data[month]["count"] += 1
    data[month]["revenue"] += val

for month, val in process_csv("glovo_orders_with_addresses.csv"):
    data[month]["count"] += 1
    data[month]["revenue"] += val

output = []
for month in sorted(data):
    if data[month]["count"] < 10:  # skip near-empty months
        continue
    output.append({
        "month":   month,
        "count":   data[month]["count"],
        "revenue": round(data[month]["revenue"], 2),
        "partial": month == CURRENT_MONTH,
    })

with open("orders_by_month.json", "w") as f:
    json.dump(output, f, indent=2)

print("Month breakdown:")
for row in output:
    flag = " (partial)" if row["partial"] else ""
    print(f"  {row['month']}{flag}: {row['count']} orders  €{row['revenue']:.0f}")
print(f"\n→ {len(output)} months → orders_by_month.json")
