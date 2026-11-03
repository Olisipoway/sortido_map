"""
probe_glovo.py — Delivery zone sweep for Glovo / Sortido.

--sweep  : point-in-polygon against decoded coverage polygon (headless, fast, used by launchd).
--browser: Playwright-based in-browser sweep (interactive, per-location, run manually).

Output appended to zone_snapshots.jsonl.
"""

import json, time, urllib.parse, re
import argparse
from datetime import datetime

SORTIDO_STORE_URL = "https://glovoapp.com/pt/pt/lisboa/stores/sortido-lis"

def _get_current_eta(ctx):
    """Fetch Sortido's live ETA from its store page SSR (respects session delivery address).
    Returns float minutes (midpoint of range) or None.
    """
    try:
        resp = ctx.request.get(SORTIDO_STORE_URL, timeout=15000)
        html = resp.text()
        # SSR embeds ETA in <span class="StoreEta_text__Q1xcJ">15-35′</span>
        m = re.search(r'StoreEta_text[^>]+>(\d+)-(\d+)', html)
        if m:
            return round((int(m.group(1)) + int(m.group(2))) / 2.0, 1)
    except Exception as e:
        print(f"  [Glovo] ETA fetch failed: {e}")
    return None

from grid import radial_rings, STOP_RINGS

# ── store IDs ─────────────────────────────────────────────────────────────────

WATCH = {
    "sortido": "566220",
}

# ── polygon sweep (headless) ──────────────────────────────────────────────────

_polygon = None

def _load_polygon():
    global _polygon
    try:
        with open("glovo_zone_polygon.json") as f:
            polys = json.load(f)
        _polygon = polys[4]   # index 4 = main Lisbon metro polygon (315 pts)
    except (FileNotFoundError, IndexError):
        print("WARNING: glovo_zone_polygon.json not found — Glovo probe will always return []")

_load_polygon()

def _point_in_polygon(lat, lon, polygon):
    x, y = lon, lat
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i][0], polygon[i][1]
        yj, xj = polygon[j][0], polygon[j][1]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def probe(lat, lon):
    if _polygon and _point_in_polygon(lat, lon, _polygon):
        return list(WATCH.keys())
    return []

def sweep(delay=0.0):
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    print(f"[{ts}] glovo: radial polygon sweep from Sortido darkstore")

    cells_served = []
    consecutive_empty = 0

    for ring_idx, ring in radial_rings():
        ring_hits = []
        for lat, lon in ring:
            if probe(lat, lon):
                ring_hits.append([lat, lon])
            if delay:
                time.sleep(delay)
        cells_served.extend(ring_hits)
        print(f"  ring {ring_idx:2d} ({ring_idx*0.5:.1f}km): {len(ring_hits)}/{len(ring)} hits")
        if len(ring_hits) == 0:
            consecutive_empty += 1
            if consecutive_empty >= STOP_RINGS:
                print(f"  {STOP_RINGS} empty rings → boundary found")
                break
        else:
            consecutive_empty = 0

    with open("zone_snapshots.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "platform": "glovo", "cells": cells_served},
                           separators=(",", ":")) + "\n")
    print(f"  glovo: {len(cells_served)} cells → zone_snapshots.jsonl")

# ── browser sweep (Playwright, interactive) ───────────────────────────────────

ARROIOS_ADDR = {
    "latitude":    38.7264969,
    "longitude":   -9.1373136,
    "cityCode":    "LIS",
    "countryCode": "PT",
    "cityName":    "Lisboa",
    "text":        "Arroios",
    "details":     "",
    "placeId":     "EiBSdWUgZGUgQXJyb2lvcywgTGlzYm9hLCBQb3J0dWdhbCIuKiwKFAoSCRU63oiZMxkNEX3xpSLj4cjBEhQKEgk78-RhGjMZDRHQNpDkvesABA",
    "isVerified":  True,
}

def _set_glovo_location_ctx(ctx, lat, lon):
    """Write glovo_delivery_address into the context cookie jar (bypasses JS)."""
    addr = dict(ARROIOS_ADDR)
    addr["latitude"]  = lat
    addr["longitude"] = lon
    cookie_value = urllib.parse.quote(json.dumps(addr, separators=(",", ":")), safe="")
    ctx.add_cookies([{
        "name":   "glovo_delivery_address",
        "value":  cookie_value,
        "domain": ".glovoapp.com",
        "path":   "/",
    }])

