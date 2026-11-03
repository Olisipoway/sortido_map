"""
probe_ubereats_browser.py — UberEats zone sweep via in-browser fetch.

Opens a real Chromium browser. After the user sets a Lisbon delivery address
(which establishes valid reCAPTCHA/Cloudflare/PerimeterX tokens), the script
updates the uev2.loc cookie + calls setTargetLocationV1 before each getFeedV1
call, so delivery location varies correctly per grid cell.

Output appended to zone_snapshots.jsonl.
"""

import json, time, re, base64, urllib.parse, random
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

def _parse_eta(data):
    """Extract ETA minutes from getStoreV1 data dict."""
    eta_r = (data.get("etaRange") or {})
    lo, hi = eta_r.get("minMinutes"), eta_r.get("maxMinutes")
    if lo is not None and hi is not None:
        return round((lo + hi) / 2.0, 1)
    text = eta_r.get("text") or ""
    nums = [int(n) for n in re.findall(r'\d+', text)]
    if len(nums) >= 2:
        return round((nums[0] + nums[1]) / 2.0, 1)
    if len(nums) == 1:
        return float(nums[0])
    return None

from grid import radial_rings, STOP_RINGS

# ── store UUIDs to watch ───────────────────────────────────────────────────────

WATCH = {
    "sortido": "755282a8-7d8f-51aa-a570-86867606e6c4",
}

# ── cacheKey builder ──────────────────────────────────────────────────────────

def make_cache_key(lat, lon):
    loc = {"address": {"address1": "", "address2": "", "aptOrSuite": "",
                        "eaterFormattedAddress": "", "subtitle": "", "title": "",
                        "uuid": ""},
           "latitude": lat, "longitude": lon,
           "reference": "", "referenceType": "lat_lng", "type": "lat_lng",
           "addressComponents": {"city": "Lisboa", "countryCode": "PT",
                                 "firstLevelSubdivisionCode": "11", "postalCode": ""}}
    url_encoded = urllib.parse.quote(json.dumps(loc, separators=(",", ":")))
    b64 = base64.b64encode(url_encoded.encode()).decode().rstrip("=")
    return f"{b64}/DELIVERY///0/0//JTVCJTVE/undefined//////HOME////////"

# ── sweep JS: update location then check Sortido specifically via getStoreV1 ──
# getFeedV1 (the full restaurant list) is rate-limited to ~33 calls per session
# by UberEats bot-defense ("bd.error.too_many_requests"). getStoreV1 is a
# single-store endpoint — the same one the catalog scraper uses — and is not
# subject to that limit.
#
# Receives [lat, lon, csrfToken].
# 1. Updates uev2.loc cookie so UberEats backend reads correct location.
# 2. Calls setTargetLocationV1({}) to commit location to server session.
# 3. Calls getStoreV1 for Sortido's UUID specifically.
# Returns the raw getStoreV1 response JSON.

STORE_UUID = "755282a8-7d8f-51aa-a570-86867606e6c4"

