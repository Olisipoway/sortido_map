import subprocess
import json
import csv
import time
import os
import sys
from datetime import datetime, timezone


def log(msg, end="\n"):
    print(msg, end=end, flush=True)

# Paste fresh Bearer token from browser DevTools (valid ~4 hours)
# How to get: portal.glovoapp.com → DevTools → Network → any 'query' XHR → Headers → Authorization
TOKEN = "eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleW1ha2VyLXZwLTAwMTQtdnAtZXUiLCJ0eXAiOiJKV1QifQ.eyJpc3MiOiJodHRwczovL3ZlbmRvcnBvcnRhbC1ldS5kaC1hdXRoLmlvIiwic3ViIjoiNGYxYzBkZTItMTM1ZS00ZWExLWFkNmItZDJhMWI5NjlhZmZlIiwiYXVkIjoidmVuZG9yLXBvcnRhbC1wcmQtZXUiLCJleHAiOjE3OTMxNDg0MDIsImlhdCI6MTc5MzEzNDAwMiwianRpIjoiMnA4bmdrbDRpdTl6MGh2b2xxZXVqa2dnOW5pYTJrZ3hpb2VqMTd2YiIsInNjb3BlIjoia2V5bWFrZXItdXNlci52ZW5kb3Jwb3J0YWwudmVuZG9yLXBvcnRhbC1wcmQtZXUuZ3ZfcHQiLCJtZXRhZGF0YSI6eyJlbWFpbCI6InZhc2NvQG9saXNpcG93YXkuY29tIiwibHB2aWQiOiJSMVpmVUZRdE9URTBNRFE1IiwicGxhdGZvcm1zIjpbIjkxNDA0OTtHVl9QVCJdfX0.X6YN97N1eQBgH0c2A2Que_62plMX1QMGHOrXR4bk5lnzd1nqmHAvVCuj7zdiZ2jK3XMtokStO6GxHPZhS1HvobMaJwxmmpMRpLbUGWsIpUqbWxKV3cW9KDwjW6tEytjCChDjJx4aIjgitVWLu4K-nCqem3IAqMLgUIx1GsDi1bDkUkYx6R0RPj0VvT9HdZXmecEcwyPS8gjy-T9dXeTSJ-Oa41X_EdHVhJiZYP6Y6vv8ufb1G3U5r9FKpKtNfKeu5IJtMu5ltVi5pc-OeyZuHVmjy_OboWUeT8P6nrh4CvnT3MtdIVMFvu06a0qF6V_R9k04uAariN2G2eOwI2Refw"
PX_COOKIES = "_px3=bce046d681b4c0556430a3505bbd9beb43cb7202fbd25f399440032a67488618:cnXmr5DXPvmkv9A+vLGANTZt4G2cg/dpoucgVZwm4rHxSCwxxQlXEIhnLcsiAOhj8i0cV7Ae0AsuCHvKtZ/Jag==:1000:Sqc/VjX0L7wN1LDmRH4af9NrKRWDPk3an9SmEiCYy9LXu0+oWsKGlgLtL9Vd5xegUgqNeqRIh9UUj11+hEIHZHcA3PK/2Z1AN1snI31cuACNU9aQrwLrJdPbJBktExIIiBOyzUiwvadSHXeR84e3vvq8lD8ZnYi7xhYmAhPAqCy33k4rDvNCx8Mpkh3I6jJ92YuEB5KOe2EOMSEc9VUvUWP4k4x71JlV+T9AMhCJryic4DGIct/5IfGEvZ1NLhEAzIlZONg/x1f8tF60u4QkvEJWeynMp6Iv1wIXSOu7JYmNwfkaHtLSciKQ0p4qivi35U5uUK3An5WrnLbzqa6ycvaVSvX70yq9U17+hQSxbrlX7gwjAdmdGNLZEeSSZEpMDgRS+aq0yAEyaC8zpQmrOGJCfPcjcYcpZs//5FPL7ZqUJJ7zc8GXpfPP5/sbZf+cj5Zkb/d7vZzM8nzTwZ1nkkPXLOy6VbGpPjQYOkrMzqI=; _pxvid=cecb92d1-cec8-11f1-9489-116ac485bd81; pxcts=YpwwQRNcYK2QulfRL0Ws/A2-Xg1UzC5GEtkcOLCjyWQ=:6dl0xF7efZLt8HD5YWejyXCAasO6r3KhbQ9Un/ykI4C1tGIqNIN-7MnS-TnzcswFlWdgHDmRdZGLNqd6mGsA2BQdaZBDtkgO2HUb3u5r/FLUDGL-RZCK0U0/F3Jb5KMsKDvxI1U0eexXBZDYIYmNgVpa13qECyDawlcfMdNdMeeu/jPd9xGgTth6IYa3ZvJy"