def _make_browser_ctx(p):
    browser = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled", "--lang=pt-PT"],
    )
    ctx = browser.new_context(
        locale="pt-PT",
        timezone_id="Europe/Lisbon",
        geolocation={"latitude": ARROIOS_ADDR["latitude"], "longitude": ARROIOS_ADDR["longitude"]},
        permissions=["geolocation"],
        viewport={"width": 1280, "height": 900},
        service_workers="block",   # prevent SW cache from leaking location state across pages
    )
    return browser, ctx

# ── browser sniff: intercept Glovo API calls to find location-aware endpoint ──

def sniff_browser():
    """Navigate to Sortido's store page at two locations; print all JSON API calls."""
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    with sync_playwright() as p:
        browser, ctx = _make_browser_ctx(p)
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)

        captured = []

        def on_response(resp):
            url = resp.url
            if "glovoapp.com" not in url:
                return
            ct = resp.headers.get("content-type", "")
            if "json" not in ct:
                return
            try:
                body = resp.json()
                captured.append({"url": url, "status": resp.status, "body": body})
            except Exception:
                pass

        page.on("response", on_response)

        print("Opening Glovo — set delivery address to Arroios via the UI, wait for store list.")
        page.goto("https://glovoapp.com/pt/pt/", wait_until="domcontentloaded", timeout=30000)
        input("\n[Enter when store list is visible] ")
        time.sleep(1)

        probes = [
            ("Arroios (should deliver)", 38.7264969, -9.1373136),
            ("Sintra (should not)",      38.6700,    -9.2800),
        ]

        for label, lat, lon in probes:
            captured.clear()
            ctx.set_geolocation({"latitude": lat, "longitude": lon})
            print(f"\n--- {label} ({lat},{lon}) ---")
            page.goto("https://glovoapp.com/pt/en/store/sortido-arroios/",
                      wait_until="networkidle", timeout=30000)
            time.sleep(2)

            # Also extract __NEXT_DATA__ embedded in the HTML
            next_data = page.evaluate("""() => {
                const el = document.getElementById('__NEXT_DATA__');
                return el ? el.textContent : null;
            }""")
            if next_data:
                nd = json.loads(next_data)
                nd_str = json.dumps(nd)
                avail_kws = ["deliver", "availab", "open", "closed", "zone", "coverage", "unreachable"]
                hits = [kw for kw in avail_kws if kw in nd_str.lower()]
                print(f"  __NEXT_DATA__ ({len(nd_str)} chars) — keywords: {hits or 'none'}")
                if hits:
                    # Print the relevant subtree
                    def _search(obj, depth=0):
                        if depth > 6:
                            return
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if any(kw in str(k).lower() or kw in str(v).lower()
                                       for kw in avail_kws):
                                    print(f"    {'  '*depth}{k}: {json.dumps(v)[:120]}")
                                else:
                                    _search(v, depth+1)
                        elif isinstance(obj, list):
                            for item in obj[:5]:
                                _search(item, depth+1)
                    _search(nd)

            print(f"  {len(captured)} JSON API responses:")
            for c in captured:
                body_str = json.dumps(c["body"])
                avail_kws = ["deliver", "availab", "open", "closed", "zone", "coverage"]
                mark = " ***" if any(kw in body_str.lower() for kw in avail_kws) else ""
                # Always show presearch body regardless of keywords
                is_presearch = "presearch" in c["url"] or "store_wall" in c["url"]
                print(f"  [{c['status']}]{mark} {c['url']}")
                if mark or is_presearch:
                    print(f"    {body_str[:600]}")

            # Test delivery_point_info with explicit lat/lon — no cookie needed.
            # If it returns different data for served vs unserved locations, use it as sweep signal.
            for test_lat, test_lon, test_label in [
                (38.7264969, -9.1373136, "Arroios"),
                (38.6700,    -9.2800,    "Sintra"),
                (38.7500,    -9.1900,    "Benfica"),
            ]:
                try:
                    r = ctx.request.get(
                        f"https://api.glovoapp.com/customer_profile/api/v1/guest/address_book"
                        f"/delivery_point_info?latitude={test_lat}&longitude={test_lon}&countryCode=PT",
                        timeout=10000,
                    )
                    body_str = r.text()
                    print(f"  delivery_point_info({test_label}) → {r.status}  {body_str[:300]}")
                except Exception as e:
                    print(f"  delivery_point_info({test_label}) → error: {e}")

        browser.close()

# ── browser sweep (Playwright, interactive) ───────────────────────────────────

