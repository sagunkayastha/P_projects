"""The one background worker: runs jobs from the on-disk job table, one at a time, through ComfyUI.

Restart-safe: a job's ComfyUI prompt_id + client_id are stored before tracking, so after an app restart
the worker re-attaches to it; if ComfyUI itself was restarted (prompt unknown) the job is submitted again.
Queued jobs simply stay queued. Results are downloaded from ComfyUI and saved in APP_DIR at once.
"""
import hashlib
import json
import os
import random
import threading
import time
import uuid

import base64
import io
import re

import comfy
import db
import gpu
import graphs
import layout
import media
import refs
import studio

CANCEL: set[int] = set()
_wake = threading.Event()
STATUS = {"comfy": "starting", "job": None}
_family = {"v": None}
KEEP = 20  # references kept per character
# Face check rules (SigLIP2 cosine to the SOURCE picture). Measured on test characters 2026-10-24 (STATE-LOG):
FACE_FLOOR = float(os.environ.get("FACE_FLOOR", "0.85"))    # a view whose face is less alike is never kept
WHOLE_FLOOR = float(os.environ.get("WHOLE_FLOOR", "0.90"))  # same, for views with no detectable face
OUTFIT_FLOOR = 0.80  # outfit views: new clothes lower the whole-picture similarity on purpose
PANEL_FACE = float(os.environ.get("PANEL_FACE", "0.45"))    # a panel face below this is someone else
PANEL_WHOLE = float(os.environ.get("PANEL_WHOLE", "0.45"))  # no face and a whole picture below this: nobody there
VISION_MODEL = os.environ.get("LLM_VISION_MODEL", "qwen36")
TRAITS_ASK = ("This is a character design. List the visible traits that must stay the same in every drawing of this "
              "character: age and build, hair (length, style, shade), eyes, glasses or other accessories, face marks, "
              "and each clothing item with its pattern. Plain comma-separated phrases, at most 45 words, no name, "
              "no art-style words, no background.")

# character set: 8 angles x 3 expressions + 4 outfits = 28 pictures; the 20 closest to the source are kept
OUTFITS = studio.OUTFITS + [("sport", "wearing a sports tracksuit and sneakers instead of the usual outfit")]


def char_plan():
    items = [(f"{a}_{e}", f"{ad} The character has a {ed}.") for a, ad in studio.ANGLES for e, ed in studio.EXPRESSIONS]
    items += [(f"outfit-{o}", f"Show the same character in a three-quarter view, calm expression, {od}.")
              for o, od in OUTFITS]
    return items


def seed():
    return random.randrange(1, 2**32)


def wake():
    _wake.set()


def add_job(kind, params, owner):
    jid = db.insert("jobs", kind=kind, status="queued", params=params, owner=owner)
    wake()
    return jid


def cancel(jid):
    job = db.get("jobs", jid)
    if not job:
        return
    if job["status"] == "queued":
        db.update("jobs", jid, status="cancelled", finished=time.time())
        _after(db.get("jobs", jid))
    elif job["status"] == "running":
        CANCEL.add(jid)


# ---------- inputs ----------
def _upload(iid):
    data = media.read(iid)
    return comfy.upload(data, f"app_{hashlib.sha1(data).hexdigest()[:16]}.png")


def _graph(job):
    p = job["params"]
    kind = job["kind"]
    if kind in ("image", "panel"):
        if p.get("refs"):
            names = [_upload(i) for i in p["refs"]]
            return "klein", graphs.klein_refs(p["prompt"], names, p["w"], p["h"], p["seed"])
        return "anima", graphs.anima_bw(p["prompt"], p["w"], p["h"], p["seed"])
    if kind == "charref":
        if p.get("change"):  # the prompt is built now: the trait list may have been written since the job was queued
            ch = db.get("characters", int(job["owner"].split(":")[1]))
            p["prompt"] = studio.edit_prompt("klein9", p["change"], (ch or {}).get("traits") or "")
        return "klein", graphs.klein_edit(p["prompt"], _upload(p["src"]), p["w"], p["h"], p["seed"])
    if kind == "panelcheck":
        return "score", graphs.score(_upload(p["ref"]), [_upload(p["image"])])
    if kind == "charscore":
        ch = db.get("characters", p["char"])
        cands = db.query("SELECT id, image_id FROM jobs WHERE kind='charref' AND owner=? AND status='done' "
                         "AND image_id IS NOT NULL", (f"char:{ch['id']}",))
        p["cands"] = [c["image_id"] for c in cands]
        p["round"] = db.one("SELECT COUNT(*) AS n FROM jobs WHERE owner=? AND kind='charscore' AND status='done'",
                            (f"char:{ch['id']}",))["n"]
        return "score", graphs.score(_upload(ch["source_image"]), [_upload(i) for i in p["cands"]])
    raise RuntimeError(f"unknown job kind {kind}")


