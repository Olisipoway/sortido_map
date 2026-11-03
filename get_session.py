import json, sys, time
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

PLATFORMS = {
    "glovo":    "https://glovoapp.com/pt/pt/",
    "bolt":     "https://food.bolt.eu/pt-pt/",
    "ubereats": "https://www.ubereats.com/pt/",
}

# Injected into every page load — intercepts fetch + XHR, stores JSON responses
# in sessionStorage so they survive client-side navigations.
INTERCEPT_JS = """
(function() {
    if (window.__cap_installed) return;
    window.__cap_installed = true;
    if (!sessionStorage.getItem('__cap')) sessionStorage.setItem('__cap', '[]');

    function push(url, method, body, post) {
        try {
            var s = body && body.trim ? body.trim() : '';
            if (!s || s.length < 5) return;
            // Also capture Glovo RSC page fetches (App Router navigation)
            var isGlovoPage = url.indexOf('glovoapp.com') >= 0 &&
                              url.indexOf('_next/static') < 0 &&
                              url.indexOf('_next/image') < 0 &&
                              url.indexOf('.css') < 0 && url.indexOf('.js') < 0 &&
                              url.indexOf('.png') < 0 && url.indexOf('.jpg') < 0;
            if (s[0] !== '{' && s[0] !== '[' && !isGlovoPage) return;
            var arr = JSON.parse(sessionStorage.getItem('__cap') || '[]');
            arr.push({url: url, method: method, body: s.slice(0, 300000), post: post || null});
            sessionStorage.setItem('__cap', JSON.stringify(arr));
        } catch(e) {}
    }

    var origFetch = window.fetch;
    window.fetch = function(input, init) {
        var url    = typeof input === 'string' ? input : (input && input.url) || '';
        var method = (init && init.method) || 'GET';
        var post   = (init && init.body) ? String(init.body).slice(0, 1000) : null;
        return origFetch.apply(this, arguments).then(function(resp) {
            resp.clone().text().then(function(body) { push(url, method, body, post); });
            return resp;
        });
    };

    var oOpen = XMLHttpRequest.prototype.open;
    var oSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function(method, url) {
        this._cm = method; this._cu = url;
        return oOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function(body) {
        var self = this;
        this._cp = body ? String(body).slice(0, 1000) : null;
        this.addEventListener('load', function() {
            push(self._cu, self._cm, self.responseText, self._cp);
        });
        return oSend.apply(this, arguments);
    };
})();
"""

def capture(platform):
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
        ctx.add_init_script(INTERCEPT_JS)
        page = ctx.new_page()
        Stealth().apply_stealth_sync(page)

        print(f"\nOpening {platform} — set address, open store list, press Enter.\n")
        page.goto(PLATFORMS[platform], wait_until="domcontentloaded", timeout=30000)
        input("  [Enter when done] ")
        time.sleep(1)

        # Read intercepted calls from sessionStorage
        raw = page.evaluate("() => sessionStorage.getItem('__cap') || '[]'")
        api_raw = json.loads(raw)
        print(f"  {len(api_raw)} XHR/fetch responses captured")

        # Also grab __NEXT_DATA__ if present
        nd_raw = page.evaluate("() => JSON.stringify(window.__NEXT_DATA__ || null)")
        nd = json.loads(nd_raw) if nd_raw and nd_raw != "null" else None

        captured = []

        if nd:
            print("  [Found window.__NEXT_DATA__]")
            captured.append({"url": "window.__NEXT_DATA__", "method": "GET",
                              "status": 200, "headers": {}, "req": None, "resp": nd})

        for call in api_raw:
            try:
                data = json.loads(call["body"])
            except Exception:
                # Keep raw text for non-JSON glovoapp.com page responses
                if "glovoapp.com" in call["url"] and "api.glovoapp" not in call["url"]:
                    data = {"_raw": call["body"][:5000]}
                else:
                    continue
            req_body = None
            try:
                pd = call.get("post")
                if pd:
                    req_body = json.loads(pd) if pd.strip().startswith("{") else pd
            except Exception:
                pass
            captured.append({
                "url":    call["url"],
                "method": call["method"],
                "status": 200,
                "headers": {},
                "req":    req_body,
                "resp":   data,
            })

        cookies = ctx.cookies()
        out = {"platform": platform, "cookies": cookies, "calls": captured}
        with open(f"{platform}_session.json", "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

        print(f"\n→ {len(cookies)} cookies  |  {len(captured)} calls  →  {platform}_session.json")
        for c in captured:
            print(f"\n  {c['method']} {c['url'][:100]}")
            if c.get("req"):
                print(f"  req: {str(c['req'])[:120]}")
            if isinstance(c["resp"], dict):
                print(f"  resp keys: {list(c['resp'].keys())[:8]}")

        browser.close()

if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else None
    if p in PLATFORMS:
        capture(p)
    else:
        print(f"Usage: /usr/bin/python3 get_session.py [{'|'.join(PLATFORMS)}]")