SWEEP_JS = """
async ([lat, lon, csrfToken]) => {
    try {
        const locObj = {
            address: {
                address1: "Arroios", address2: "Lisboa", aptOrSuite: "",
                eaterFormattedAddress: "Arroios, Lisboa, Portugal",
                subtitle: "Lisboa", title: "Arroios", uuid: ""
            },
            latitude: lat, longitude: lon,
            reference: "ChIJo1rldpszGQ0RC6R6T9uxjjE",
            referenceType: "google_places", type: "google_places",
            addressComponents: {
                city: "Lisboa", countryCode: "PT",
                firstLevelSubdivisionCode: "11", postalCode: ""
            },
            categories: ["AREAS_AND_BUILDINGS","LANDMARK","geography"],
            originType: "user_autocomplete",
            source: "manual_auto_complete", userState: "Unknown",
            residenceType: ""
        };
        document.cookie = 'uev2.loc=' + encodeURIComponent(JSON.stringify(locObj))
                        + '; path=/; domain=.ubereats.com';

        const stResp = await fetch('/_p/api/setTargetLocationV1?localeCode=pt', {
            method: 'POST',
            headers: {'Content-Type':'application/json','x-csrf-token':csrfToken},
            body: '{}'
        });
        if (!stResp.ok) return {_error: `setTarget ${stResp.status}`};

        // Single-store endpoint — not rate-limited like getFeedV1
        const resp = await fetch('/_p/api/getStoreV1?localeCode=pt', {
            method: 'POST',
            headers: {'Content-Type':'application/json','x-csrf-token':csrfToken},
            body: JSON.stringify({storeUuid: '755282a8-7d8f-51aa-a570-86867606e6c4'})
        });
        const text = await resp.text();
        try { return JSON.parse(text); } catch(e) { return {_raw: text.slice(0,300)}; }
    } catch(e) {
        return {_error: e.toString()};
    }
}
"""

# Sanity-check variants (no location change — tests different body/key formats at
# the already-set Arroios address)
def _make_check_js(body_template):
    return f"""
async ([cacheKey, csrfToken]) => {{
    try {{
        const resp = await fetch('/_p/api/getFeedV1?localeCode=pt', {{
            method: 'POST',
            headers: {{'Content-Type':'application/json','x-csrf-token':csrfToken}},
            body: JSON.stringify({{cacheKey, ...({body_template})}})
        }});
        const text = await resp.text();
        try {{ return JSON.parse(text); }} catch(e) {{ return {{_raw: text.slice(0,300)}}; }}
    }} catch(e) {{
        return {{_error: e.toString()}};
    }}
}}
"""

CHECK_VARIANTS = [
    ("nulls",   _make_check_js(
        '{"feedSessionCount":{"announcementCount":0,"announcementLabel":""},'
        '"userQuery":"","date":null,"startTime":0,"endTime":0,'
        '"carouselId":null,"sortAndFilters":[],"billboardUuid":null,'
        '"feedProvider":null,"promotionUuid":null,"targetingStoreTag":null,'
        '"venueUUID":null,"selectedSectionUUID":null,"favorites":"",'
        '"vertical":null,"searchSource":null,"searchType":null,'
        '"keyName":null,"serializedRequestContext":null,"isUserInitiatedRefresh":false}')),
    ("strings", _make_check_js(
        '{"feedSessionCount":{"announcementCount":0,"announcementLabel":""},'
        '"userQuery":"","date":"","startTime":0,"endTime":0,'
        '"carouselId":"","sortAndFilters":[],"billboardUuid":"",'
        '"feedProvider":"","promotionUuid":"","targetingStoreTag":"",'
        '"venueUUID":"","selectedSectionUUID":"","favorites":"",'
        '"vertical":"","searchSource":"","searchType":"",'
        '"keyName":"","serializedRequestContext":"","isUserInitiatedRefresh":false}')),
    ("minimal", _make_check_js(
        '{"feedSessionCount":{"announcementCount":0,"announcementLabel":""},'
        '"userQuery":"","isUserInitiatedRefresh":false}')),
]

_UUID_RE = re.compile(
    r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
    re.IGNORECASE
)

def extract_store_uuids(resp):
    if not isinstance(resp, dict):
        return set()
    return set(_UUID_RE.findall(json.dumps(resp)))

# ── main sweep ────────────────────────────────────────────────────────────────