# ---------- results ----------
def _finish(job, entry):
    imgs, ui = comfy.outputs(entry)
    kind, p = job["kind"], job["params"]
    if kind == "charscore":
        return _finish_score(job, ui)
    if kind == "panelcheck":
        return _finish_check(job, ui)
    if not imgs:
        raise RuntimeError("ComfyUI finished but made no picture")
    data = comfy.view(imgs[-1])
    source = {"image": "chat", "charref": "character", "panel": "panel"}[kind]
    meta = {k: p.get(k) for k in ("seed", "w", "h", "label", "refs") if p.get(k) is not None}
    iid = media.save(data, source, p.get("prompt", ""), job["id"], meta)
    db.update("jobs", job["id"], status="done", image_id=iid, finished=time.time(), progress=1, total=1)
    _after(db.get("jobs", job["id"]))


def _scores(ui):
    raw = (ui.get("scores") or [None])[0]
    if not raw:
        raise RuntimeError("face check returned nothing")
    return json.loads(raw)


def judge(it, med=None):
    """Is a view/panel too unlike the source? Absolute floors against the SOURCE, plus (for a set) the old
    relative rule: a face clearly below the set's usual similarity has drifted to another person."""
    fs = it.get("face_sim")
    if not refs.ON:  # old rule only
        return bool(med is not None and fs is not None and fs < med - 0.15)
    if fs is not None:
        return fs < FACE_FLOOR or (med is not None and fs < med - 0.15)
    return it.get("whole_sim", 0) < (OUTFIT_FLOOR if it.get("label", "").startswith("outfit-") else WHOLE_FLOOR)


