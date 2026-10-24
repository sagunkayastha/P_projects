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

import comfy
import db
import graphs
import layout
import media
import studio

CANCEL: set[int] = set()
_wake = threading.Event()
STATUS = {"comfy": "starting", "job": None}
_family = {"v": None}
KEEP = 20  # references kept per character

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
        return "klein", graphs.klein_edit(p["prompt"], _upload(p["src"]), p["w"], p["h"], p["seed"])
    if kind == "charscore":
        ch = db.get("characters", p["char"])
        cands = db.query("SELECT id, image_id FROM jobs WHERE kind='charref' AND owner=? AND status='done' "
                         "AND image_id IS NOT NULL", (f"char:{ch['id']}",))
        p["cands"] = [c["image_id"] for c in cands]
        return "score", graphs.score(_upload(ch["source_image"]), [_upload(i) for i in p["cands"]])
    raise RuntimeError(f"unknown job kind {kind}")


# ---------- results ----------
def _finish(job, entry):
    imgs, ui = comfy.outputs(entry)
    kind, p = job["kind"], job["params"]
    if kind == "charscore":
        return _finish_score(job, ui)
    if not imgs:
        raise RuntimeError("ComfyUI finished but made no picture")
    data = comfy.view(imgs[-1])
    source = {"image": "chat", "charref": "character", "panel": "panel"}[kind]
    meta = {k: p.get(k) for k in ("seed", "w", "h", "label", "refs") if p.get(k) is not None}
    iid = media.save(data, source, p.get("prompt", ""), job["id"], meta)
    db.update("jobs", job["id"], status="done", image_id=iid, finished=time.time(), progress=1, total=1)
    _after(db.get("jobs", job["id"]))


def _finish_score(job, ui):
    p = job["params"]
    raw = (ui.get("scores") or [None])[0]
    if not raw:
        raise RuntimeError("face check returned nothing")
    res = json.loads(raw)
    items = dict(zip(p["cands"], res["items"]))
    # A picture whose face is clearly less alike than the set's usual face similarity has drifted to another
    # person: never kept. Outfit pictures always stay (whole-picture similarity punishes the new clothes);
    # the other slots go to the angle/expression pictures most like the source.
    fs = sorted(it["face_sim"] for it in items.values() if it.get("face_sim") is not None)
    med = fs[len(fs) // 2] if fs else None
    for iid, it in items.items():
        it["label"] = (db.get("images", iid)["meta"] or {}).get("label", "")
        it["drifted"] = bool(med is not None and it.get("face_sim") is not None and it["face_sim"] < med - 0.15)
        it["score"] = round(it["whole_sim"] - (1.0 if it["drifted"] else 0.0), 4)
    ranked = sorted(items.items(), key=lambda kv: -kv[1]["score"])
    outfits = [iid for iid, it in ranked if it["label"].startswith("outfit-") and not it["drifted"]]
    angles = [iid for iid, it in ranked if not it["label"].startswith("outfit-") and not it["drifted"]]
    keep = outfits[:4] + angles[:KEEP - len(outfits[:4])]
    keep = sorted(keep, key=lambda i: -items[i]["score"])
    scores = {str(iid): it for iid, it in ranked}
    ch = db.get("characters", p["char"])
    db.update("characters", ch["id"], status="ready", refs=keep, scores=scores, error=None)
    db.update("jobs", job["id"], status="done", finished=time.time(), progress=1, total=1)
    _write_character_folder(db.get("characters", ch["id"]))


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


def page_panel_done(pid, idx, job):
    page = db.get("pages", pid)
    if not page:
        return
    panels = page["panels"]
    if panels[idx].get("job_id") != job["id"]:
        return  # an older try of this panel
    if job["status"] == "done":
        panels[idx]["image_id"] = job["image_id"]
    db.update("pages", pid, panels=panels)
    if any(db.get("jobs", p["job_id"])["status"] in ("queued", "running") for p in panels if p.get("job_id")):
        return
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


def run(job):
    jid = job["id"]
    STATUS["job"] = jid
    p = job["params"]
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
        if not any(db.get("jobs", p["job_id"])["status"] in ("queued", "running")
                   for p in page["panels"] if p.get("job_id")):
            compose_page(page["id"])


def start():
    recover()
    threading.Thread(target=loop, daemon=True, name="worker").start()