STORE_URL = "https://glovoapp.com/en/pt/store/stores/sortido-arroios"

# Visible-text phrases that indicate Glovo cannot deliver to the address.
# Populated from the --dry-run diagnostic; update if Glovo changes wording.
_UNAVAIL_PHRASES = ()   # filled in after first dry-run

def sweep_browser(delay=0.3, dry_run=False):
    """
    Per-cell availability via full client-side page render.

    Glovo's store page is CSR (no SSR __NEXT_DATA__). The SPA reads the delivery
    address from localStorage. We inject the per-cell address into localStorage
    via add_init_script (runs before the page's own JS), then wait for networkidle
    so the SPA finishes rendering, then read the visible page text.

    --dry-run prints the rendered page text for a few locations so you can
    identify the exact phrase Glovo shows when delivery is unavailable, then
    update _UNAVAIL_PHRASES above.
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    grid = build_grid()
    print(f"Grid: {len(grid)} cells")

    def _addr_init_script(lat, lon):
        """JS init-script: update lat/lon in the localStorage address Glovo set during setup."""
        addr = dict(addr_ls_template)
        addr["latitude"]  = lat
        addr["longitude"] = lon
        addr_json = json.dumps(addr, separators=(",", ":"))
        return f"""(function() {{
            try {{ localStorage.setItem({json.dumps(addr_ls_key)}, {json.dumps(addr_json)}); }} catch(e) {{}}
        }})();"""

    def _check_cell(ctx, lat, lon, debug=False):
        """Open a fresh page, inject the per-cell address, wait for full render, check DOM."""
        page = ctx.new_page()
        page.add_init_script(_addr_init_script(lat, lon))
        Stealth().apply_stealth_sync(page)

        result = False
        try:
            page.goto(STORE_URL, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=8000)

            page_text, current_url = page.evaluate("""() => [
                (document.body.innerText || '').toLowerCase(),
                window.location.href
            ]""")

            if debug:
                _debug_cell(lat, lon, current_url, page_text)

            on_store = "sortido-arroios" in current_url
            if on_store and page_text:
                if _UNAVAIL_PHRASES:
                    result = not any(p in page_text for p in _UNAVAIL_PHRASES)
                else:
                    # _UNAVAIL_PHRASES not yet configured — dry-run to identify them
                    result = False

        except Exception as e:
            if debug:
                print(f"    exception: {e}")
        finally:
            page.close()

        return result

    def _debug_cell(lat, lon, current_url, page_text):
        print(f"    target=({lat},{lon})")
        print(f"    url={current_url}")
        print(f"    on_store={'sortido-arroios' in current_url}")
        if page_text:
            # Print first 400 chars of rendered text + flag known availability keywords
            print(f"    page_text[:400]: {page_text[:400]!r}")
            for kw in ["unreachable", "unavailable", "not deliver", "não conseguimos",
                       "fora da zona", "outside", "add to cart", "adicionar"]:
                if kw in page_text:
                    idx = page_text.index(kw)
                    print(f"    [{kw}] → ...{page_text[max(0,idx-30):idx+80]}...")
        else:
            print("    page_text empty — page may not have loaded")

    with sync_playwright() as p:
        browser, ctx = _make_browser_ctx(p)

        setup_page = ctx.new_page()
        Stealth().apply_stealth_sync(setup_page)
        print("\nOpening Glovo...")
        setup_page.goto("https://glovoapp.com/pt/pt/", wait_until="domcontentloaded", timeout=30000)
        print("→ SET your delivery address to anywhere in Arroios and wait for the store list to load")
        print("  (we need a valid session address so the store page renders properly)")
        input("\n[Enter when store list is visible] ")

        # Capture the localStorage key and value format that Glovo uses for the delivery address.
        # We'll update just the lat/lon per cell but preserve everything else (placeId, cityCode, etc.)
        ls_state = setup_page.evaluate("""() => {
            const res = {};
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                const v = localStorage.getItem(k) || '';
                res[k] = v;
            }
            return res;
        }""")

        addr_ls_key = None
        addr_ls_template = None
        for k, v in ls_state.items():
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict) and "latitude" in parsed and "longitude" in parsed:
                    addr_ls_key = k
                    addr_ls_template = parsed
                    print(f"  Found address in localStorage['{k}']:")
                    print(f"    lat={parsed['latitude']}  lon={parsed['longitude']}")
                    break
            except Exception:
                pass

        if not addr_ls_key:
            print("  WARNING: no latitude/longitude found in localStorage — address injection may not work")
            print("  Keys present:", [k for k in ls_state if '/address' in k.lower() or 'delivery' in k.lower()])
            addr_ls_key = "glovo_delivery_address"
            addr_ls_template = dict(ARROIOS_ADDR)

        time.sleep(1)
        setup_page.close()

        ARROIOS_LAT, ARROIOS_LON = ARROIOS_ADDR["latitude"], ARROIOS_ADDR["longitude"]

        if dry_run:
            probes = [
                ("Arroios (near darkstore)", ARROIOS_LAT, ARROIOS_LON),
                ("Benfica",                  38.7500,     -9.1900),
                ("Sintra",                   38.6700,     -9.2800),
                ("Porto",                    41.1500,     -8.6100),
            ]
            print()
            for label, plat, plon in probes:
                v = _check_cell(ctx, plat, plon, debug=True)
                print(f"  ({'✓' if v else '?'}) {label}")
                print()
            print("─────────────────────────────────────────────────────")
            print("Next step: find the phrase Glovo shows for unavailable locations")
            print("(look at the page_text lines above for Sintra / Porto),")
            print("then set _UNAVAIL_PHRASES in the code and run --browser for the full sweep.")
            browser.close()
            return

        if not _UNAVAIL_PHRASES:
            print("\nERROR: _UNAVAIL_PHRASES is empty. Run --dry-run first to identify the")
            print("       unavailability phrase, update _UNAVAIL_PHRASES, then re-run.")
            browser.close()
            return

        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        cells_served = []
        errors = 0
        t0 = time.time()

        print(f"\n[{ts}] Sweeping {len(grid)} cells...")

        for i, (lat, lon) in enumerate(grid):
            try:
                served = _check_cell(ctx, lat, lon)
            except Exception as e:
                errors += 1
                if errors <= 3:
                    print(f"  [cell {i}] error: {e}")
                continue

            if served:
                cells_served.append([lat, lon, ["sortido"]])

            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                rate = elapsed / (i + 1)
                eta = rate * (len(grid) - i - 1)
                print(f"  {i+1}/{len(grid)}  served={len(cells_served)}"
                      f"  errors={errors}  eta={eta/60:.0f}min")

            if delay:
                time.sleep(delay)

        browser.close()

    with open("zone_snapshots.jsonl", "a", encoding="utf-8") as f:
        line = {"ts": ts, "platform": "glovo", "cells": cells_served}
        f.write(json.dumps(line, separators=(",", ":")) + "\n")

    print(f"\nglovo: {len(cells_served)} cells | {errors} errors → zone_snapshots.jsonl")

# ── presearch-based sweep (Playwright APIRequestContext, per-cell) ────────────

PRESEARCH_URL = "https://api.glovoapp.com/v1/web/store_wall/presearch?handlingType=DELIVERY"
STORE_ID      = "566220"
STORE_V3_URL  = f"https://api.glovoapp.com/v3/stores/{STORE_ID}"

def sweep_presearch(delay=0.5, dry_run=False):
    """
    Per-cell availability via Glovo's presearch endpoint.

    Glovo passes delivery location as custom request headers (glovo-delivery-
    location-latitude / -longitude), NOT in cookies or body. page.evaluate()
    fetch() fails CORS preflight for these non-standard headers.

    Fix: use ctx.request.post() (Playwright's APIRequestContext), which makes
    a direct HTTP request from the context — bypasses CORS, inherits session
    cookies automatically, lets us inject custom headers freely.

    Flow:
      1. Open Glovo in browser, user sets Arroios address.
      2. page.on("request") captures the presearch headers the SPA sends.
      3. Per cell: ctx.request.post(presearch_url, headers={...per-cell lat/lon}).
      4. 200 with popularSearches list → Glovo serves this area.
         Non-200 or error → outside coverage.

    Run --dry-run first to verify the 200 vs 4xx signal holds for
    Arroios (served) vs Sintra / Porto (unserved).
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    with sync_playwright() as p:
        browser, ctx = _make_browser_ctx(p)
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)

        # Intercept the SPA's own presearch requests to steal its session headers.
        # These include glovo-device-urn, glovo-perseus-*, glovo-app-version, etc.
        # We keep all of them except cookie (ctx.request sends cookies automatically).
        captured_headers = {}
        def on_request(req):
            if "presearch" in req.url and req.method == "POST":
                h = {k: v for k, v in req.headers.items()
                     if not k.startswith(":") and k not in ("cookie",)}
                captured_headers.update(h)
                lat = h.get("glovo-delivery-location-latitude", "?")
                lon = h.get("glovo-delivery-location-longitude", "?")
                print(f"  [presearch captured] lat={lat}  lon={lon}  ({len(h)} headers)")

        page.on("request", on_request)

        print("\nOpening Glovo...")
        page.goto("https://glovoapp.com/pt/pt/", wait_until="domcontentloaded", timeout=30000)
        print("→ SET your delivery address to Arroios and wait for the store list to load")
        print("  (presearch headers will be captured automatically when the page fires it)")
        input("\n[Enter when store list is visible] ")

        if not captured_headers:
            print("  No presearch captured yet — navigating to Sortido store page to trigger it...")
            page.goto(STORE_URL, wait_until="domcontentloaded", timeout=15000)
            time.sleep(3)

        if not captured_headers:
            print("\nERROR: Could not capture presearch headers.")
            print("  The Glovo page may not have fired presearch during this session.")
            print("  Run --sniff-address to inspect Glovo's request headers manually.")
            browser.close()
            return

        glovo_hdrs = sorted(k for k in captured_headers if k.startswith("glovo-"))
        print(f"  Captured: {glovo_hdrs}")

        def _make_headers(lat, lon):
            h = dict(captured_headers)
            h["glovo-delivery-location-latitude"]  = str(lat)
            h["glovo-delivery-location-longitude"] = str(lon)
            h["glovo-delivery-location-accuracy"]  = "0"
            h["glovo-delivery-location-timestamp"] = str(int(time.time() * 1000))
            return h

        def _check(lat, lon):
            # GET /v3/stores/{STORE_ID} with location headers:
            # 200 = Sortido delivers here, 404 = outside zone
            try:
                resp = ctx.request.get(STORE_V3_URL, headers=_make_headers(lat, lon), timeout=12000)
                body = None
                try:
                    body = resp.json()
                except Exception:
                    pass
                fee_eur = None
                if resp.status == 200 and body:
                    fee_raw = (body.get("deliveryFeeInfo") or {}).get("fee")
                    if fee_raw is not None:
                        fee_eur = round(float(fee_raw), 2)
                return resp.status, body, fee_eur
            except Exception as e:
                return 0, {"_error": str(e)}, None

        ARROIOS_LAT, ARROIOS_LON = ARROIOS_ADDR["latitude"], ARROIOS_ADDR["longitude"]

        if dry_run:
            eta_min = _get_current_eta(ctx)
            probes = [
                ("Arroios (near darkstore)", ARROIOS_LAT, ARROIOS_LON),
                ("Benfica",                  38.7500,     -9.1900),
                ("Sintra",                   38.6700,     -9.2800),
                ("Porto",                    41.1500,     -8.6100),
            ]
            print(f"\nCurrent ETA from store page: {eta_min}min")
            print()
            for label, plat, plon in probes:
                status, body, fee_eur = _check(plat, plon)
                serves = status == 200
                if serves:
                    msg = f"eta={eta_min}min  fee=€{fee_eur}"
                else:
                    msg = (body or {}).get("error", {}).get("message", "")
                print(f"  {'✓' if serves else '✗'} {label}: HTTP {status}  {msg}")
            print()
            print("✓ = 200 (Sortido delivers here)  ✗ = 404 (outside zone)")
            print("If Arroios=✓ and Sintra=✗ → run without --dry-run for the full sweep.")

            browser.close()
            return

        ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        cells_served = []
        errors = 0
        consecutive_empty = 0
        print(f"\n[{ts}] Glovo: radial sweep from Sortido darkstore")

        for ring_idx, ring in radial_rings():
            ring_hits = []
            for lat, lon in ring:
                status, body, fee_eur = _check(lat, lon)
                if body and "_error" in body:
                    errors += 1
                    if errors <= 3:
                        print(f"  [ring {ring_idx}] error: {body['_error'][:80]}")
                elif status == 200:
                    _set_glovo_location_ctx(ctx, lat, lon)
                    eta_min = _get_current_eta(ctx)
                    ring_hits.append([lat, lon, eta_min, fee_eur])
                if delay:
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

        browser.close()

    with open("zone_snapshots.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "platform": "glovo", "cells": cells_served},
                           separators=(",", ":")) + "\n")
    print(f"\nglovo: {len(cells_served)} cells | {errors} errors → zone_snapshots.jsonl")


