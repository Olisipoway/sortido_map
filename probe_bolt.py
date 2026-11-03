"""
probe_bolt.py — Delivery zone sweep for Bolt / Bolt Market.

Queries getSearchScreenContent per grid cell via Bolt's live API.
Session cookies are loaded from bolt_session.json (captured via get_session.py bolt).
Re-run get_session.py bolt when _cfuvid expires (~30 min).

Output appended to zone_snapshots.jsonl.
"""

import json, time, urllib.request, urllib.parse, urllib.error
import argparse
from datetime import datetime

from grid import radial_rings, STOP_RINGS

# ── stores to watch ───────────────────────────────────────────────────────────

WATCH = {
    "sortido":                   186270,
    "bolt_market_arroios":       112233,
    "bolt_market_campo_ourique": 176655,
    "bolt_market_benfica":        35280,
}

# ── session ───────────────────────────────────────────────────────────────────

_cookies = {}
_params  = {}

def _load_session():
    global _cookies, _params
    try:
        with open("bolt_session.json") as f:
            s = json.load(f)
    except FileNotFoundError:
        print("WARNING: bolt_session.json not found — run: /usr/bin/python3 get_session.py bolt")
        return

    _cookies = {ck["name"]: ck["value"] for ck in s["cookies"]}

    for call in s["calls"]:
        if "getSearchScreenContent" in call["url"]:
            p = urllib.parse.urlparse(call["url"])
            raw = urllib.parse.parse_qs(p.query)
            _params = {k: v[0] for k, v in raw.items()
                       if k not in ("delivery_lat", "delivery_lng")}
            break
    else:
        print("WARNING: no getSearchScreenContent call in bolt_session.json — may be stale")

_load_session()

# ── HTTP helper ───────────────────────────────────────────────────────────────

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

def _get(url, timeout=12):
    hdrs = {
        "User-Agent":      UA,
        "Accept":          "application/json",
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
        "Cookie":          "; ".join(f"{k}={v}" for k, v in _cookies.items()),
    }
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as e:
        return {"_error": e.code}, e.code
    except Exception as e:
        return {"_error": str(e)}, 0

# ── probe ─────────────────────────────────────────────────────────────────────

def probe(lat, lon):
    if not _params:
        return []
    params = dict(_params)
    params["delivery_lat"] = lat
    params["delivery_lng"] = lon
    url = ("https://deliveryuser.live.boltsvc.net"
           "/deliveryClient/public/getSearchScreenContent?"
           + urllib.parse.urlencode(params))
    data, status = _get(url)

    if status == 403:
        print("  [Bolt 403 — session expired, re-run: get_session.py bolt]")
        return []
    if status == 429:
        print("  [Bolt 429 — backing off 5 s]")
        time.sleep(5)
        return []

    all_ids = set()
    for cats in data.get("data", {}).get("provider_categories_by_search_tab", {}).values():
        for cat in cats:
            for pid in cat.get("provider_ids", []):
                all_ids.add(pid)

    sortido_id = WATCH.get("sortido")
    serves = sortido_id is not None and sortido_id in all_ids

    eta_min = None
    fee_eur = None
    if serves:
        prov = (data.get("data", {})
                    .get("providers", {})
                    .get("data", {})
                    .get(str(sortido_id)))
        if prov:
            eta_d = (prov.get("eta") or {}).get("delivery") or {}
            lo, hi = eta_d.get("min"), eta_d.get("max")
            if lo is not None and hi is not None:
                eta_min = round((lo + hi) / 2 / 60, 1)
            fee_d = (prov.get("delivery") or {}).get("fee") or {}
            if fee_d.get("value") is not None:
                fee_eur = round(float(fee_d["value"]), 2)

    return serves, eta_min, fee_eur

# ── discovery ─────────────────────────────────────────────────────────────────

DARKSTORE_COORDS = [
    ("bolt_arroios",        38.7201, -9.1376),
    ("bolt_avenidas_novas", 38.7356, -9.1509),
    ("bolt_benfica",        38.7501, -9.1925),
    ("bolt_alcantara",      38.7048, -9.1727),
    ("bolt_campo_ourique",  38.7149, -9.1684),
]

def discover():
    print("Discovering Bolt darkstore provider IDs...\n")
    for key, lat, lon in DARKSTORE_COORDS:
        params = dict(_params)
        params["delivery_lat"] = lat
        params["delivery_lng"] = lon
        url = ("https://deliveryuser.live.boltsvc.net"
               "/deliveryClient/public/getSearchScreenContent?"
               + urllib.parse.urlencode(params))
        data, status = _get(url)
        if status != 200:
            print(f"{key} ({lat},{lon}): HTTP {status}")
            time.sleep(1.5)
            continue

        all_ids = []
        for cats in data.get("data", {}).get("provider_categories_by_search_tab", {}).values():
            for cat in cats:
                all_ids.extend(cat.get("provider_ids", []))

        print(f"{key} ({lat},{lon}):  {len(set(all_ids))} providers total")
        for k, vid in WATCH.items():
            if vid in all_ids:
                print(f"  ✓ {k} (id={vid})")
        time.sleep(1.5)

# ── sweep ─────────────────────────────────────────────────────────────────────

SCHEDULE_HOURS = [7, 10, 13, 16, 20, 23]