VENDOR_ID = "914049"
ENTITY_ID = "GV_PT"
API_URL   = "https://vagw-api.eu.prd.portal.restaurant/query"

CURL_HEADERS = [
    "-H", "accept: */*",
    "-H", "accept-language: en-US,en;q=0.7",
    "-H", "apollographql-client-name: API Gateway",
    "-H", f"authorization: Bearer {TOKEN}",
    "-H", "content-type: application/json",
    "-H", "origin: https://portal.glovoapp.com",
    "-H", "referer: https://portal.glovoapp.com/",
    "-H", 'sec-ch-ua: "Brave";v="155", "Chromium";v="155", "Not(A:Brand";v="24"',
    "-H", "sec-ch-ua-mobile: ?0",
    "-H", 'sec-ch-ua-platform: "macOS"',
    "-H", "sec-fetch-dest: empty",
    "-H", "sec-fetch-mode: cors",
    "-H", "sec-fetch-site: cross-site",
    "-H", "sec-gpc: 1",
    "-H", "user-agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
    "-H", "x-app-name: one-web",
    "-H", "x-country: PT",
    "-H", "x-global-entity-id: GV_PT",
    "-H", "x-rps-device: 94a2e1df-ed85-45d2-aa45-cd1d94945989",
    "-H", "x-user-id: 4f1c0de2-135e-4ea1-ad6b-d2a1b969affe",
    "-H", "x-vendor-id: R1ZfUFQtOTE0MDQ5",
    "-H", f"x-px-cookies: {PX_COOKIES}",
]

GLOBAL_VENDOR = {"globalEntityId": ENTITY_ID, "vendorId": VENDOR_ID}


