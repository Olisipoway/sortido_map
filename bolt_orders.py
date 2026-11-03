"""
Fetch Bolt Food order history via the partner portal API.
Token expires ~10 min — refresh from foodpartner.bolt.eu → DevTools → Network →
any request → Authorization header (Bearer eyJ...)
"""
import subprocess, json, csv, time, os, random
from datetime import datetime, timezone
from urllib.parse import urlencode

BASE_URL   = "https://deliveryproviderportal.live.boltsvc.net/deliveryProvider"
PROVIDER_ID = 186270
SESSION_ID  = "242f576b-ad4d-465e-a541-c86ee89cd98a"
DEVICE_ID   = "242f576b-ad4d-465e-a541-c86ee89cd98a"

# Paste fresh Bearer token from foodpartner.bolt.eu DevTools (~10 min expiry)
TOKEN = "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6ImRiZTMwOTZhLTc3NWUtNDNkNy04MDkwLTg5MDkyOGEyNzAzNyJ9.eyJkYXRhIjp7ImFjY291bnRfaWQiOjM5Nzg2NywiYWNjb3VudF90eXBlIjoicHJvdmlkZXIiLCJpc19zdXBlcl91c2VyIjpmYWxzZSwiY2l0eV9wZXJtaXNzaW9ucyI6W10sInZlbmRvcl9wZXJtaXNzaW9ucyI6W10sInByb3ZpZGVyX3Blcm1pc3Npb25zIjpbeyJwcm92aWRlcl9pZCI6MTg2MjcwfV0sInJlZnJlc2hfdG9rZW5faWQiOjM5OTA2NTEyfSwiaWF0IjoxNzkzMTM2NTg3LCJleHAiOjE3OTMxMzcxODcsImlzcyI6InByb3ZpZGVyX3BvcnRhbCJ9.crtZU7n9YvGFmpv4ZliOe13NCT3irUFA-9qrBG_WKcCmoDTjLKeHQXg_VrmbDT_WUhhPztzYURiDcqz2QjZgng"

PARAMS = {
    "session_id": SESSION_ID,
    "device_id":  DEVICE_ID,
    "device_name": "Chrome",
    "device_os_version": "10.15.7",
    "language": "en-US",
    "version":  "MW.0.01",
}


def post(endpoint, body):
    url = f"{BASE_URL}/{endpoint}?" + urlencode(PARAMS)
    result = subprocess.run(
        ["curl", "--silent", "--url", url,
         "-H", "accept: application/json",
         "-H", "content-type: application/json",
         "-H", "origin: https://foodpartner.bolt.eu",
         "-H", "referer: https://foodpartner.bolt.eu/",
         "-H", f"authorization: Bearer {TOKEN}",
         "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
         "--data-raw", json.dumps(body)],
        capture_output=True, text=True
    )
    if not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def get_history_batch(start_id=None, end_id=None):
    body = {"provider_id": PROVIDER_ID, "filter": {}}
    if start_id is not None:
        body["start"] = start_id
    if end_id is not None:
        body["end"] = end_id
    return post("getOrderHistoryDetails", body)


def ts_to_iso(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def extract_order(o):
    placed = o.get("order_waiting_confirmation_transition_timestamp")
    final  = o.get("order_final_state_transition_timestamp")
    value  = (o.get("total_item_price") or {}).get("value")
    prep   = o.get("preparation_details") or {}
    return {
        "order_id":      o.get("order_id"),
        "reference_id":  o.get("order_reference_id"),
        "placed_at":     ts_to_iso(placed),
        "final_at":      ts_to_iso(final),
        "status":        o.get("order_state"),
        "fail_reason":   o.get("order_fail_reason"),
        "order_value":   value,
        "delivery_type": o.get("delivery_type"),
        "order_type":    o.get("order_type"),
        "prep_time_s":   prep.get("actual_preparation_time_seconds"),
    }


if __name__ == "__main__":
    OUTPUT_FILE  = "bolt_orders.csv"
    ORDERS_CACHE = "bolt_orders_list.json"

    fieldnames = [
        "order_id", "reference_id", "placed_at", "final_at",
        "status", "fail_reason", "order_value", "delivery_type",
        "order_type", "prep_time_s",
    ]

    done_ids = set()
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done_ids.add(row["order_id"])
        print(f"Resuming — {len(done_ids)} already saved.")

    all_orders = []
    if os.path.exists(ORDERS_CACHE):
        with open(ORDERS_CACHE) as f:
            all_orders = json.load(f)
        print(f"Loaded {len(all_orders)} orders from cache.")
    else:
        # Paginate backwards by order ID range.
        # Each call returns up to ~20 orders between start and end order IDs.
        # We walk backwards using the min order_id from each batch.
        # Batch size ~500k IDs covers ~20 orders per call at current density.
        BATCH_SIZE = 500_000
        start_id   = 342_000_000   # safely above most recent known order
        end_id     = start_id - BATCH_SIZE
        page       = 1
        STOP_AT    = 300_000_000   # go back ~1 year of order IDs

        while start_id > STOP_AT:
            print(f"Page {page} ({end_id}–{start_id})...", end=" ", flush=True)
            data = get_history_batch(start_id, end_id)

            if data is None:
                print("null — token expired, update TOKEN and re-run")
                break
            code = data.get("code") if isinstance(data, dict) else None
            if code not in (0, None):
                print(f"error {code}: {data.get('message')}")
                break

            orders = (data.get("data") or {}).get("orders") or []

            if orders:
                print(f"{len(orders)} orders")
                all_orders.extend(orders)
                min_id   = min(o["order_id"] for o in orders)
                start_id = min_id - 1
                end_id   = start_id - BATCH_SIZE
            else:
                print("0 — stepping back")
                start_id = end_id - 1
                end_id   = start_id - BATCH_SIZE

            page += 1
            time.sleep(random.uniform(1, 2))

        with open(ORDERS_CACHE, "w") as f:
            json.dump(all_orders, f)
        print(f"\nTotal fetched: {len(all_orders)} — cached to {ORDERS_CACHE}")

    if not all_orders:
        print("No orders. Token may be expired — update TOKEN and retry.")
        exit()

    with open(OUTPUT_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not done_ids:
            writer.writeheader()

        new = 0
        for o in all_orders:
            oid = str(o.get("order_id", ""))
            if oid in done_ids:
                continue
            writer.writerow(extract_order(o))
            done_ids.add(oid)
            new += 1

    print(f"Wrote {new} new orders → {OUTPUT_FILE}")
