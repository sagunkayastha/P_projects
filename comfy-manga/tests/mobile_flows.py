"""End-to-end flows of the manga app in mobile emulation (Galaxy S24-class: 360x780 CSS px, DPR 3, touch).

Run against a TEST instance only (it makes pictures, a character and a page):
  docker run --rm --network host -v $PWD/tests:/t -v <outdir>:/out local/pw-test:1.52 \
      python /t/mobile_flows.py http://127.0.0.1:8290 /out
Screenshots go to <outdir>; prints PASS/FAIL per check and exits 1 on any failure.
"""
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE, OUT = sys.argv[1], sys.argv[2]
RESULTS = []
UA = ("Mozilla/5.0 (Linux; Android 15; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/136.0.0.0 Mobile Safari/537.36")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


def api(path, method="GET", body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"} if body else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r), dict(r.headers)


def shot(page, name):
    page.screenshot(path=f"{OUT}/{name}.png")


def wait_for(fn, timeout=240, every=1.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(every)
    return None


class Touch:
    def __init__(self, page):
        self.cdp = page.context.new_cdp_session(page)

    def ev(self, kind, pts):
        self.cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [
            {"x": x, "y": y, "id": i} for i, (x, y) in enumerate(pts)]})

    def swipe(self, x0, y0, x1, y1, steps=8):
        self.ev("touchStart", [(x0, y0)])
        for k in range(1, steps + 1):
            self.ev("touchMove", [(x0 + (x1 - x0) * k / steps, y0 + (y1 - y0) * k / steps)])
            time.sleep(0.016)
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

    def tap(self, x, y):
        self.ev("touchStart", [(x, y)])
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})

    def pinch(self, cx, cy, d0, d1, steps=8):
        self.ev("touchStart", [(cx - d0, cy), (cx + d0, cy)])
        for k in range(1, steps + 1):
            d = d0 + (d1 - d0) * k / steps
            self.ev("touchMove", [(cx - d, cy), (cx + d, cy)])
            time.sleep(0.016)
        self.cdp.send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})