def sweep(delay=1.5, dry_run=False):
    grid = build_grid()
    random.shuffle(grid)   # avoid always reaching Arroios at cell ~880 after session drift
    print(f"Grid: {len(grid)} cells (randomised order)")

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

        # Capture POST headers from page's own API calls (for CSRF sniffing)
        captured_post_headers = []
        def on_request(req):
            if "_p/api/" in req.url and req.method == "POST":
                captured_post_headers.append((req.url, dict(req.headers)))
        page.on("request", on_request)

        print("\nOpening UberEats...")
        page.goto("https://www.ubereats.com/pt/", wait_until="domcontentloaded", timeout=30000)
        print("→ Set your delivery address to Arroios, Lisboa")
        print("→ Wait for the store list to fully load")
        input("\n[Enter when store list is visible] ")
        time.sleep(2)

        # ── CSRF token discovery ───────────────────────────────────────────────

        csrf_token = ""

        # 1. Sniff from the page's own POST requests
        for url, hdrs in captured_post_headers:
            for k, v in hdrs.items():
                if "csrf" in k.lower() or "token" in k.lower():
                    csrf_token = v
                    print(f"CSRF from request header: {k} = {v[:40]}")
                    break
            if csrf_token:
                break

        # 2. Try meta tag / window globals
        if not csrf_token:
            from_page = page.evaluate("""() => {
                const m = document.querySelector('meta[name="csrf-token"]');
                if (m) return m.content;
                for (const k of ['__CSRF_TOKEN__', 'csrfToken', '_csrf']) {
                    if (window[k]) return String(window[k]);
                }
                return null;
            }""")
            if from_page:
                csrf_token = from_page
                print(f"CSRF from page HTML: {from_page[:40]}")

        # 3. Fallback: jwt-session httpOnly cookie (readable by Playwright)
        if not csrf_token:
            all_cookies = ctx.cookies()
            jwt = next((c["value"] for c in all_cookies if c["name"] == "jwt-session"), None)
            if jwt:
                csrf_token = jwt
                print(f"CSRF: jwt-session ({jwt[:20]}...)")

        if not csrf_token:
            print("WARNING: CSRF token not found — will try empty string")

        # ── Sanity check: getStoreV1 at Arroios ──────────────────────────────────

        ARROIOS_LAT, ARROIOS_LON = 38.7264969, -9.1373136

        print("\nSanity check at Arroios (getStoreV1)...")
        r0 = page.evaluate(SWEEP_JS, [ARROIOS_LAT, ARROIOS_LON, csrf_token])
        status0 = r0.get("status") if isinstance(r0, dict) else "?"
        d0 = (r0.get("data", {}) or {}) if isinstance(r0, dict) else {}
        closed0 = d0.get("closedMessage", "NOT_FOUND")
        print(f"  status={status0}  closedMessage={closed0!r}")
        if status0 != "success" or closed0 == "NOT_FOUND":
            print(f"  WARNING: {json.dumps(r0)[:150]}")
            ans = input("Continue anyway? [y/N] ").strip().lower()
            if ans != "y":
                browser.close()
                return
        else:
            print(f"  {'✓ delivers here' if not closed0 else '✗ ' + closed0}")

        if dry_run:
            probes = [
                ("Arroios (near darkstore)", ARROIOS_LAT, ARROIOS_LON),
                ("Sintra",                   38.6700,     -9.2800),
                ("Porto",                    41.1500,     -8.6100),
            ]
            print()
            for label, plat, plon in probes:
                r = page.evaluate(SWEEP_JS, [plat, plon, csrf_token])
                status = r.get("status") if isinstance(r, dict) else "?"
                data   = (r.get("data", {}) or {}) if isinstance(r, dict) else {}
                closed = data.get("closedMessage", "NOT_FOUND")
                serves = status == "success" and not closed
                eta_min = _parse_eta(data)
                mark = '✓' if serves else '✗'
                extra = f"  eta={eta_min}min" if serves else ""
                print(f"  {mark} {label}: closedMessage={closed!r}{extra}")
            print()
            print("Arroios=✓ + Sintra/Porto=✗ → sweep is ready.")
            browser.close()
            return

        # ── Full grid sweep ───────────────────────────────────────────────────

        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        cells_served = []
        errors = 0
        unexpected = 0
        sample_unexpected = []
        last_uuid_count = None   # UUID count from the most recent success response

        print(f"\n[{ts}] Sweeping {len(grid)} cells...")

        for i, (lat, lon) in enumerate(grid):
            try:
                resp = page.evaluate(SWEEP_JS, [lat, lon, csrf_token])
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"  [cell {i}] exception: {e}")
                continue

            if isinstance(resp, dict) and resp.get("status") == "success":
                data = resp.get("data", {}) or {}
                # closedMessage='' → delivers here; 'Atualmente indisponível' → doesn't.
                closed = data.get("closedMessage", "x")
                last_uuid_count = len(data.get("catalogSectionsMap", {}))
                if i < 3:
                    print(f"  [cell {i}] ({lat},{lon}) closed={closed!r}")
                if not closed:
                    cells_served.append([lat, lon, _parse_eta(data), None])

            elif isinstance(resp, dict) and resp.get("_error"):
                errors += 1
                if errors <= 3:
                    print(f"  [cell {i}] _error: {resp['_error'][:80]}")

            else:
                unexpected += 1
                if len(sample_unexpected) < 3:
                    snippet = json.dumps(resp)[:120] if isinstance(resp, dict) else str(resp)[:120]
                    sample_unexpected.append(f"cell {i} ({lat},{lon}): {snippet}")

            if (i + 1) % 100 == 0:
                catalog_note = f"  catalog_stores={last_uuid_count}" if last_uuid_count is not None else ""
                print(f"  {i+1}/{len(grid)}  served={len(cells_served)}"
                      f"  errors={errors}  unexpected={unexpected}{catalog_note}")
                if sample_unexpected:
                    for s in sample_unexpected:
                        print(f"    unexpected → {s}")
                    sample_unexpected.clear()

            time.sleep(delay)

        browser.close()

    # Write results
    with open("zone_snapshots.jsonl", "a", encoding="utf-8") as f:
        line = {"ts": ts, "platform": "ubereats", "cells": cells_served}
        f.write(json.dumps(line, separators=(",", ":")) + "\n")

    print(f"\nubereats: {len(cells_served)} cells with served stores | {errors} errors → zone_snapshots.jsonl")