def sweep(delay=2.0):
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[{ts}] bolt: radial sweep from Sortido darkstore")

    cells_served = []
    consecutive_empty = 0

    for ring_idx, ring in radial_rings():
        ring_hits = []
        for lat, lon in ring:
            serves, eta_min, fee_eur = probe(lat, lon)
            if serves:
                ring_hits.append([lat, lon, eta_min, fee_eur])
            time.sleep(delay)
        cells_served.extend(ring_hits)
        n = len(ring_hits)
        etas = [c[2] for c in ring_hits if c[2] is not None]
        avg_eta = f"  avg_eta={round(sum(etas)/len(etas),1)}min" if etas else ""
        print(f"  ring {ring_idx:2d} ({ring_idx*0.5:.1f}km): {n}/{len(ring)} hits{avg_eta}")
        if n == 0:
            consecutive_empty += 1
            if consecutive_empty >= STOP_RINGS:
                print(f"  {STOP_RINGS} empty rings → boundary found")
                break
        else:
            consecutive_empty = 0

    with open("zone_snapshots.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "platform": "bolt", "cells": cells_served},
                           separators=(",", ":")) + "\n")
    print(f"  bolt: {len(cells_served)} served cells → zone_snapshots.jsonl")

def run_scheduler():
    print(f"Scheduler active — sweeps at hours: {SCHEDULE_HOURS}")
    while True:
        now = datetime.now()
        if now.hour in SCHEDULE_HOURS and now.minute == 0:
            sweep()
            time.sleep(61)
        time.sleep(30)

def _auto_refresh_session():
    """
    Open food.bolt.eu in a stealth Playwright browser, capture fresh Cloudflare
    cookies, and save them to bolt_session.json. No user interaction needed —
    the browser solves the Cloudflare challenge automatically.
    Returns True on success, False if playwright is unavailable.
    """
    try:
        from playwright.sync_api import sync_playwright
        from playwright_stealth import Stealth
    except ImportError:
        return False

    print("  [Bolt] Auto-refreshing session via browser…")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=False,
                args=["--disable-blink-features=AutomationControlled", "--lang=pt-PT"],
            )
            ctx = browser.new_context(
                locale="pt-PT",
                timezone_id="Europe/Lisbon",
                geolocation={"latitude": 38.7201, "longitude": -9.1376},
                permissions=["geolocation"],
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()
            Stealth().apply_stealth_sync(page)

            # Capture the getSearchScreenContent URL to extract session params
            captured_calls = []
            def on_request(req):
                if "getSearchScreenContent" in req.url:
                    captured_calls.append(req.url)
            ctx.on("request", on_request)

            page.goto("https://food.bolt.eu/pt-pt/", wait_until="domcontentloaded", timeout=30000)
            # Wait for page to settle and Cloudflare cookies to be set
            time.sleep(6)

            cookies = ctx.cookies()
            cf_ok = any(c["name"] in ("_cfuvid", "cf_clearance") for c in cookies)

            # Build the same session format get_session.py uses
            calls_out = []
            for url in captured_calls:
                calls_out.append({"url": url, "method": "GET", "status": 200,
                                   "headers": {}, "req": None, "resp": {}})

            out = {"platform": "bolt", "cookies": cookies, "calls": calls_out}
            with open("bolt_session.json", "w") as f:
                json.dump(out, f, ensure_ascii=False, indent=2)

            browser.close()

        _load_session()
        print(f"  [Bolt] Session refreshed. cf_cookies={'ok' if cf_ok else 'missing'} "
              f"params={'ok' if _params else 'missing'}")
        return cf_ok
    except Exception as e:
        print(f"  [Bolt] Auto-refresh failed: {e}")
        return False


def run_loop(interval_minutes=60):
    import subprocess, sys as _sys
    print(f"[Bolt] Loop: sweep every {interval_minutes} min. Ctrl+C to stop.")
    consecutive_empty = 0
    while True:
        _load_session()
        if not _params:
            print("  [Bolt] No session params — attempting auto-refresh…")
            if not _auto_refresh_session():
                print("  [Bolt] Auto-refresh failed. Run manually: /usr/bin/python3 get_session.py bolt")
                time.sleep(300)
                continue

        t0 = time.time()
        sweep(delay=1.5)

        # Detect session failure: bolt probe returns [] for all cells on 403/429.
        with open("zone_snapshots.jsonl") as fz:
            last_line = fz.readlines()[-1]
        last = json.loads(last_line)
        n = len(last.get("cells", []))
        if last.get("platform") == "bolt" and n < 100:
            consecutive_empty += 1
            print(f"  [Bolt] {n} cells — session expired, auto-refreshing…")
            if not _auto_refresh_session():
                wait_s = min(300 * consecutive_empty, 1800)
                print(f"  [Bolt] Auto-refresh failed. Waiting {wait_s//60} min, then retry.")
                time.sleep(wait_s)
            continue

        consecutive_empty = 0
        subprocess.run([_sys.executable, "build_zone_data.py"], capture_output=True)
        elapsed = time.time() - t0
        wait = max(30, interval_minutes * 60 - elapsed)
        ts_next = datetime.fromtimestamp(time.time() + wait).strftime("%H:%M")
        print(f"  [Bolt] Next sweep at {ts_next} ({wait/60:.1f} min)")
        time.sleep(wait)

# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--discover",  action="store_true",
                        help="Print provider IDs at known darkstore coords")
    parser.add_argument("--sweep",     action="store_true",
                        help="Run one sweep now")
    parser.add_argument("--schedule",  action="store_true",
                        help="Run sweeps at scheduled hours indefinitely")
    parser.add_argument("--loop",      action="store_true",
                        help="Sweep continuously, every --interval minutes")
    parser.add_argument("--interval",  type=int, default=60,
                        help="Loop interval in minutes (default: 60)")
    args = parser.parse_args()

    if args.discover:
        discover()
    elif args.sweep:
        sweep()
    elif args.schedule:
        run_scheduler()
    elif args.loop:
        run_loop(interval_minutes=args.interval)
    else:
        parser.print_help()