def last_job(page):
    return page.evaluate("() => { const m = msgs[msgs.length-1]; return m && m.job; }")


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 360, "height": 780}, device_scale_factor=3, is_mobile=True,
                            has_touch=True, user_agent=UA, accept_downloads=True)
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "ERR_FAILED" not in m.text else None)
        t = Touch(page)

        # --- 0. cache-busting + layout
        r = page.goto(BASE + "/")
        html = page.content()
        check("index is no-store", r.headers.get("cache-control") == "no-store")
        check("assets carry a content hash", "/static/app.js?v=" in html and "{{v}}" not in html)
        js = [x for x in html.split('"') if x.startswith("/static/app.js?v=")][0]
        h = urllib.request.urlopen(BASE + js, timeout=30).headers
        check("hashed asset is cached immutable", "immutable" in (h.get("Cache-Control") or ""), h.get("Cache-Control"))
        page.wait_for_selector("#composer")
        time.sleep(1)
        check("no sideways scroll at 360 px", page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        comp = page.locator("#composer").bounding_box()
        check("composer sits at the bottom", abs(comp["y"] + comp["height"] - 780) < 2, str(comp))
        check("text box is 16 px (no zoom on focus)", page.evaluate(
            "getComputedStyle(document.querySelector('#text')).fontSize") == "16px")
        shot(page, "01-chat-start")

        # --- 1. new chat + send: instant pending bubble, then queued/running with progress, then picture
        page.click("#menu")
        page.click("#newchat")
        page.wait_for_timeout(500)
        page.fill("#text", "an old fisherman with a thick beard mending a net on a wooden pier, morning fog")
        t0 = time.time()
        page.click("#send")
        page.wait_for_selector(".msg.pending, .msg[data-id]", timeout=1000)
        check("message shows at once after send", time.time() - t0 < 1.0, f"{time.time() - t0:.2f}s")
        check("text box cleared after send", page.input_value("#text") == "")
        j = wait_for(lambda: (last_job(page) or {}).get("status") == "running" and (last_job(page) or {}).get("total"), 120, 0.3)
        page.wait_for_timeout(300)
        shot(page, "02-chat-progress")
        check("progress shown while drawing", j and page.locator(".bar i").count() > 0)
        done = wait_for(lambda: (last_job(page) or {}).get("status") == "done", 180)
        page.wait_for_timeout(1500)
        check("picture arrives without reload", done and page.locator(".res img").count() >= 1)
        fisher_img = last_job(page)["image_id"]
        shot(page, "03-chat-done")

        # --- 2. keyboard: the layout viewport shrinks (interactive-widget=resizes-content); composer stays visible
        page.set_viewport_size({"width": 360, "height": 420})
        page.focus("#text")
        page.wait_for_timeout(400)
        comp = page.locator("#composer").bounding_box()
        check("composer above the keyboard (420 px tall view)", abs(comp["y"] + comp["height"] - 420) < 2, str(comp))
        shot(page, "04-chat-keyboard")
        page.set_viewport_size({"width": 360, "height": 780})

        # --- 3. reload while a job runs: it is still there and finishes
        page.fill("#text", "a small robot watering flowers on a balcony, close-up")
        page.click("#send")
        wait_for(lambda: (last_job(page) or {}).get("status") in ("queued", "running"), 10, 0.2)
        page.reload()
        page.wait_for_selector(".msg[data-id]")
        j = wait_for(lambda: last_job(page), 10, 0.3)
        check("job still listed after reload", j and j["status"] in ("queued", "running", "done"), str(j and j["status"]))
        done = wait_for(lambda: (last_job(page) or {}).get("status") == "done", 180)
        check("job finished after reload", done)

        # --- 4. send fails (offline): clear error + retry
        page.route("**/api/chats/*/messages", lambda route: route.abort())
        page.fill("#text", "a cat sleeping on a stack of books")
        page.click("#send")
        page.wait_for_selector(".notsent", timeout=5000)
        check("failed send says so and offers retry", "retry" in page.inner_text(".notsent"))
        shot(page, "05-chat-notsent")
        page.unroute("**/api/chats/*/messages")
        page.click(".notsent")
        ok = wait_for(lambda: page.locator(".notsent").count() == 0 and page.locator(".msg.pending").count() == 0, 10, 0.3)
        check("retry sends it", ok)
        n_before = len(api(f"/api/chats/{page.evaluate('chatId')}")[0]["messages"])
        page.evaluate("""async () => {  // same ckey twice (a retry after a lost answer) makes one message
            const k = 'dup-' + Date.now();
            for (let i = 0; i < 2; i++) await fetch(`/api/chats/${chatId}/messages`, {method: 'POST',
              headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: 'dup test, a lighthouse', ckey: k})});
        }""")
        n_after = len(api(f"/api/chats/{page.evaluate('chatId')}")[0]["messages"])
        check("double send is stored once", n_after == n_before + 1, f"{n_before}->{n_after}")
        wait_for(lambda: (last_job(page) or {}).get("status") == "done", 300)

        # --- 5. drawer + back button
        page.click("#menu")
        page.wait_for_timeout(400)
        check("drawer opens", page.evaluate("document.querySelector('#drawer').classList.contains('open')"))
        shot(page, "06-drawer")
        page.go_back()
        page.wait_for_timeout(400)
        check("back closes the drawer", not page.evaluate("document.querySelector('#drawer').classList.contains('open')"))

        # --- 6. gallery: newest first, thumbnails, infinite scroll
        page.click("#menu")
        page.click(".ditem[data-view=gallery]")
        page.wait_for_selector("#grid button img")
        page.wait_for_timeout(1500)
        total = api("/api/images?limit=1")[0]["total"]
        first = page.locator("#grid button").first.get_attribute("data-id")
        newest = str(api("/api/images?limit=1")[0]["items"][0]["id"])
        check("gallery newest first", first == newest, f"{first} vs {newest}")
        src = page.locator("#grid img").first.get_attribute("src")
        check("gallery uses small thumbnails", "/thumb" in src)
        shot(page, "07-gallery")
        for _ in range(8):
            page.evaluate("document.querySelector('#gallery-scroll').scrollTop = 1e9")
            page.wait_for_timeout(600)
        n = page.locator("#grid button").count()
        check("infinite scroll loads all", n == total, f"{n}/{total}")
        page.evaluate("document.querySelector('#gallery-scroll').scrollTop = 0")
        page.wait_for_timeout(300)

        # --- 7. viewer: swipe, double-tap zoom, pinch, download, back closes
        page.locator("#grid button").nth(1).click()
        page.wait_for_selector("#viewer:not([hidden])")
        page.wait_for_timeout(700)
        c0 = page.inner_text("#vcount")
        shot(page, "08-viewer")
        t.swipe(300, 400, 40, 410)
        page.wait_for_timeout(700)
        c1 = page.inner_text("#vcount")
        check("swipe left shows next picture", c1.startswith("3 /"), f"{c0} -> {c1}")
        t.swipe(40, 400, 300, 410)
        page.wait_for_timeout(700)
        check("swipe right goes back", page.inner_text("#vcount").startswith("2 /"))
        t.tap(180, 400)
        page.wait_for_timeout(120)
        t.tap(180, 400)
        page.wait_for_timeout(500)
        tr = page.evaluate("document.querySelectorAll('.vslide')[1].querySelector('img').style.transform")
        check("double-tap zooms in", "scale(2.5)" in tr, tr)
        t.swipe(180, 400, 120, 380)  # pan while zoomed: must not change picture
        page.wait_for_timeout(400)
        check("pan while zoomed keeps the picture", page.inner_text("#vcount").startswith("2 /"))
        shot(page, "09-viewer-zoom")
        t.tap(180, 400)
        page.wait_for_timeout(120)
        t.tap(180, 400)
        page.wait_for_timeout(500)
        t.pinch(180, 400, 40, 120)
        page.wait_for_timeout(300)
        tr = page.evaluate("document.querySelectorAll('.vslide')[1].querySelector('img').style.transform")
        sc = float(tr.split("scale(")[1].split(")")[0]) if "scale(" in tr else 1
        check("pinch zooms", sc > 1.5, tr)
        href = page.get_attribute("#vdl", "href")
        req = urllib.request.urlopen(BASE + href, timeout=30)
        check("download sends the full PNG as a file", "attachment" in req.headers.get("Content-Disposition", "")
              and req.headers.get("Content-Type") == "image/png")
        page.go_back()
        page.wait_for_timeout(500)
        check("back closes the viewer", page.evaluate("document.querySelector('#viewer').hidden")
              and page.evaluate("cur.view") == "gallery")

        # --- 8. make character from the viewer (then stop it: the GPU test set already has two)
        page.locator(f"#grid button[data-id='{fisher_img}']").click()
        page.wait_for_selector("#viewer:not([hidden])")
        page.click("#vchar")
        page.wait_for_selector("#sheet:not([hidden]) input")
        shot(page, "10-make-character")
        FN = f"Fisher {int(time.time()) % 100000}"
        page.fill("#sheet input", FN)
        page.click("#sheet .primary")
        page.wait_for_selector("#toast:not([hidden])")
        check("make character confirms", "Making" in page.inner_text("#toast"), page.inner_text("#toast"))
        page.click("#toast button")
        page.wait_for_timeout(1500)
        check("characters list shows the new one building", FN in page.inner_text("#charlist")
              and "making pictures" in page.inner_text("#charlist"))
        wait_for(lambda: "making pictures · 1" in page.inner_text("#charlist"), 120, 1)
        shot(page, "11-characters-building")
        page.locator(".card", has_text=FN).locator("button.danger").click()
        ok = wait_for(lambda: "stopped" in page.locator(".card", has_text=FN).inner_text(), 60, 1)
        check("stop a character set", ok)

        # --- 9. character detail
        page.locator(".card", has_text="Rin").locator("button", has_text="Open").click()
        page.wait_for_selector("#chardetail .refs img")
        page.wait_for_timeout(1500)
        n = page.locator("#chardetail .refs:not(.dropped) img").count()
        check("character shows its 20 pictures", n == 20, str(n))
        shot(page, "12-character")

        # --- 10. use in chat with the character
        page.locator("#chardetail button", has_text="Use in chat").click()
        page.wait_for_timeout(500)
        check("chat set to draw with Rin", "Rin" in page.inner_text("#charpick"))
        page.fill("#text", "Rin drinks coffee at a small cafe table, looking out the window")
        page.click("#send")
        done = wait_for(lambda: (last_job(page) or {}).get("status") == "done", 300)
        page.wait_for_timeout(1500)
        check("picture with a character", done)
        shot(page, "13-chat-with-character")
        page.click("#charpick")
        page.wait_for_selector("#sheet:not([hidden])")
        page.click("#sheet .ghost")
        page.click("#sheet .primary")
        page.wait_for_timeout(300)
        check("character picker clears", "nobody" in page.inner_text("#charpick"))

        # --- 11. make page
        page.click("#menu")
        page.click(".ditem[data-view=page]")
        page.wait_for_selector("#pagechars .chip")
        page.locator("#pagechars .chip", has_text="Kai").click()
        page.wait_for_timeout(500)
        page.fill("#l1", "Kai sits on a rooftop at sunset, reading a book")
        page.fill("#l2", 'A paper plane hits Kai on the head. "Ow!"')
        page.fill("#l3", "Kai unfolds the paper plane, puzzled")
        page.fill("#l4", 'Kai smiles and looks down at the street. "So it was you."')
        shot(page, "14-page-form")
        n_pages = len(api("/api/pages")[0])
        page.click("#makepage")
        wait_for(lambda: len(api("/api/pages")[0]) > n_pages, 20, 0.5)
        page.wait_for_timeout(1500)
        shot(page, "15-page-working")
        pid = api("/api/pages")[0][0]["id"]
        ok = wait_for(lambda: api(f"/api/pages/{pid}")[0]["status"] == "done", 400, 3)
        page.wait_for_timeout(2500)
        check("page composed", ok)
        page.locator("#pagelist .card").first.scroll_into_view_if_needed()
        shot(page, "16-page-done")
        old_img = api(f"/api/pages/{pid}")[0]["image_id"]
        page.locator("#pagelist .card").first.locator(".panel").nth(1).locator("button").click()
        page.wait_for_timeout(800)
        st = api(f"/api/pages/{pid}")[0]
        check("redo one panel starts", st["status"] == "working")
        ok = wait_for(lambda: api(f"/api/pages/{pid}")[0]["status"] == "done", 300, 3)
        new_img = api(f"/api/pages/{pid}")[0]["image_id"]
        check("redo makes a new page picture", ok and new_img != old_img, f"{old_img}->{new_img}")
        page.wait_for_timeout(2000)
        page.locator("#pagelist .card").first.locator(".pagepic").click()
        page.wait_for_selector("#viewer:not([hidden])")
        page.wait_for_timeout(800)
        shot(page, "17-page-viewer")
        page.go_back()

        check("no JS errors", not errors, "; ".join(errors[:3]))
        ctx.close()

        # --- 12. desktop
        d = b.new_context(viewport={"width": 1280, "height": 800})
        dp = d.new_page()
        dp.goto(BASE + "/#chat")
        dp.wait_for_timeout(2500)
        check("desktop: no sideways scroll", dp.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        shot(dp, "18-desktop-chat")
        dp.goto(BASE + "/#gallery")
        dp.wait_for_timeout(2500)
        shot(dp, "19-desktop-gallery")
        b.close()
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(bad)}/{len(RESULTS)} checks passed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
