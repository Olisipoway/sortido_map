"""
probe_ubereats_api.py — Explore Uber Eats Marketplace API for Sortido.

Tries the store, delivery-area, and reporting endpoints to see what data
is available without browser scraping. Credentials are read from
ubereats_api_creds.json so they don't end up in git history.

ubereats_api_creds.json format:
{
    "client_id":     "Ovkz-...",
    "client_secret": "rbRO94L1...",
    "store_uuid":    "755282a8-7d8f-51aa-a570-86867606e6c4"
}
"""

import json, urllib.request, urllib.parse, urllib.error, sys

AUTH_URL = "https://auth.uber.com/oauth/v2/token"
BASE     = "https://api.uber.com"

# ── credentials ───────────────────────────────────────────────────────────────

try:
    creds = json.load(open("ubereats_api_creds.json"))
except FileNotFoundError:
    print("ubereats_api_creds.json not found — creating template, fill it in and rerun")
    json.dump({
        "client_id":     "Ovkz-LnATquK7VRuHC9XoEmxFZTOGeTi",
        "client_secret": "rbRO94L1AzRnMdQIBfwHhyoh12wipr4KFmKzQY8d",
        "store_uuid":    "755282a8-7d8f-51aa-a570-86867606e6c4"
    }, open("ubereats_api_creds.json", "w"), indent=2)
    sys.exit(0)

CLIENT_ID     = creds["client_id"]
CLIENT_SECRET = creds["client_secret"]
STORE_UUID    = creds["store_uuid"]

# ── auth ──────────────────────────────────────────────────────────────────────

def get_token(scope="eats.store eats.report"):
    data = urllib.parse.urlencode({
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type":    "client_credentials",
        "scope":         scope,
    }).encode()
    req = urllib.request.Request(
        AUTH_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())["access_token"]
    except urllib.error.HTTPError as e:
        body = e.read()
        print(f"Auth failed {e.code}: {body[:200]}")
        sys.exit(1)

# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _req(token, method, path, payload=None):
    url = BASE + path
    body = json.dumps(payload).encode() if payload else None
    hdrs = {
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
    }
    if body:
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except Exception:
            body = {}
        return body, e.code

def get(token, path):  return _req(token, "GET",  path)
def post(token, path, payload): return _req(token, "POST", path, payload)

# ── probe ─────────────────────────────────────────────────────────────────────

def probe(token, label, method, path, payload=None):
    fn = post if method == "POST" else get
    args = (token, path, payload) if payload else (token, path)
    data, status = fn(*args)
    ok = "✓" if status == 200 else "✗"
    print(f"\n{ok} [{status}] {method} {path}")
    if isinstance(data, dict):
        keys = list(data.keys())
        print(f"  keys: {keys[:12]}")
        if status == 200 and data:
            # Print a compact but readable excerpt
            excerpt = json.dumps(data, indent=2)
            lines = excerpt.split("\n")
            for line in lines[:40]:
                print(f"  {line}")
            if len(lines) > 40:
                print(f"  ... ({len(lines)} lines total)")
        elif status != 200:
            print(f"  error: {json.dumps(data)[:200]}")
    return data, status

def main():
    print("Getting access token...")
    token = get_token()
    print(f"Token: {token[:30]}...\n")

    endpoints = [
        # Store listing — what stores are visible to this app
        ("GET",  f"/v1/eats/stores",                                           None),
        ("GET",  f"/v2/eats/stores",                                           None),

        # Store detail — primary store endpoint
        ("GET",  f"/v1/eats/stores/{STORE_UUID}",                              None),
        ("GET",  f"/v2/eats/stores/{STORE_UUID}",                              None),

        # Hours, special hours, status
        ("GET",  f"/v1/eats/stores/{STORE_UUID}/hours_and_special_hours",      None),
        ("GET",  f"/v1/eats/stores/{STORE_UUID}/status",                       None),

        # Delivery zone / coverage — may or may not exist
        ("GET",  f"/v1/eats/stores/{STORE_UUID}/delivery_areas",               None),
        ("GET",  f"/v1/eats/stores/{STORE_UUID}/delivery_area",                None),
        ("GET",  f"/v1/eats/stores/{STORE_UUID}/coverage",                     None),

        # Reports
        ("GET",  f"/v1/eats/report",                                           None),
        ("POST", f"/v1/eats/report",
         {"store_uuid": STORE_UUID, "report_type": "ORDERS",
          "start_time": "2026-10-01T00:00:00Z", "end_time": "2026-10-30T23:59:59Z"}),
    ]

    results = {}
    for method, path, payload in endpoints:
        data, status = probe(token, "", method, path, payload)
        results[path] = status

    print("\n\n── Summary ──")
    for path, status in results.items():
        mark = "✓" if status == 200 else f"✗ {status}"
        print(f"  {mark}  {path}")

if __name__ == "__main__":
    main()