def run_loop_presearch(interval_minutes=60, delay=0.5):
    """
    Like sweep_presearch() but keeps the browser open and repeats every
    interval_minutes. Navigates back to the Glovo homepage before each sweep
    to refresh the glovo-perseus-* anti-bot tokens.
    """
    import subprocess, sys as _sys
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    print(f"[Glovo] Loop: sweep every {interval_minutes} min. Ctrl+C to stop.")

    with sync_playwright() as p:
        browser, ctx = _make_browser_ctx(p)
        # Seed delivery address cookie so _get_current_eta() gets real ETA from store page SSR
        _set_glovo_location_ctx(ctx, ARROIOS_ADDR["latitude"], ARROIOS_ADDR["longitude"])
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)

        captured_headers = {}
        def on_request(req):
            if "presearch" in req.url and req.method == "POST":
                h = {k: v for k, v in req.headers.items()
                     if not k.startswith(":") and k not in ("cookie",)}
                captured_headers.update(h)
                lat = h.get("glovo-delivery-location-latitude", "?")
                print(f"  [Glovo headers refreshed] lat={lat}")

        page.on("request", on_request)

        import os
        glovo_session_file = "glovo_headers.json"

        print("\nOpening Glovo…")

        # Load saved headers if available — skips manual setup on restarts.
        if os.path.exists(glovo_session_file):
            with open(glovo_session_file) as sf:
                saved_hdrs = json.load(sf)
            # Sanity check: all values must be strings (not cookies/calls lists)
            if all(isinstance(v, str) for v in saved_hdrs.values()):
                captured_headers.update(saved_hdrs)
            else:
                print("  glovo_headers.json has wrong format — will re-capture from browser")
            print("  Loaded saved Glovo headers — navigating to refresh tokens…")
            page.goto("https://glovoapp.com/pt/pt/", wait_until="domcontentloaded", timeout=30000)
            time.sleep(5)  # presearch fires automatically → updates captured_headers
            if not captured_headers:
                captured_headers.update(saved_hdrs)  # fall back to saved if refresh missed
        else:
            page.goto("https://glovoapp.com/pt/pt/", wait_until="domcontentloaded", timeout=30000)
            print("→ SET your delivery address to Arroios and wait for the store list to load")
            input("\n[Enter when store list is visible] ")

            if not captured_headers:
                page.goto(STORE_URL, wait_until="domcontentloaded", timeout=15000)
                time.sleep(3)

            if not captured_headers:
                print("\nERROR: Could not capture presearch headers.")
                browser.close()
                return

            # Save for future restarts
            with open(glovo_session_file, "w") as sf:
                json.dump(dict(captured_headers), sf, ensure_ascii=False, indent=2)
            print(f"  Headers saved to {glovo_session_file}")

        print(f"  Captured: {sorted(k for k in captured_headers if k.startswith('glovo-'))}")

        def _make_headers(lat, lon):
            h = dict(captured_headers)
            h["glovo-delivery-location-latitude"]  = str(lat)
            h["glovo-delivery-location-longitude"] = str(lon)
            h["glovo-delivery-location-accuracy"]  = "0"
            h["glovo-delivery-location-timestamp"] = str(int(time.time() * 1000))
            return h

        def _check(lat, lon):
            try:
                resp = ctx.request.get(STORE_V3_URL, headers=_make_headers(lat, lon), timeout=12000)
                body = None
                try:
                    body = resp.json()
                except Exception:
                    pass
                fee_eur = None
                if resp.status == 200 and body:
                    fee_raw = (body.get("deliveryFeeInfo") or {}).get("fee")
                    if fee_raw is not None:
                        fee_eur = round(float(fee_raw), 2)
                return resp.status, body, fee_eur
            except Exception as e:
                return 0, {"_error": str(e)}, None

        def _do_sweep():
            ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            cells_served = []
            errors = 0
            consecutive_empty = 0
            print(f"\n[{ts}] Glovo: radial sweep from Sortido darkstore")
            for ring_idx, ring in radial_rings():
                ring_hits = []
                for lat, lon in ring:
                    status, body, fee_eur = _check(lat, lon)
                    if body and "_error" in body:
                        errors += 1
                        if errors <= 3:
                            print(f"  [ring {ring_idx}] error: {body['_error'][:80]}")
                    elif status == 200:
                        _set_glovo_location_ctx(ctx, lat, lon)
                        eta_min = _get_current_eta(ctx)
                        ring_hits.append([lat, lon, eta_min, fee_eur])
                    if delay:
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
            ts, cells_served, errors = _do_sweep()

            with open("zone_snapshots.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": ts, "platform": "glovo", "cells": cells_served},
                                   separators=(",", ":")) + "\n")
            print(f"  glovo: {len(cells_served)} cells | {errors} errors → zone_snapshots.jsonl")

            subprocess.run([_sys.executable, "build_zone_data.py"], capture_output=True)

            elapsed = time.time() - t_cycle
            wait = max(30, interval_minutes * 60 - elapsed)
            ts_next = datetime.fromtimestamp(time.time() + wait).strftime("%H:%M")
            print(f"  [Glovo] Next sweep at {ts_next} ({wait/60:.1f} min) — refreshing headers…")
            time.sleep(wait)

            # Re-navigate to Glovo homepage to capture fresh anti-bot tokens.
            try:
                captured_headers.clear()
                page.goto("https://glovoapp.com/pt/pt/",
                          wait_until="domcontentloaded", timeout=30000)
                time.sleep(5)
                if not captured_headers:
                    print("  WARNING: no fresh headers after re-navigate — using previous ones")
            except Exception as e:
                print(f"  WARNING: header refresh failed ({e}) — using previous headers")

        browser.close()