def gql(operation, query, variables):
    payload = json.dumps({"operationName": operation, "query": query, "variables": variables})
    result = subprocess.run(
        ["curl", "--silent", "--url", API_URL] + CURL_HEADERS + ["--data-raw", payload],
        capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


LIST_ORDERS_QUERY = """
query ListOrders($params: ListOrdersReq!) {
  orders {
    listOrders(input: $params) {
      nextPageToken
      orders {
        orderId
        orderStatus
        placedTimestamp
        deliveryType
      }
    }
  }
}
"""

ORDER_DETAIL_QUERY = """
query GetOrderDetails($params: OrderReq!) {
  orders {
    order(input: $params) {
      order {
        orderId
        placedTimestamp
        status
        orderValue
        delivery {
          provider
          location {
            AddressText
            city
            district
            postCode
          }
        }
      }
      orderStatuses {
        status
        timestamp
        detail {
          ... on Accepted {
            estimatedDeliveryTime
            commitedPickupTime
          }
          ... on Delivered {
            timestamp
          }
          ... on PickedUpByRider {
            timestamp
          }
        }
      }
    }
  }
}
"""


def list_orders(time_from, time_to):
    orders = []
    page_token = None
    page = 1
    while True:
        pagination = {"pageSize": 50}
        if page_token:
            pagination["pageToken"] = page_token
        data = gql("ListOrders", LIST_ORDERS_QUERY, {"params": {
            "globalVendorCodes": [GLOBAL_VENDOR],
            "timeFrom": time_from,
            "timeTo": time_to,
            "pagination": pagination,
            "useRefundStreamIssueSource": False,
        }})
        if "errors" in data or "data" not in data:
            log(f"Error: {data.get('errors') or list(data.keys())}")
            if "appId" in data:
                wait = 60
                log(f"Rate limited — waiting {wait}s...")
                time.sleep(wait)
                continue
            break
        result = data["data"]["orders"]["listOrders"]
        batch = result.get("orders", [])
        orders.extend(batch)
        log(f"Page {page}: {len(batch)} orders (total: {len(orders)})")
        page_token = result.get("nextPageToken")
        if not page_token:
            break
        page += 1
        time.sleep(0.5)
    return orders


def get_order_detail(order_id, placed_timestamp):
    while True:
        data = gql("GetOrderDetails", ORDER_DETAIL_QUERY, {
            "params": {
                "orderId": order_id,
                "GlobalVendorCode": GLOBAL_VENDOR,
                "isBillingDataFlagEnabled": False,
                "placedTimestamp": placed_timestamp,
                "useRefundStreamIssueSource": False,
            },
        })
        if data is None or "appId" in data:
            log(" [rate limited, waiting 60s]")
            time.sleep(60)
            continue
        return (data.get("data") or {}).get("orders", {}).get("order")


def extract_timestamps(order_statuses):
    ts = {}
    for s in (order_statuses or []):
        status = s.get("status")
        detail = s.get("detail") or {}
        if status == "accepted":
            ts["pickup_time"]   = detail.get("commitedPickupTime")
            ts["delivery_time"] = detail.get("estimatedDeliveryTime")
        elif status == "delivered":
            ts["delivered_at"]  = detail.get("timestamp") or s.get("timestamp")
        elif status == "pickedUpByRider":
            ts["picked_up_at"]  = detail.get("timestamp") or s.get("timestamp")
    return ts


if __name__ == "__main__":
    ORDERS_CACHE = "glovo_orders_list.json"
    output_file  = "glovo_orders_with_addresses.csv"

    # Load cached order list or fetch fresh
    if os.path.exists(ORDERS_CACHE):
        with open(ORDERS_CACHE) as f:
            orders = json.load(f)
        log(f"Loaded {len(orders)} orders from cache.")
    else:
        chunks = [
            ("2026-08-24T00:00:00.000Z", "2026-09-23T22:59:59.999Z"),
            ("2026-09-24T00:00:00.000Z", "2026-10-23T22:59:59.999Z"),
        ]
        orders = []
        for time_from, time_to in chunks:
            log(f"Fetching {time_from} → {time_to}...")
            orders += list_orders(time_from, time_to)
        with open(ORDERS_CACHE, "w") as f:
            json.dump(orders, f)
        log(f"\nTotal orders: {len(orders)} — cached to {ORDERS_CACHE}")

    if not orders:
        log("No orders. Token may be expired — paste a fresh one into TOKEN and retry.")
        exit()

    # Load already-processed order IDs from existing CSV
    done_ids = set()
    fieldnames = [
        "order_id", "placed_at", "status", "order_value", "delivery_type",
        "address", "city", "district", "postcode",
        "pickup_time", "delivery_time", "picked_up_at", "delivered_at",
    ]
    if os.path.exists(output_file):
        with open(output_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                done_ids.add(row["order_id"])
        log(f"Resuming — {len(done_ids)} already done, {len(orders) - len(done_ids)} remaining.")

    with open(output_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not done_ids:
            writer.writeheader()

        for i, order in enumerate(orders):
            order_id  = order["orderId"]
            placed_at = order["placedTimestamp"]
            if order_id in done_ids:
                continue
            log(f"[{i+1}/{len(orders)}] {order_id} ", end="")

            detail = get_order_detail(order_id, placed_at)
            if not detail:
                log("— no detail")
                continue

            o   = detail.get("order", {})
            loc = (o.get("delivery") or {}).get("location") or {}
            ts  = extract_timestamps(detail.get("orderStatuses"))

            writer.writerow({
                "order_id":      order_id,
                "placed_at":     placed_at,
                "status":        o.get("status"),
                "order_value":   o.get("orderValue"),
                "delivery_type": order.get("deliveryType"),
                "address":       loc.get("AddressText"),
                "city":          loc.get("city"),
                "district":      loc.get("district"),
                "postcode":      loc.get("postCode"),
                **ts,
            })
            log(f"— {loc.get('AddressText', 'no address')}")
            time.sleep(3)

    log(f"\nDone. Saved to {output_file}")