def run_loop(interval_minutes=60, delay=1.5):
    """
    Like sweep() but keeps the browser open and repeats every interval_minutes.
    The CSRF token and UberEats session stay valid for the browser lifetime.
    """
    import subprocess, sys as _sys

    print(f"[UberEats] Loop: sweep every {interval_minutes} min. Ctrl+C to stop.")

    ARROIOS_LAT, ARROIOS_LON = 38.7264969, -9.1373136

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

        captured_post_headers = []
        def on_request(req):
            if "_p/api/" in req.url and req.method == "POST":
                captured_post_headers.append((req.url, dict(req.headers)))
        page.on("request", on_request)

        import os
        session_file = "ubereats_session.json"
        if os.path.exists(session_file):
            with open(session_file) as sf:
                saved = json.load(sf)
            ctx.add_cookies(saved["cookies"])
            print("\n[UberEats] Loaded saved session — opening UberEats…")
            page.goto("https://www.ubereats.com/pt/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)
            # Navigate to Sortido store page to trigger API calls and capture real CSRF token
            page.goto("https://www.ubereats.com/pt/store/sortido/dVKCqH2PVKWW00Y7L9IFMw",
                      wait_until="domcontentloaded", timeout=30000)
            time.sleep(5)
        else:
            print("\nOpening UberEats...")
            page.goto("https://www.ubereats.com/pt/", wait_until="domcontentloaded", timeout=30000)
            print("→ Set your delivery address to Arroios, Lisboa")
            print("→ Wait for the store list to fully load")
            input("\n[Enter when store list is visible] ")
            time.sleep(2)
            saved_out = {"platform": "ubereats", "cookies": ctx.cookies(), "calls": []}
            with open(session_file, "w") as sf:
                json.dump(saved_out, sf, ensure_ascii=False, indent=2)
            print(f"  Session saved to {session_file}")

        def _get_csrf():
            for url, hdrs in captured_post_headers:
                for k, v in hdrs.items():
                    if "csrf" in k.lower() or "x-csrf" in k.lower():
                        return v
            return page.evaluate("""() => {
                const m = document.querySelector('meta[name="csrf-token"]');
                if (m) return m.content;
                for (const k of ['__CSRF_TOKEN__', 'csrfToken', '_csrf']) {
                    if (window[k]) return String(window[k]);
                }
                return null;
            }""") or ""

        csrf_token = _get_csrf()
        if not csrf_token:
            print("WARNING: CSRF token not found — will try empty string")

        # Sanity check
        print("\nSanity check at Arroios...")
        r0 = page.evaluate(SWEEP_JS, [ARROIOS_LAT, ARROIOS_LON, csrf_token])
        status0 = r0.get("status") if isinstance(r0, dict) else "?"
        d0 = (r0.get("data", {}) or {}) if isinstance(r0, dict) else {}
        closed0 = d0.get("closedMessage", "NOT_FOUND")
        print(f"  status={status0}  closedMessage={closed0!r}")
        if status0 != "success" or closed0 == "NOT_FOUND":
            ans = input("Sanity check failed. Continue? [y/N] ").strip().lower()
            if ans != "y":
                browser.close()
                return
        else:
            print("  ✓ delivers here")

        def _do_sweep():
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            cells_served, errors, unexpected = [], 0, 0
            consecutive_empty = 0
            print(f"\n[{ts}] UberEats: radial sweep from Sortido darkstore")
            for ring_idx, ring in radial_rings():
                shuffled = list(ring)
                random.shuffle(shuffled)
                ring_hits = []
                for lat, lon in shuffled:
                    try:
                        resp = page.evaluate(SWEEP_JS, [lat, lon, csrf_token])
                    except Exception as e:
                        errors += 1
                        if errors <= 3:
                            print(f"  [ring {ring_idx}] exception: {e}")
                        continue
                    if isinstance(resp, dict) and resp.get("status") == "success":
                        data = resp.get("data", {}) or {}
                        if not data.get("closedMessage", "x"):
                            ring_hits.append([lat, lon, _parse_eta(data), None])
                    elif isinstance(resp, dict) and resp.get("_error"):
                        errors += 1
                        if errors <= 3:
                            print(f"  [ring {ring_idx}] _error: {resp['_error'][:80]}")
                    else:
                        unexpected += 1
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
            return ts, cells_served, errors

        while True:
            t_cycle = time.time()

            # Refresh CSRF token in case it rotated
            csrf_token = _get_csrf() or csrf_token

            ts, cells_served, errors = _do_sweep()

            with open("zone_snapshots.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": ts, "platform": "ubereats", "cells": cells_served},
                                   separators=(",", ":")) + "\n")
            print(f"  ubereats: {len(cells_served)} cells | {errors} errors → zone_snapshots.jsonl")

            subprocess.run([_sys.executable, "build_zone_data.py"], capture_output=True)

            elapsed = time.time() - t_cycle
            wait = max(30, interval_minutes * 60 - elapsed)
            ts_next = datetime.fromtimestamp(time.time() + wait).strftime("%H:%M")
            print(f"  [UberEats] Next sweep at {ts_next} ({wait/60:.1f} min)")
            time.sleep(wait)

        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true",
                        help="Open browser, sanity-check, test location update — no full sweep")
    parser.add_argument("--loop",     action="store_true",
                        help="Keep browser open, sweep every --interval min")
    parser.add_argument("--interval", type=int, default=60,
                        help="Loop interval in minutes (default: 60)")
    args = parser.parse_args()
    if args.loop:
        run_loop(interval_minutes=args.interval)
    else:
        sweep(dry_run=args.dry_run)