def sniff_store():
    """
    Visit Sortido's store page at two addresses; capture api.glovoapp.com
    request URLs to identify the store-specific availability endpoint.

    Uses request events only (no response body reads in callbacks — those
    crash with asyncio.CancelledError which is BaseException, not Exception).
    After both interactions, replays GET endpoints with ctx.request to compare
    bodies safely outside the event loop.
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    with sync_playwright() as p:
        browser, ctx = _make_browser_ctx(p)
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)

        arroios_reqs = []
        outzone_reqs = []
        phase = ["arroios"]  # mutable cell so closure sees updates

        def on_request(req):
            if "api.glovoapp.com" not in req.url:
                return
            entry = {
                "url": req.url,
                "method": req.method,
                "headers": {k: v for k, v in req.headers.items()
                            if not k.startswith(":") and k != "cookie"},
            }
            (arroios_reqs if phase[0] == "arroios" else outzone_reqs).append(entry)

        # ctx-level listener catches ALL pages in the context (handles new tabs / SPA navigation)
        ctx.on("request", on_request)

        page.goto("https://glovoapp.com/pt/pt/", wait_until="domcontentloaded", timeout=30000)
        print("Step 1: Set your delivery address to ARROIOS (in Sortido's zone).")
        print("Step 2: Navigate to Sortido's store page (search 'Sortido').")
        print("Step 3: Wait for products to fully load.")
        input("[Enter when Sortido products are visible with Arroios address] ")

        arroios_snap = list(arroios_reqs)
        print(f"\n=== Arroios: {len(arroios_snap)} api.glovoapp.com requests ===")
        for r in arroios_snap:
            print(f"  [{r['method']}] {r['url']}")

        phase[0] = "outzone"
        print("\nStep 4: Change delivery address to somewhere Sortido doesn't reach (e.g. Sintra).")
        print("Step 5: Navigate back to Sortido's store page.")
        print("Step 6: Wait for page to finish loading.")
        input("[Enter when done] ")

        outzone_snap = list(outzone_reqs)
        print(f"\n=== Out-of-zone: {len(outzone_snap)} api.glovoapp.com requests ===")
        for r in outzone_snap:
            print(f"  [{r['method']}] {r['url']}")

        arroios_urls = {r["url"] for r in arroios_snap}
        outzone_urls = {r["url"] for r in outzone_snap}
        only_arroios = arroios_urls - outzone_urls
        only_outzone = outzone_urls - arroios_urls
        in_both = arroios_urls & outzone_urls

        if only_arroios:
            print("\n  Only fired with Arroios (possible served-only endpoints):")
            for url in sorted(only_arroios):
                print(f"    {url}")
        if only_outzone:
            print("\n  Only fired with out-of-zone address:")
            for url in sorted(only_outzone):
                print(f"    {url}")

        # Replay shared GET endpoints with location headers from each phase to compare bodies
        a_hdrs = next((r["headers"] for r in arroios_snap if "glovo-delivery-location-latitude" in r["headers"]), {})
        o_hdrs = next((r["headers"] for r in outzone_snap if "glovo-delivery-location-latitude" in r["headers"]), {})
        glovo_a = {k: v for k, v in a_hdrs.items() if k.startswith("glovo-")}
        glovo_o = {k: v for k, v in o_hdrs.items() if k.startswith("glovo-")}

        if glovo_a and glovo_o and in_both:
            print(f"\n  Replaying {len(in_both)} shared GET URLs to compare bodies...")
            for url in sorted(in_both):
                method = next((r["method"] for r in arroios_snap if r["url"] == url), "GET")
                if method != "GET":
                    continue
                try:
                    ra = ctx.request.get(url, headers=glovo_a, timeout=8000)
                    ro = ctx.request.get(url, headers=glovo_o, timeout=8000)
                    ba, bo = ra.text()[:300], ro.text()[:300]
                    if ra.status != ro.status:
                        print(f"\n  [STATUS {ra.status}→{ro.status}] {url}")
                        print(f"    arroios: {ba}")
                        print(f"    outzone: {bo}")
                    elif ba != bo:
                        print(f"\n  [BODY DIFFERS] [{ra.status}] {url}")
                        print(f"    arroios: {ba}")
                        print(f"    outzone: {bo}")
                except Exception as e:
                    print(f"  replay error {url[:80]}: {e}")

        print(f"\nDone. {len(in_both)} shared, {len(only_arroios)} arroios-only, {len(only_outzone)} outzone-only.")
        browser.close()


def sniff_address():
    """
    Open Glovo, let user set an address, intercept ALL api.glovoapp.com request
    headers (especially for presearch) to find how the delivery address is passed.
    Run this once when the presearch signal seems broken.
    """
    from playwright.sync_api import sync_playwright
    from playwright_stealth import Stealth

    with sync_playwright() as p:
        browser, ctx = _make_browser_ctx(p)
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)

        def on_request(req):
            url = req.url
            if "api.glovoapp.com" not in url:
                return
            headers = dict(req.headers)
            addr_hdrs = {k: v for k, v in headers.items()
                         if any(w in k.lower() for w in
                                ['address', 'delivery', 'location', 'lat', 'lon', 'place', 'city'])}
            if 'presearch' in url or 'store_wall' in url or addr_hdrs:
                print(f"\n[{req.method}] {url}")
                body = None
                try:
                    body = req.post_data
                except Exception:
                    pass
                if body:
                    print(f"  body: {body[:400]}")
                if addr_hdrs:
                    print(f"  address-related headers: {addr_hdrs}")
                if 'presearch' in url:
                    # Print ALL headers for presearch — this is what we need
                    interesting = {k: v for k, v in headers.items()
                                   if not k.startswith(':') and k not in ('user-agent',)}
                    print(f"  presearch headers: {json.dumps(interesting, indent=2)}")

        page.on("request", on_request)

        page.goto("https://glovoapp.com/pt/pt/", wait_until="domcontentloaded", timeout=30000)
        print("Set your delivery address to Arroios.")
        print("Then navigate to the Sortido store page and wait for products to load.")
        print("Watch this terminal for presearch request details.\n")
        input("[Enter when done] ")
        browser.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep",         action="store_true",
                        help="Polygon sweep (headless, fast)")
    parser.add_argument("--browser",       action="store_true",
                        help="Per-page Playwright sweep (slow, mostly for debugging)")
    parser.add_argument("--presearch",     action="store_true",
                        help="One-page presearch sweep — set address in UI, then runs all cells")
    parser.add_argument("--sniff",         action="store_true",
                        help="Intercept Glovo API calls at Arroios+Sintra to find location-aware endpoint")
    parser.add_argument("--sniff-store",   action="store_true",
                        help="Visit Sortido store page at two addresses; show which API calls differ")
    parser.add_argument("--sniff-address", action="store_true",
                        help="Intercept presearch request headers during address setting")
    parser.add_argument("--dry-run",       action="store_true",
                        help="(--browser/--presearch) test a few locations without full sweep")
    parser.add_argument("--loop",          action="store_true",
                        help="Keep browser open, sweep every --interval min")
    parser.add_argument("--interval",      type=int, default=60,
                        help="Loop interval in minutes (default: 60)")
    args = parser.parse_args()

    if args.sniff:
        sniff_browser()
    elif getattr(args, "sniff_store"):
        sniff_store()
    elif getattr(args, "sniff_address"):
        sniff_address()
    elif args.presearch:
        sweep_presearch(dry_run=args.dry_run)
    elif args.loop:
        run_loop_presearch(interval_minutes=args.interval)
    elif args.browser:
        sweep_browser(dry_run=args.dry_run)
    elif args.sweep:
        sweep()
    else:
        parser.print_help()