def _finish_score(job, ui):
    p = job["params"]
    res = _scores(ui)
    items = dict(zip(p["cands"], res["items"]))
    fs = sorted(it["face_sim"] for it in items.values() if it.get("face_sim") is not None)
    med = fs[len(fs) // 2] if fs else None
    for iid, it in items.items():
        it["label"] = (db.get("images", iid)["meta"] or {}).get("label", "")
        it["drifted"] = judge(it, med)
        q = it["face_sim"] if refs.ON and it.get("face_sim") is not None else it["whole_sim"] - (0.3 if refs.ON else 0)
        it["score"] = round(q - (1.0 if it["drifted"] else 0.0), 4)
    ch = db.get("characters", p["char"])
    owner = f"char:{ch['id']}"
    # best of 2: a view that drifted is drawn once more with a new seed; the better try of each view is kept
    if refs.ON and p.get("round", 0) == 0 and p.get("retry", True):
        plan = dict(char_plan())
        bad = [it["label"] for it in items.values() if it["drifted"] and it["label"] in plan]
        if bad:
            src = ch["source_image"]
            w, h = studio.SIZE
            db.update("characters", ch["id"], status="building", scores={str(i): it for i, it in items.items()})
            db.update("jobs", job["id"], status="done", finished=time.time(), progress=1, total=1)
            for lb in bad:
                add_job("charref", {"change": plan[lb], "prompt": "", "src": src, "w": w, "h": h, "seed": seed(),
                                    "label": lb, "retry": 1}, owner)
            return
    best = {}
    for iid, it in items.items():
        k = it["label"] or str(iid)
        if k not in best or it["score"] > items[best[k]]["score"]:
            best[k] = iid
    for iid, it in items.items():
        it["spare"] = best.get(it["label"] or str(iid)) != iid  # the weaker try of a view drawn twice
    ranked = sorted(((i, it) for i, it in items.items() if not it["spare"]), key=lambda kv: -kv[1]["score"])
    outfits = [iid for iid, it in ranked if it["label"].startswith("outfit-") and not it["drifted"]]
    angles = [iid for iid, it in ranked if not it["label"].startswith("outfit-") and not it["drifted"]]
    keep = outfits[:4] + angles[:KEEP - len(outfits[:4])]
    keep = sorted(keep, key=lambda i: -items[i]["score"])
    scores = {str(iid): it for iid, it in sorted(items.items(), key=lambda kv: -kv[1]["score"])}
    # the user looks at the set before it is used (keep/drop per view): status "review" until saved
    db.update("characters", ch["id"], status="review" if refs.ON else "ready", refs=keep, scores=scores, error=None)
    db.update("jobs", job["id"], status="done", finished=time.time(), progress=1, total=1)
    if not refs.ON:
        _write_character_folder(db.get("characters", ch["id"]))


def _finish_check(job, ui):
    """A panel that should show a character: is the character there? Else draw it once more by itself."""
    p = job["params"]
    it = _scores(ui)["items"][0]
    if it.get("face_sim") is not None:
        bad, why = it["face_sim"] < PANEL_FACE, "the face does not look like {name}"
    else:
        bad, why = it["whole_sim"] < PANEL_WHOLE, "{name} may be missing"
    db.update("jobs", job["id"], status="done", finished=time.time(), progress=1, total=1)
    pid, idx = p["page"], p["idx"]
    page = db.get("pages", pid)
    if not page:
        return
    panels = page["panels"]
    pn = panels[idx]
    if pn.get("check_id") != job["id"]:
        return
    for v in pn.get("versions", []):
        if v["image_id"] == p["image"]:
            v["check"] = {k: it.get(k) for k in ("face_sim", "whole_sim")} | {"ok": not bad}
    pn.pop("check_id", None)
    if bad and not p.get("auto"):
        prm = dict(db.get("jobs", p["job"])["params"])
        prm.pop("client_id", None)
        prm["seed"] = seed()
        prm["auto"] = 1
        pn["job_id"] = add_job("panel", prm, f"page:{pid}:{idx}")
        pn["warn"] = None
        db.update("pages", pid, panels=panels)
        return
    pn["warn"] = why.format(name=p.get("name", "the character")) + ": check it, ↻ Redo or ✎ Edit" if bad else None
    db.update("pages", pid, panels=panels)
    _maybe_compose(pid)


def _write_character_folder(ch):
    """Mirror a finished character on disk: characters/<slug>/{source.png, refs/NN.png, character.json}."""
    d = db.APP_DIR / "characters" / ch["slug"]
    (d / "refs").mkdir(parents=True, exist_ok=True)
    for x in (d, d / "refs"):
        os.chmod(x, 0o700)
    (d / "source.png").write_bytes(media.read(ch["source_image"]))
    refs = []
    for n, iid in enumerate(ch["refs"] or [], 1):
        row = db.get("images", iid)
        label = (row["meta"] or {}).get("label", "ref")
        name = f"{n:02d}_{label}.png"
        (d / "refs" / name).write_bytes(media.read(iid))
        refs.append({"file": f"refs/{name}", "image_id": iid, "label": label, "prompt": row["prompt"],
                     "score": (ch["scores"] or {}).get(str(iid), {}).get("score")})
    info = {"name": ch["name"], "slug": ch["slug"], "source_image_id": ch["source_image"], "refs": refs,
            "method": "FLUX.2 klein 9B edit of the source picture, 28 made, 20 kept by face similarity (SigLIP2)",
            "made": time.strftime("%Y-%m-%d %H:%M:%S")}
    (d / "character.json").write_text(json.dumps(info, indent=2))


def _after(job):
    """Owner bookkeeping once a job ends (done / failed / cancelled)."""
    owner = job.get("owner") or ""
    if owner.startswith("char:") and job["kind"] == "charref":
        cid = int(owner.split(":")[1])
        left = db.one("SELECT COUNT(*) AS n FROM jobs WHERE owner=? AND kind='charref' AND status IN ('queued','running')",
                      (owner,))["n"]
        if left == 0:
            ch = db.get("characters", cid)
            done = db.one("SELECT COUNT(*) AS n FROM jobs WHERE owner=? AND kind='charref' AND status='done'",
                          (owner,))["n"]
            if ch and ch["status"] == "building":
                if done >= 4:
                    db.update("characters", cid, status="checking")
                    add_job("charscore", {"char": cid}, owner)
                else:
                    db.update("characters", cid, status="failed", error="too few pictures were made")
    elif owner.startswith("char:") and job["kind"] == "charscore" and job["status"] != "done":
        db.update("characters", int(owner.split(":")[1]), status="failed",
                  error=job.get("error") or "face check stopped")
    elif owner.startswith("page:") and job["kind"] == "panel":
        _, pid, idx = owner.split(":")
        page_panel_done(int(pid), int(idx), job)
    elif owner.startswith("page:") and job["kind"] == "panelcheck" and job["status"] != "done":
        _, pid, idx = owner.split(":")
        page = db.get("pages", int(pid))
        if page and page["panels"][int(idx)].get("check_id") == job["id"]:
            page["panels"][int(idx)].pop("check_id", None)
            db.update("pages", int(pid), panels=page["panels"])
            _maybe_compose(int(pid))


def versions(panel):
    """Every picture made for a panel, oldest first: [{image_id, line, quotes}] (pages made before
    versions existed have only their current picture)."""
    vs = list(panel.get("versions") or [])
    if panel.get("image_id") and not any(v["image_id"] == panel["image_id"] for v in vs):
        vs.insert(0, {"image_id": panel["image_id"], "line": panel.get("line", ""), "quotes": panel.get("quotes", [])})
    return vs


def page_panel_done(pid, idx, job):
    page = db.get("pages", pid)
    if not page:
        return
    panels = page["panels"]
    if panels[idx].get("job_id") != job["id"]:
        return  # an older try of this panel
    if job["status"] == "done":
        p = job["params"]
        vs = versions(panels[idx])
        vs.append({"image_id": job["image_id"], "line": p.get("line", panels[idx].get("line", "")),
                   "quotes": p.get("quotes", panels[idx].get("quotes", []))})
        panels[idx]["versions"] = vs
        panels[idx]["image_id"] = job["image_id"]  # the newest try is used; the user can pick an older one
        if p.get("refs") and p.get("check_ref"):
            panels[idx]["check_id"] = add_job("panelcheck", {"page": pid, "idx": idx, "job": job["id"], "image": job["image_id"],
                                                             "ref": p["check_ref"], "name": p.get("check_name"),
                                                             "auto": p.get("auto", 0)}, f"page:{pid}:{idx}")
    db.update("pages", pid, panels=panels)
    _maybe_compose(pid)


def page_busy(page):
    def busy(j):
        return bool(j) and db.get("jobs", j)["status"] in ("queued", "running")
    return any(busy(p.get("job_id")) or busy(p.get("check_id")) for p in page["panels"])


def _maybe_compose(pid):
    page = db.get("pages", pid)
    if page and not page_busy(page):
        compose_page(pid)


def compose_page(pid):
    page = db.get("pages", pid)
    panels = page["panels"]
    pngs = [media.read(p["image_id"]) if p.get("image_id") else None for p in panels]
    if not any(pngs):
        db.update("pages", pid, status="failed", error="no panel was made")
        return
    data = layout.compose(pngs, [p.get("quotes", []) for p in panels])
    iid = media.save(data, "page", " / ".join(page["lines"]), None, {"page": pid})
    missing = sum(1 for x in pngs if not x)
    db.update("pages", pid, image_id=iid, status="done",
              error=f"{missing} panel(s) failed: use Redo on them" if missing else None)
    d = db.APP_DIR / "pages" / f"page-{pid:04d}"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    (d / "page.png").write_bytes(data)
    for i, p in enumerate(panels):
        if p.get("image_id"):
            (d / f"panel-{i + 1}.png").write_bytes(media.read(p["image_id"]))
    (d / "page.json").write_text(json.dumps(db.get("pages", pid), indent=2))


# ---------- the loop ----------
def _next():
    return (db.one("SELECT * FROM jobs WHERE status='running' ORDER BY id LIMIT 1")
            or db.one("SELECT * FROM jobs WHERE status='queued' ORDER BY id LIMIT 1"))


def _progress(jid):
    last = {"t": 0.0}

    def cb(v, m):
        if time.time() - last["t"] > 0.4 or v == m:
            last["t"] = time.time()
            db.update("jobs", jid, progress=v, total=m)
    return cb


def describe(iid):
    """Trait list of a character from its picture by the local vision LLM (through the manga-gpu helper).
    Raises when the LLM is not running."""
    data = gpu.models()
    if not data:
        raise RuntimeError("the local LLM is off")
    from PIL import Image
    im = Image.open(io.BytesIO(media.read(iid))).convert("RGB")
    im.thumbnail((768, 768))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    body = {"model": VISION_MODEL, "temperature": 0.2, "max_tokens": 400,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}},
                {"type": "text", "text": TRAITS_ASK}]}]}
    text = gpu.chat(body)["choices"][0]["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip().strip(".").replace("\n", " ")[:400]


def _traits(job):
    """Trait list at character time, only when the local LLM happens to be running (in drawing mode it is
    off: the user can type the looks, or tap "Describe with AI" in LLM mode)."""
    ch = db.get("characters", job["params"]["char"])
    try:
        text = describe(ch["source_image"])
        if text and not (ch.get("traits") or "").strip():
            db.update("characters", ch["id"], traits=text)
        db.update("jobs", job["id"], status="done", finished=time.time())
    except Exception as e:  # noqa: BLE001 - the set is still made without it
        db.update("jobs", job["id"], status="done", error=f"no trait list: {e}"[:300], finished=time.time())


def run(job):
    jid = job["id"]
    STATUS["job"] = jid
    p = job["params"]
    if job["kind"] == "traits":
        db.update("jobs", jid, status="running", started=time.time())
        return _traits(job)
    if not job.get("prompt_id"):
        family, wf = _graph(job)
        if family != "score" and family != _family["v"]:
            if _family["v"] is not None:
                comfy.free()
            _family["v"] = family
        client = uuid.uuid4().hex
        pid = comfy.submit(wf, client)
        p["client_id"] = client
        db.update("jobs", jid, status="running", prompt_id=pid, params=p, started=time.time(),
                  attempts=(job["attempts"] or 0) + 1, progress=0, total=0)
        job = db.get("jobs", jid)
    try:
        entry = comfy.track(job["prompt_id"], job["params"].get("client_id", uuid.uuid4().hex),
                            cancel_check=lambda: jid in CANCEL, on_progress=_progress(jid))
    except comfy.PromptLost:
        db.update("jobs", jid, status="queued", prompt_id=None)
        return
    _finish(db.get("jobs", jid), entry)


def loop():
    while True:
        if not comfy.alive():
            STATUS["comfy"] = "down"
            db.bump()
            while not comfy.alive():
                time.sleep(3)
            STATUS["comfy"] = "up"
            _family["v"] = None
            db.bump()
        STATUS["comfy"] = "up"
        job = _next()
        if not job:
            STATUS["job"] = None
            _wake.wait(5)
            _wake.clear()
            continue
        jid = job["id"]
        try:
            run(job)
        except comfy.JobCancelled:
            db.update("jobs", jid, status="cancelled", finished=time.time())
            _after(db.get("jobs", jid))
        except Exception as e:  # noqa: BLE001
            j = db.get("jobs", jid)
            if not comfy.alive() and (j["attempts"] or 0) < 4:
                # ComfyUI went away mid-job: keep the job; it re-attaches or is sent again when ComfyUI is back
                time.sleep(3)
                continue
            db.update("jobs", jid, status="failed", error=str(e)[:400] or type(e).__name__, finished=time.time())
            _after(db.get("jobs", jid))
        finally:
            CANCEL.discard(jid)


def recover():
    """After a restart: finish bookkeeping that a crash may have cut short (jobs themselves resume in loop)."""
    active = "status IN ('queued','running')"
    for ch in db.query("SELECT * FROM characters WHERE status IN ('building','checking')"):
        owner = f"char:{ch['id']}"
        if db.one(f"SELECT id FROM jobs WHERE owner=? AND {active}", (owner,)):
            continue
        if ch["status"] == "building":
            last = db.one("SELECT * FROM jobs WHERE owner=? AND kind='charref' ORDER BY id DESC LIMIT 1", (owner,))
            if last:
                _after(last)
        else:
            add_job("charscore", {"char": ch["id"]}, owner)
    for page in db.query("SELECT * FROM pages WHERE status='working'"):
        if not page_busy(page):
            compose_page(page["id"])


def start():
    recover()
    threading.Thread(target=loop, daemon=True, name="worker").start()
