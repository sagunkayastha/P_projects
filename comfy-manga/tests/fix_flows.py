"""Flows for the per-panel fix + character review work (2026-10-24), mobile emulation 360x780, touch.

TEST instance only (uses the test characters "nori" and "bram"; makes a page and one character):
  docker run --rm --network host --ipc=host -u 1000 -v $PWD/tests:/t:ro -v <out>:/out local/pw-test:1.52 \
      python /t/fix_flows.py http://127.0.0.1:8290 /out [page|review|all]
Screenshots + a video go to <out>; PASS/FAIL per check, exit 1 on any failure.
"""
import json
import sys
import time
import urllib.request

from playwright.sync_api import sync_playwright

BASE, OUT = sys.argv[1], sys.argv[2]
WHAT = sys.argv[3] if len(sys.argv) > 3 else "all"
RESULTS = []
UA = ("Mozilla/5.0 (Linux; Android 15; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/136.0.0.0 Mobile Safari/537.36")


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS " if ok else "FAIL ") + name + (f" — {detail}" if detail else ""), flush=True)


def api(path, method="GET", body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def wait_for(fn, timeout=900, every=2.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(every)
    return None


def shot(page, name, full=False):
    page.screenshot(path=f"{OUT}/{name}.png", full_page=full)


def page_done(pid):
    def f():
        pg = api(f"/api/pages/{pid}")
        return pg if pg["status"] != "working" else None
    return f


def flow_page(page):
    page.goto(BASE + "/#page")
    page.wait_for_selector("#pageform")
    page.evaluate("localStorage.setItem('manga-pagechars', '[]')")
    page.reload()
    page.wait_for_selector("#pagechars .chip")
    lines = ["Nori walks into a small cafe on a rainy evening",
             'Bram looks up from behind the counter, smiling. "Welcome back."',
             "close-up: Nori takes off her glasses and wipes the rain off them",
             'Nori and Bram laugh together at the counter. "Same as always?"']
    for i, t in enumerate(lines):
        page.fill(f"#l{i + 1}", t)
    before = len(api("/api/pages"))
    page.click("#makepage")
    page.wait_for_selector(".nochar", timeout=5000)
    on = page.eval_on_selector_all(".nochar .pick button.on", "bs => bs.map(b => b.dataset.slug)")
    check("no character picked: sheet warns and pre-picks the named characters", sorted(on) == ["bram", "nori"], str(on))
    shot(page, "a1-nochar-sheet")
    page.click(".nochar .primary")
    pages = wait_for(lambda: (lambda L: L if len(L) > before else None)(api("/api/pages")), 20)
    pid = pages[0]["id"]
    check("page made with the picked characters", pages[0]["chars"] == ["nori", "bram"] or sorted(pages[0]["chars"]) == ["bram", "nori"], str(pages[0]["chars"]))
    nm = {s: n for s, n in (("nori", "Nori"), ("bram", "Bram"))}
    order = [nm[s] for s in pages[0]["chars"]]
    casts = [sorted(order[k] for k in p["cast"]) for p in pages[0]["panels"]]
    check("detected cast per panel (names in lines)", casts == [["Nori"], ["Bram"], ["Nori"], ["Bram", "Nori"]], str(casts))
    pg = wait_for(page_done(pid))
    check("page finished", pg and pg["image_id"], pg and pg.get("error"))
    page.wait_for_timeout(2500)
    card = page.locator(f'.card[data-page="{pid}"]')
    card.scroll_into_view_if_needed()
    shot(page, "a2-page-card")
    card.locator(".panels").scroll_into_view_if_needed()
    shot(page, "a3-panels")
    check("every panel has Redo + Edit buttons", card.locator(".panel .pbtns .btn").count() == 8)
    shown = card.locator(".panel .n").all_inner_texts()
    check("panel shows who is in it", "Nori" in shown[0] and "Bram" in shown[1] and "Nori" in shown[3] and "Bram" in shown[3], str(shown))
    imgs0 = [p["image_id"] for p in pg["panels"]]
    page0 = pg["image_id"]

    # Redo one panel: only that panel is drawn again, the page is put together again
    card.locator('.panel[data-idx="1"] .pbtns .btn').first.click()
    page.wait_for_timeout(1500)
    shot(page, "a4-redo-running")
    st = api(f"/api/pages/{pid}")
    running = [p["job"]["status"] if p["job"] else None for p in st["panels"]]
    check("Redo starts only that panel", running[1] in ("queued", "running") and all(r == "done" for k, r in enumerate(running) if k != 1), str(running))
    pg = wait_for(page_done(pid))
    imgs1 = [p["image_id"] for p in pg["panels"]]
    check("other panels kept, panel 2 new", imgs1[0] == imgs0[0] and imgs1[2] == imgs0[2] and imgs1[3] == imgs0[3]
          and imgs1[1] != imgs0[1], f"{imgs0} -> {imgs1}")
    check("page put together again", pg["image_id"] != page0)
    check("panel 2 has 2 versions", len(pg["panels"][1]["versions"]) == 2)
    page.wait_for_timeout(2500)
    card.locator('.panel[data-idx="1"]').scroll_into_view_if_needed()
    shot(page, "a5-versions")

    # Pick the old version again
    page1 = pg["image_id"]
    card.locator('.panel[data-idx="1"] .vers button').first.click()
    pg = wait_for(lambda: (lambda x: x if x["panels"][1]["image_id"] == imgs0[1] else None)(api(f"/api/pages/{pid}")), 30)
    check("tap old version: panel goes back, page re-made", pg and pg["image_id"] not in (page0, page1), pg and str(pg["image_id"]))

    # Edit: new line + only Bram in it
    card.locator('.panel[data-idx="2"] .pbtns .btn').nth(1).click()
    page.wait_for_selector("#sheet textarea")
    page.fill("#sheet textarea", "close-up: Bram polishes a cup and frowns")
    on = page.eval_on_selector_all("#sheet .chip.on", "bs => bs.map(b => b.textContent)")
    check("Edit: chips follow the names in the new line", on == ["Bram"], str(on))
    shot(page, "a6-edit-sheet")
    page.click("#sheet .primary")
    page.wait_for_timeout(1000)
    st = api(f"/api/pages/{pid}")
    p2 = st["panels"][2]
    check("Edit: line, cast and prompt changed", p2["line"].startswith("close-up: Bram") and [st["chars"][k] for k in p2["cast"]] == ["bram"]
          and "Bram is the person" in p2["prompt"] and "Nori" not in p2["prompt"], p2["prompt"][:120])
    pg = wait_for(page_done(pid))
    check("edited panel drawn, page re-made", pg["panels"][2]["image_id"] != imgs0[2])
    page.wait_for_timeout(2500)
    card.scroll_into_view_if_needed()
    shot(page, "a7-after-edit")
    card.locator(".panels").scroll_into_view_if_needed()
    shot(page, "a8-after-edit-panels")
    return pid


def flow_chat(page):
    page.goto(BASE + "/#chat")
    page.wait_for_selector("#composer")
    btn = page.locator(".msg .acts .btn", has_text="Edit").first
    if not btn.count():
        check("chat has an Edit button", False, "no finished chat picture in test data")
        return
    btn.scroll_into_view_if_needed()
    btn.click()
    v = page.input_value("#text")
    check("chat Edit puts the message back in the box", len(v) > 10, v[:60])
    shot(page, "a9-chat-edit")
    page.fill("#text", "")
    page.evaluate("localStorage.setItem('manga-draft', '\"\"')")


def flow_review(page):
    c = api("/api/characters", "POST", {"image_id": 1, "name": "Nori Two"})
    cid = c["id"]
    c = wait_for(lambda: (lambda x: x if x["status"] in ("review", "failed", "ready") else None)(api(f"/api/characters/{cid}")), 1800, 5)
    check("new character stops at review (not used before the user saves)", c and c["status"] == "review", c and c["status"])
    if not c or c["status"] != "review":
        return
    page.goto(BASE + f"/#chars")
    page.wait_for_selector("#charlist .card")
    shot(page, "b4-1-list")
    page.locator("#charlist .btn", has_text="Check & save").first.click()
    page.wait_for_selector(".rvgrid .rv")
    shot(page, "b4-2-review")
    n_on = page.locator(".rv.on").count()
    page.locator(".rv.on").first.click()
    check("tap drops a view", page.locator(".rv.on").count() == n_on - 1)
    page.locator(".review textarea").scroll_into_view_if_needed()
    page.fill(".review textarea", (c.get("traits") or "short black bob, round glasses, striped scarf, long cardigan"))
    shot(page, "b4-3-review-bottom")
    page.locator(".review .primary").click()
    c2 = wait_for(lambda: (lambda x: x if x["status"] == "ready" else None)(api(f"/api/characters/{cid}")), 20)
    check("Save makes it ready with the kept views", c2 and len(c2["refs"]) == n_on - 1, c2 and str(len(c2["refs"])))
    check("looks saved", c2 and c2.get("traits"))
    page.wait_for_timeout(1500)
    shot(page, "b4-4-ready")


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 360, "height": 780}, device_scale_factor=3, is_mobile=True, has_touch=True,
                         user_agent=UA, record_video_dir=OUT, record_video_size={"width": 360, "height": 780})
    pg = ctx.new_page()
    if WHAT in ("page", "all"):
        flow_page(pg)
        flow_chat(pg)
    if WHAT in ("review", "all"):
        flow_review(pg)
    ctx.close()
    br.close()

bad = [r for r in RESULTS if not r[1]]
print(f"{len(RESULTS) - len(bad)}/{len(RESULTS)} passed")
sys.exit(1 if bad else 0)
