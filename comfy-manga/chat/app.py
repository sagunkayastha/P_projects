"""Manga maker: chat -> pictures, characters from any picture, 4-panel pages. Mobile first, fully local.

FastAPI app; ComfyUI runs in its own container (COMFY_URL). Everything is stored on disk in APP_DIR
(~/Documents/Personal/manga/app): SQLite (chats, jobs, images, characters, pages) + image files.
"""
import asyncio
import contextvars
import hashlib
import os
import re
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

import db
import director
import gpu as gpuhelper
import graphs
import layout
import media
import pages as pagejobs
import refs as refpick
import studio
import worker
import writer

STATIC = Path(__file__).resolve().parent / "static"
ASSETS = ("app.js", "app.css")


def _version():
    h = hashlib.sha1()
    for name in ASSETS:
        h.update((STATIC / name).read_bytes())
    return h.hexdigest()[:10]


VERSION = _version()


def _import_dirs():
    for d in [x for x in os.environ.get("IMPORT_DIRS", "").split(":") if x]:
        if Path(d).is_dir():
            try:
                media.import_folder(d)
            except Exception as e:  # noqa: BLE001 - never block startup on an import
                print(f"import {d} failed: {e}", flush=True)


@asynccontextmanager
async def lifespan(app):
    db.init()
    director.init()
    worker.start()
    threading.Thread(target=_import_dirs, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def cache_rules(request: Request, call_next):
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/static/"):
        # index.html asks for /static/x?v=<content hash>: safe to cache for ever; anything else must revalidate
        resp.headers["Cache-Control"] = ("public, max-age=31536000, immutable" if request.query_params.get("v")
                                         else "no-cache")
    else:
        # no-store for everything else, pictures too: picture ids start at 1 again in a fresh (private) store,
        # so a cached /api/images/1 would show an old picture
        resp.headers["Cache-Control"] = "no-store"
    return resp


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def index():
    html = (STATIC / "index.html").read_text().replace("{{v}}", VERSION).replace("{{store}}", db.STORE)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


# ---------- live updates ----------
@app.get("/api/wait")
async def wait(since: int = -1):
    """Long poll: returns as soon as anything changed (or after ~25 s)."""
    loop = asyncio.get_running_loop()
    rev = await loop.run_in_executor(None, db.wait, since, 25.0)
    return {"rev": rev, "comfy": worker.STATUS["comfy"], "version": VERSION, "queue": _queue_count()}


def _queue_count():
    return db.one("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued','running')")["n"]


# ---------- shapes / jobs ----------
def _job_view(jid):
    j = db.get("jobs", jid) if jid else None
    if not j:
        return None
    out = {k: j[k] for k in ("id", "kind", "status", "progress", "total", "error", "image_id", "started", "finished")}
    if j["status"] == "queued":
        out["ahead"] = db.one("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued','running') AND id<?",
                              (jid,))["n"]
    if j["image_id"]:
        img = db.get("images", j["image_id"])
        out["w"], out["h"] = img["w"], img["h"]
    if j["params"].get("used"):
        out["used"] = j["params"]["used"]
    return out


@app.post("/api/jobs/{jid}/cancel")
def cancel_job(jid: int):
    if not db.get("jobs", jid):
        raise HTTPException(404, "no such job")
    worker.cancel(jid)
    return {"ok": True}


# ---------- queue (what the GPU is doing and what waits) ----------
def _what(j):
    p, kind, owner = j["params"] or {}, j["kind"], j["owner"] or ""
    if kind == "image":
        return "Chat picture: " + (p.get("text") or "")[:50]
    if kind == "panel":
        return f"Page {p.get('page')} · panel {(p.get('idx') or 0) + 1}" + (" (auto redo)" if p.get("auto") else "")
    if kind == "panelcheck":
        return f"Page {p.get('page')} · panel {(p.get('idx') or 0) + 1} · face check"
    if kind == "scene":
        return f"Page {p.get('page')} · " + {"plate": "place picture", "props": "objects picture"}.get(p.get("kind"), "scene")
    if kind in ("charref", "charscore", "traits"):
        ch = db.get("characters", int(owner.split(":")[1])) if owner.startswith("char:") else None
        name = ch["name"] if ch else "character"
        return {"charref": f"{name} · view {(p.get('label') or '').replace('_', ' ')}" + (" (2nd try)" if p.get("retry") else ""),
                "charscore": f"{name} · face check", "traits": f"{name} · looks in words"}[kind]
    return kind


@app.get("/api/queue")
def queue():
    rows = db.query("SELECT * FROM jobs WHERE status IN ('queued','running') ORDER BY status='running' DESC, id LIMIT 200")
    return [{"id": j["id"], "status": j["status"], "progress": j["progress"], "total": j["total"], "what": _what(j),
             "started": j["started"]} for j in rows]


# ---------- chats ----------
@app.get("/api/chats")
def chats():
    return db.query("SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.chat_id=c.id) AS n "
                    "FROM chats c ORDER BY c.id DESC LIMIT 200")


@app.post("/api/chats")
def new_chat():
    cid = db.insert("chats", title="")
    return db.get("chats", cid)


def _msg_view(m):
    return {**m, "job": _job_view(m["job_id"])}


@app.get("/api/chats/{cid}")
def chat(cid: int):
    c = db.get("chats", cid)
    if not c:
        raise HTTPException(404, "no such chat")
    msgs = db.query("SELECT * FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 200", (cid,))[::-1]
    return {"chat": c, "messages": [_msg_view(m) for m in msgs]}


def _ready_chars(slugs):
    out = []
    for s in (slugs or [])[:2]:
        ch = db.one("SELECT * FROM characters WHERE slug=?", (s,))
        if not ch or ch["status"] != "ready":
            raise HTTPException(400, f"character '{s}' is not ready")
        out.append(ch)
    return out


def _cast(chars, text):
    """(reference specs, cast dicts for writer.cast_text) for the characters in one picture."""
    return pagejobs.char_refs(chars, text)


SKETCH = ("Image 1 is the user's rough sketch: keep its layout, camera, framing, poses and where everything is, and "
          "turn it into a finished, clean drawing{what}. Confident clean lines, correct anatomy and proportions; no "
          "sketch lines, no construction lines, no pencil smudges, nothing stays rough.")


_STYLE = contextvars.ContextVar("style", default="bw")
# chat looks: B/W manga (default, pages always), colour, and two colour layouts with room for a title
LOOKS = {"bw": "", "colour": "",
         "cover": " Manga volume cover: the character large in the lower two-thirds, a clean empty area across the "
                  "top third for the title, no text.",
         "chapter": " Chapter title splash: a wide cinematic scene with the characters and the place, an empty area on "
                    "one side for the chapter title, no text."}


def _add_image(params, owner):
    """worker.add_job for chat pictures; colour looks add the colour flag (graphs.colourize at run time)."""
    if _STYLE.get() != "bw":
        params["colour"] = True
    return worker.add_job("image", params, owner)


def _sketch_job(text, sketch, chars, owner, seed=None, model="klein"):
    """One finished picture from the user's sketch (klein, the sketch as image 1, keep its layout)."""
    row = db.get("images", sketch)
    w, h = graphs.fit_size(min(2.0, max(0.5, row["w"] / row["h"])), 1.0)
    refs, cast = _cast(chars, text) if chars else ([], [])
    what = f" of: {text.strip().rstrip('.')}" if text.strip() else ""
    who = f" {writer.cast_text(cast, start=2)} Same face, hair and clothes as the reference sheets." if chars else ""
    once = f" {pagejobs.once_text([c['name'] for c in chars])}" if chars else ""
    prompt = (f"{SKETCH.format(what=what)}{who}{once} {pagejobs.ONE} {graphs.STYLE} "
              "No text, no letters, no speech bubbles.").replace("  ", " ")
    params = {"prompt": prompt, "text": text, "w": w, "h": h, "seed": seed or worker.seed(), "refs": [sketch] + refs,
              "sketch": sketch}
    if model == "qwen":  # Qwen-Image-Edit: inputs are "Picture 1, 2, 3", at most 3
        params.update(model="qwen", prompt=prompt.replace("Image ", "Picture ").replace("image ", "Picture "),
                      refs=params["refs"][:3])
    if chars:
        params["chars"] = [c["slug"] for c in chars]
    return _add_image(params, owner)


# Modify of a finished picture (image 1): a change to it, or a new picture of the same character(s)
EDIT = {"small": "Edit image 1, a finished picture. Change: {what}. Keep everything the change does not name exactly as in "
                 "image 1: the same person, face, style and background.",
        "new": "Image 1 shows the character: keep their face, hair and clothes exactly as in image 1. Draw a new picture of "
               "them: {what}. New pose and new camera; do not copy the pose or framing of image 1."}


def _edit_job(text, src, edit, chars, owner, seed=None, model="klein"):
    """Modify: klein or Qwen-Image-Edit with the picture as image 1 (and character sheets after it)."""
    row = db.get("images", src)
    w, h = graphs.fit_size(min(2.0, max(0.5, row["w"] / row["h"])), 1.0)
    refs, cast = _cast(chars, text) if chars else ([], [])
    who = f" {writer.cast_text(cast, start=2)} Same face, hair and clothes as the reference sheets." if chars else ""
    prompt = (f"{EDIT[edit].format(what=text.strip().rstrip('.'))}{who} {pagejobs.ONE} {graphs.STYLE} "
              "No text, no letters, no speech bubbles.").replace("  ", " ")
    params = {"prompt": prompt, "text": text, "w": w, "h": h, "seed": seed or worker.seed(), "refs": [src] + refs,
              "sketch": src, "edit": edit}
    if model == "qwen":  # Qwen names its inputs "Picture 1, 2, 3" and takes at most 3
        params.update(model="qwen", prompt=prompt.replace("image ", "Picture ").replace("Image ", "Picture "),
                      refs=params["refs"][:3])
    if chars:
        params["chars"] = [c["slug"] for c in chars]
    return _add_image(params, owner)


def _anima_job(text, shape, chars, owner, seed=None, sketch=None, model="anima", scribble=False):
    """Anima (trained on scraped anime art; the user's choice): text only, or steered by the sketch (lineart
    control) and the first character's picture (IP-Adapter: the face drifts more than with klein)."""
    if sketch:
        row = db.get("images", sketch)
        w, h = graphs.fit_size(min(2.0, max(0.5, row["w"] / row["h"])), 1.0)
    else:
        w, h = graphs.SHAPES.get(shape, graphs.SHAPES["tall"])
    looks = "; ".join(f"{c['name']}: {c['traits']}" for c in chars if c.get("traits"))
    prompt = (text or "the scene in the sketch") + (f", {looks}" if looks else "") + ", detailed manga illustration"
    params = {"prompt": prompt, "text": text, "w": w, "h": h, "seed": seed or worker.seed(), "model": model}
    if sketch:
        params["sketch"] = sketch
        if scribble:
            params["scribble"] = True
    if chars:
        params["ipref"] = chars[0]["source_image"]
        params["chars"] = [c["slug"] for c in chars]
    return _add_image(params, owner)


def _chat_job(text, shape, chars, owner, seed=None, sketch=None, model="klein", edit=None, style="bw"):
    """Chat picture in the chosen look: B/W (default) or colour; cover / chapter add a layout with title room."""
    style = style if style in LOOKS else "bw"
    if style in ("cover", "chapter") and not edit:
        text = f"{text.strip().rstrip('.') or 'the characters'}.{LOOKS[style]}"
        if not sketch:
            shape = "tall" if style == "cover" else "wide"
    tok = _STYLE.set(style)
    try:
        return _chat_job1(text, shape, chars, owner, seed, sketch, model, edit)
    finally:
        _STYLE.reset(tok)


def _chat_job1(text, shape, chars, owner, seed=None, sketch=None, model="klein", edit=None):
    if model in graphs.UNETS:  # Anima (beretMix) or Manga Vision
        return _anima_job(text, shape, chars, owner, seed, sketch, model)
    if model == "q21" and sketch:  # Qwen-Image 2.1 + Fun ControlNet Union on the sketch (test 2026-10-26: 0.6 / 50%)
        row = db.get("images", sketch)
        w, h = graphs.fit_size(min(2.0, max(0.5, row["w"] / row["h"])), 1.0)
        return _add_image({"prompt": f"{text.strip().rstrip('.') or 'the scene in the sketch'}. {graphs.STYLE}",
                                        "text": text, "w": w, "h": h, "seed": seed or worker.seed(), "sketch": sketch,
                                        "model": "q21", "strength": 0.6, "end": 0.5,
                                        "neg": "colour, blurry, low quality, text, watermark"}, owner)
    if model == "scribble" and sketch:  # Anima + Scribble Control LoRA (sketch only)
        return _anima_job(text, shape, chars, owner, seed, sketch, "anima", scribble=True)
    if sketch and edit in EDIT and text.strip():
        return _edit_job(text, sketch, edit, chars, owner, seed, model)
    if sketch:
        return _sketch_job(text, sketch, chars, owner, seed, model)
    w, h = graphs.SHAPES.get(shape, graphs.SHAPES["tall"])
    if chars:
        refs, cast = _cast(chars, text)
        if model == "qwen":  # Qwen-Edit takes at most 3 pictures: one reference per character
            one, k = [], 0
            for c in cast:
                one.append(refs[k]); k += c.get("n", 2); c["n"] = 1
            refs = one[:3]
        keep = "face, hair and clothes" if refpick.CONT else "face, hair, body and outfit"
        pose = (" Draw a new pose that fits the text; do not copy the pose or framing of the reference pictures. "
                + pagejobs.ONE) if refpick.CONT else ""
        prompt = (f"{writer.cast_text(cast)} {text}. Keep each character's {keep} exactly as in the reference "
                  f"pictures.{pose} {graphs.STYLE} No text, no letters, no speech bubbles.")
        params = {"prompt": prompt, "text": text, "w": w, "h": h, "seed": seed or worker.seed(), "refs": refs,
                  "chars": [c["slug"] for c in chars]}
    else:  # text only: klein draws it from words (before the model choice, Anima drew these)
        params = {"prompt": f"{text.strip().rstrip('.')}. {pagejobs.ONE} {graphs.STYLE} No text, no letters, no speech "
                            f"bubbles.", "text": text, "w": w, "h": h, "seed": seed or worker.seed(), "model": "klein"}
    if model == "qwen":  # Qwen-Image-Edit drawing from words (+ one picture per character)
        params.update(model="qwen", prompt=params["prompt"].replace("image ", "Picture "), refs=params.get("refs", []))
    return _add_image(params, owner)


@app.post("/api/chats/{cid}/messages")
def send(cid: int, body: dict = Body(...)):
    c = db.get("chats", cid)
    if not c:
        raise HTTPException(404, "no such chat")
    text = (body.get("text") or "").strip()
    sketch = body.get("sketch")
    if sketch is not None and not (isinstance(sketch, int) and db.get("images", sketch)):
        raise HTTPException(400, "that sketch is gone; add it again")
    if not text and not sketch:
        raise HTTPException(400, "empty message")
    if len(text) > 2000:
        raise HTTPException(400, "message too long (max 2000 characters)")
    ckey = (body.get("ckey") or "")[:64] or None
    if ckey:
        old = db.one("SELECT * FROM messages WHERE ckey=?", (ckey,))
        if old:  # the phone sent it twice (retry after a lost answer)
            return _msg_view(old)
    shape = body.get("shape") if body.get("shape") in graphs.SHAPES else "tall"
    chars = _ready_chars(body.get("chars"))
    model = body.get("model") if body.get("model") == "klein" or body.get("model") in graphs.UNETS else "klein"
    if body.get("model") == "qwen" or (body.get("model") in ("scribble", "q21") and sketch):  # Qwen-Edit / Anima Scribble / Qwen 2.1 control: with a picture only
        model = body.get("model")
    edit = body.get("edit") if sketch and body.get("edit") in EDIT else None
    if edit and not text:
        raise HTTPException(400, "say what to change")
    style = body.get("style") if body.get("style") in LOOKS else "bw"
    mid = db.insert("messages", chat_id=cid, text=text, shape=shape, chars=[ch["slug"] for ch in chars], ckey=ckey,
                    sketch=sketch, model=model, edit=edit, style=style)
    seed = body.get("seed") if isinstance(body.get("seed"), int) and body["seed"] > 0 else None  # benches: fixed seed
    jid = _chat_job(text, shape, chars, f"msg:{mid}", seed, sketch=sketch, model=model, edit=edit, style=style)
    db.update("messages", mid, job_id=jid)
    if not c["title"]:
        db.update("chats", cid, title=text[:60] or "sketch")
    return _msg_view(db.get("messages", mid))


@app.post("/api/messages/{mid}/again")
def again(mid: int, body: dict = Body(default={})):
    """Same prompt again as a new message: seed "new" (default) or "same" (same picture settings)."""
    m = db.get("messages", mid)
    if not m:
        raise HTTPException(404, "no such message")
    chars = _ready_chars(m["chars"])
    old = db.get("jobs", m["job_id"]) if m["job_id"] else None
    seed = old["params"].get("seed") if old and (body or {}).get("seed") == "same" else None
    sketch = m.get("sketch") if m.get("sketch") and db.get("images", m["sketch"]) else None
    model = m.get("model") or "klein"
    edit = m.get("edit") if sketch else None
    style = m.get("style") or "bw"
    nid = db.insert("messages", chat_id=m["chat_id"], text=m["text"], shape=m["shape"], chars=m["chars"] or [],
                    sketch=sketch, model=model, edit=edit, style=style)
    jid = _chat_job(m["text"], m["shape"], chars, f"msg:{nid}", seed, sketch, model, edit, style)
    db.update("messages", nid, job_id=jid)
    return _msg_view(db.get("messages", nid))


@app.post("/api/sketch")
async def add_sketch(request: Request):
    """The user's own sketch or picture (raw image bytes, any common format): stored as a gallery picture
    (source "sketch", greyscale, contrast stretched, at most 2048 px); returns its id for the next message."""
    data = await request.body()
    if not data or len(data) > SKETCH_MAX:
        raise HTTPException(400, f"picture missing or too big (max {SKETCH_MAX // 2**20} MB)")
    try:
        png = _sketch_png(data)
    except Exception:
        raise HTTPException(400, "not a picture the app can read (use JPG, PNG or WebP)")
    iid = media.save(png, "sketch", "user sketch")
    row = db.get("images", iid)
    return {"id": iid, "w": row["w"], "h": row["h"]}


SKETCH_MAX = 25 * 2**20


def _sketch_png(data):
    import io

    from PIL import Image, ImageOps
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)  # phone photos carry their rotation in EXIF
    if im.mode in ("RGBA", "LA", "P"):  # transparent drawing-app exports: put them on white paper
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, "white")
        im = Image.alpha_composite(bg, im)
    im = ImageOps.autocontrast(im.convert("L"), cutoff=1)  # pencil on grey paper -> dark lines on white
    im.thumbnail((2048, 2048))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


# ---------- images / gallery ----------
@app.get("/api/images")
def images(before: str = "", limit: int = 60):
    limit = max(1, min(limit, 200))
    if before:
        ts, _, iid = before.partition("_")
        rows = db.query("SELECT id, ts, w, h, source FROM images WHERE (ts < ?) OR (ts = ? AND id < ?) "
                        "ORDER BY ts DESC, id DESC LIMIT ?", (float(ts), float(ts), int(iid), limit))
    else:
        rows = db.query("SELECT id, ts, w, h, source FROM images ORDER BY ts DESC, id DESC LIMIT ?", (limit,))
    nxt = f"{rows[-1]['ts']!r}_{rows[-1]['id']}" if len(rows) == limit else None
    total = db.one("SELECT COUNT(*) AS n FROM images")["n"]
    return {"items": rows, "next": nxt, "total": total}


@app.get("/api/images/{iid}")
def image(iid: int, dl: int = 0):
    try:
        p, row = media.path(iid)
    except FileNotFoundError:
        raise HTTPException(404, "no such picture")
    headers = {"Cache-Control": "no-store"}
    if dl:
        headers["Content-Disposition"] = f'attachment; filename="manga-{iid}.png"'
    return FileResponse(p, media_type="image/png", headers=headers)


@app.get("/api/images/{iid}/info")
def image_info(iid: int):
    row = db.get("images", iid)
    if not row:
        raise HTTPException(404, "no such picture")
    return {k: row[k] for k in ("id", "ts", "w", "h", "source", "prompt")}


@app.get("/api/images/{iid}/thumb")
def thumb(iid: int, s: str = "s"):
    try:
        p = media.thumb(iid, s if s in media.SIZES else "s")
    except FileNotFoundError:
        raise HTTPException(404, "no such picture")
    return FileResponse(p, media_type="image/webp", headers={"Cache-Control": "no-store"})


# ---------- characters ----------
def _char_view(ch, full=False):
    owner = f"char:{ch['id']}"
    counts = {r["status"]: r["n"] for r in db.query(
        "SELECT status, COUNT(*) AS n FROM jobs WHERE owner=? AND kind='charref' GROUP BY status", (owner,))}
    out = {k: ch[k] for k in ("id", "slug", "name", "source_image", "status", "error", "ts", "traits")}
    out["made"] = counts.get("done", 0)
    out["planned"] = sum(counts.values())
    out["refs"] = ch["refs"] or []
    run = db.one("SELECT id, progress, total, params FROM jobs WHERE owner=? AND status='running'", (owner,))
    out["step"] = {"progress": run["progress"], "total": run["total"],
                   "label": (run["params"] or {}).get("label", "") if run["params"] else ""} if run else None
    first = db.one("SELECT id FROM jobs WHERE owner=? AND status='queued' ORDER BY id LIMIT 1", (owner,))
    out["ahead"] = (db.one("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('queued','running') AND id<? AND owner<>?",
                           (first["id"], owner))["n"] if first and not run else 0)
    if full:
        out["scores"] = ch["scores"] or {}
        made = db.query("SELECT image_id FROM jobs WHERE owner=? AND kind='charref' AND status='done' ORDER BY id",
                        (owner,))
        out["dropped"] = [r["image_id"] for r in made if r["image_id"] not in (ch["refs"] or [])] \
            if ch["status"] in ("ready", "review") else []
        out["all"] = [r["image_id"] for r in made]
    return out


@app.get("/api/characters")
def characters():
    return [_char_view(c) for c in db.query("SELECT * FROM characters ORDER BY id DESC")]


@app.get("/api/characters/{cid}")
def character(cid: int):
    ch = db.get("characters", cid)
    if not ch:
        raise HTTPException(404, "no such character")
    return _char_view(ch, full=True)


def _slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "character"
    base, n = s, 2
    while db.one("SELECT id FROM characters WHERE slug=?", (s,)):
        s = f"{base}-{n}"
        n += 1
    return s


SETUP_MAX = {"angles": 12, "expressions": 6, "outfits": 10}


def _setup(raw):
    """The user's edited set-up list -> a clean one: known parts, short texts, own items get keys "u-<words>"."""
    if not isinstance(raw, dict):
        raise HTTPException(400, "bad set-up list")
    std = worker.default_setup()
    out = {}
    for part, most in SETUP_MAX.items():
        items, seen = [], set()
        for x in (raw.get(part) or [])[:most]:
            if not isinstance(x, dict):
                raise HTTPException(400, "bad set-up list")
            text = re.sub(r"\s+", " ", str(x.get("text") or "")).strip()[:200]
            key = str(x.get("key") or "")
            if key not in {i["key"] for i in std[part]} or key in seen:  # an item the user added
                base = "u-" + (re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:24] or "item")
                key, n = base, 1
                while key in seen:
                    n += 1
                    key = f"{base}-{n}"
            seen.add(key)
            if text:
                items.append({"key": key, "text": text, "on": bool(x.get("on", True))})
        out[part] = items
    if not worker.char_plan(out):
        raise HTTPException(400, "switch on at least one picture (an angle with an expression, or an outfit)")
    return out


@app.get("/api/charsetup")
def char_setup():
    """The standard list of pictures a new character gets (the set-up page starts from it)."""
    return worker.default_setup()


@app.post("/api/characters")
def make_character(body: dict = Body(...)):
    name = (body.get("name") or "").strip()
    if not name or len(name) > 40:
        raise HTTPException(400, "give the character a name (max 40 characters)")
    iid = body.get("image_id")
    if not isinstance(iid, int) or not db.get("images", iid):
        raise HTTPException(404, "no such picture")
    plan = worker.char_plan(_setup(body.get("setup")) if body.get("setup") is not None else None)
    slug = _slug(name)
    cid = db.insert("characters", slug=slug, name=name, source_image=iid, status="building", refs=[], plan=plan)
    # first a trait list from the picture (local vision LLM, only if it is running), used in every prompt
    if refpick.ON:
        worker.add_job("traits", {"char": cid}, f"char:{cid}")
    w, h = studio.SIZE
    s = worker.seed()  # one seed for the whole set: same noise, only the instruction changes
    for label, change in plan:
        worker.add_job("charref", {"change": change, "prompt": "", "src": iid, "w": w, "h": h,
                                   "seed": s, "label": label}, f"char:{cid}")
    return _char_view(db.get("characters", cid))


@app.post("/api/characters/{cid}/save")
def save_character(cid: int, body: dict = Body(...)):
    """After the review grid: the views the user keeps (+ the trait list) make the character usable."""
    ch = db.get("characters", cid)
    if not ch:
        raise HTTPException(404, "no such character")
    if ch["status"] not in ("review", "ready"):
        raise HTTPException(409, "this character is still being made")
    made = {r["image_id"] for r in db.query("SELECT image_id FROM jobs WHERE owner=? AND kind='charref' AND "
                                            "status='done'", (f"char:{cid}",))}
    keep = body.get("keep")
    if not isinstance(keep, list) or not all(isinstance(i, int) and i in made for i in keep):
        raise HTTPException(400, "bad picture choice")
    if not keep:
        raise HTTPException(400, "keep at least one picture")
    scores = ch["scores"] or {}
    keep = sorted(set(keep), key=lambda i: -(scores.get(str(i), {}).get("score") or 0))
    traits = body.get("traits")
    f = {"status": "ready", "refs": keep}
    if traits is not None:
        f["traits"] = str(traits).strip()[:400]
    db.update("characters", cid, **f)
    worker._write_character_folder(db.get("characters", cid))
    return _char_view(db.get("characters", cid), full=True)


@app.post("/api/characters/{cid}/traits")
def set_traits(cid: int, body: dict = Body(...)):
    """The character's looks in words (used in every prompt). Editable at any time."""
    ch = db.get("characters", cid)
    if not ch:
        raise HTTPException(404, "no such character")
    db.update("characters", cid, traits=str(body.get("traits") or "").strip()[:400])
    return _char_view(db.get("characters", cid), full=True)


@app.post("/api/characters/{cid}/cancel")
def cancel_character(cid: int):
    ch = db.get("characters", cid)
    if not ch:
        raise HTTPException(404, "no such character")
    if ch["status"] in ("building", "checking"):
        db.update("characters", cid, status="cancelled")
        for j in db.query("SELECT id FROM jobs WHERE owner=? AND status IN ('queued','running')", (f"char:{cid}",)):
            worker.cancel(j["id"])
    return {"ok": True}


@app.post("/api/characters/{cid}/retry")
def retry_character(cid: int):
    """A failed or stopped set: make the missing pictures again, then the face check."""
    ch = db.get("characters", cid)
    if not ch:
        raise HTTPException(404, "no such character")
    owner = f"char:{cid}"
    if ch["status"] == "ready":  # run the face check again on the pictures already made
        db.update("characters", cid, status="checking")
        worker.add_job("charscore", {"char": cid}, owner)
        return _char_view(db.get("characters", cid))
    if ch["status"] not in ("failed", "cancelled"):
        raise HTTPException(409, "this character is still being made")
    redo = db.query("SELECT * FROM jobs WHERE owner=? AND kind='charref' AND status IN ('failed','cancelled')", (owner,))
    db.update("characters", cid, status="building", error=None)
    for j in redo:
        p = j["params"]
        p.pop("client_id", None)
        worker.add_job("charref", p, owner)
    if not redo:
        last = db.one("SELECT * FROM jobs WHERE owner=? AND kind='charref' ORDER BY id DESC LIMIT 1", (owner,))
        worker._after(last)
    return _char_view(db.get("characters", cid))


# ---------- pages ----------
def _page_view(pg):
    out = {k: pg.get(k) for k in ("id", "ts", "chars", "lines", "image_id", "status", "error", "writer", "bible")}
    out["scene"] = {k: {**v, "job": _job_view(v.get("job_id"))} for k, v in (pg.get("scene") or {}).items()}
    out["panels"] = [{**p, "job": _job_view(p.get("job_id")), "versions": worker.versions(p)} for p in pg["panels"]]
    return out


@app.get("/api/pages")
def pages():
    return [_page_view(p) for p in db.query("SELECT * FROM pages ORDER BY id DESC LIMIT 100")]


@app.get("/api/pages/{pid}")
def page(pid: int):
    pg = db.get("pages", pid)
    if not pg:
        raise HTTPException(404, "no such page")
    return _page_view(pg)


@app.post("/api/pages")
def make_page(body: dict = Body(...)):
    lines = [str(x).strip()[:1200] for x in (body.get("lines") or [])]
    if len(lines) != 4 or not all(lines):
        raise HTTPException(400, "write one line for each of the 4 panels")
    chars = _ready_chars(body.get("chars"))
    bible = str(body.get("bible") or "").strip()[:1500]
    prompts, quotes, casts, who, fixed = writer.write(lines, _wchars(chars), bible)
    panels = [{"line": lines[i], "prompt": prompts[i], "quotes": quotes[i], "cast": casts[i]} for i in range(4)]
    for i in range(4):
        if fixed[i]:  # spelling fixed by the local LLM writer: used, and the user sees what it was
            panels[i]["fixed"] = lines[i]
            panels[i]["line"] = lines[i] = fixed[i]
    seed = body.get("seed") if isinstance(body.get("seed"), int) else None  # tests: same seeds before/after
    pid = db.insert("pages", chars=[c["slug"] for c in chars], lines=lines, panels=panels, status="working",
                    writer=who, bible=bible, seed=seed)
    pagejobs.start(pid)
    return _page_view(db.get("pages", pid))


def _wchars(chars):
    """What the prompt writer needs of each character (n = reference pictures it gets in a panel)."""
    return [{"name": c["name"], "traits": c.get("traits") or ""} for c in chars]


def _busy(job_id):
    return bool(job_id) and db.get("jobs", job_id)["status"] in ("queued", "running")


@app.post("/api/pages/{pid}/panels/{idx}/redo")
def redo_panel(pid: int, idx: int, body: dict = Body(default={})):
    """Draw one panel again (new seed); the other panels stay. Optional: a new line and/or which of the
    page's characters are in it (cast = indexes into the page's characters). The old picture stays as a
    version the user can pick again."""
    pg = db.get("pages", pid)
    if not pg or not 0 <= idx < 4:
        raise HTTPException(404, "no such panel")
    chars = _ready_chars(pg["chars"])
    panels = pg["panels"]
    pn = panels[idx]
    if _busy(pn.get("job_id")) or _busy(pn.get("check_id")):
        raise HTTPException(409, "this panel is still being made")
    line = body.get("line")
    cast = body.get("cast")
    if line is not None:
        line = str(line).strip()[:1200]
        if not line:
            raise HTTPException(400, "write what happens in this panel")
    if cast is not None:
        if not isinstance(cast, list) or not all(isinstance(i, int) and 0 <= i < len(chars) for i in cast):
            raise HTTPException(400, "bad character choice")
        cast = sorted(set(cast))
    if line is not None or cast is not None:
        new_line = line if line is not None else pn["line"]
        if cast is None and line is not None:
            cast = pn.get("cast")  # keep the user's earlier choice of characters
        prompt, quotes, cast = writer.panel(new_line, _wchars(chars), idx, cast, pg.get("bible") or "")
        pn.update(line=new_line, prompt=prompt, quotes=quotes, cast=cast, fixed=None, warn=None)
        lines = pg["lines"]
        lines[idx] = new_line
        db.update("pages", pid, lines=lines)
    pn["warn"] = None
    if not pn.get("job_id") and pg["status"] == "working":  # not started yet: the page draws it with the new line
        db.update("pages", pid, panels=panels)
        pagejobs.advance(pid)
        return _page_view(db.get("pages", pid))
    db.update("pages", pid, panels=panels, status="working", error=None)
    pg = db.get("pages", pid)
    try:
        pg["panels"][idx]["job_id"] = pagejobs.panel_job(pid, idx)
    except pagejobs.PanelError as e:
        db.update("pages", pid, status="done", error=str(e))
        raise HTTPException(409, str(e))
    db.update("pages", pid, panels=pg["panels"])
    return _page_view(db.get("pages", pid))


@app.post("/api/pages/{pid}/scene/{kind}/redo")
def redo_scene(pid: int, kind: str):
    """Draw the place plate or the prop sheet again (new seed). Panels drawn after this use the new one."""
    pg = db.get("pages", pid)
    scene = (pg or {}).get("scene") or {}
    if kind not in scene:
        raise HTTPException(404, "no such scene picture")
    if _busy(scene[kind].get("job_id")):
        raise HTTPException(409, "this picture is still being made")
    scene[kind]["job_id"] = pagejobs.scene_job(pid, kind, scene[kind]["prompt"])
    db.update("pages", pid, scene=scene)
    return _page_view(db.get("pages", pid))


@app.post("/api/pages/{pid}/panels/{idx}/pick")
def pick_version(pid: int, idx: int, body: dict = Body(...)):
    """Use an earlier (or the newest) picture of a panel and put the page together again."""
    pg = db.get("pages", pid)
    if not pg or not 0 <= idx < 4:
        raise HTTPException(404, "no such panel")
    panels = pg["panels"]
    pn = panels[idx]
    v = next((v for v in worker.versions(pn) if v["image_id"] == body.get("image_id")), None)
    if not v:
        raise HTTPException(404, "no such version")
    pn.update(image_id=v["image_id"], quotes=v.get("quotes", pn.get("quotes", [])), line=v.get("line", pn["line"]))
    lines = pg["lines"]
    lines[idx] = pn["line"]
    db.update("pages", pid, panels=panels, lines=lines)
    if not pagejobs.busy(db.get("pages", pid)):
        worker.compose_page(pid)
    return _page_view(db.get("pages", pid))


@app.post("/api/characters/{cid}/describe")
def describe_character(cid: int):
    """Looks in words from the source picture by the local vision LLM (LLM mode)."""
    ch = db.get("characters", cid)
    if not ch:
        raise HTTPException(404, "no such character")
    try:
        text = worker.describe(ch["source_image"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"could not describe: {e}"[:200])
    return {"traits": text}


# ---------- GPU mode (drawing <-> local LLM) ----------
@app.get("/api/mode")
def gpu_mode():
    st = gpuhelper.status()
    return {"helper": st is not None, "status": st, "llm": director.llm_state(), "comfy": worker.STATUS["comfy"]}


@app.post("/api/mode")
def set_gpu_mode(body: dict = Body(...)):
    m = body.get("mode")
    if m not in ("llm", "draw"):
        raise HTTPException(400, "mode is llm or draw")
    if not gpuhelper.available():
        raise HTTPException(503, "the GPU switch is not set up (no helper key)")
    if m == "llm" and _queue_count():
        raise HTTPException(409, "pictures are still being drawn: wait or stop them first")
    try:
        msg = gpuhelper.mode("llm-mode" if m == "llm" else "draw-mode")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(409, str(e)[:200])
    db.bump()
    return {"ok": True, "msg": msg}


# ---------- director ----------
@app.get("/api/director/chats")
def dchats():
    return db.query("SELECT * FROM dchats ORDER BY id DESC LIMIT 100")


@app.post("/api/director/chats")
def new_dchat():
    return db.get("dchats", db.insert("dchats", title=""))


@app.get("/api/director/chats/{cid}")
def dchat(cid: int):
    c = db.get("dchats", cid)
    if not c:
        raise HTTPException(404, "no such director chat")
    return {"chat": c, "messages": db.query("SELECT * FROM dmsgs WHERE chat_id=? ORDER BY id", (cid,))}


@app.post("/api/director/chats/{cid}/messages")
def dsend(cid: int, body: dict = Body(...)):
    c = db.get("dchats", cid)
    if not c:
        raise HTTPException(404, "no such director chat")
    text = (body.get("text") or "").strip()
    if not text or len(text) > 20000:
        raise HTTPException(400, "write a message (max 20000 characters)")
    if db.one("SELECT id FROM dmsgs WHERE chat_id=? AND status='working'", (cid,)):
        raise HTTPException(409, "the director is still answering")
    if director.llm_state()["state"] == "off":
        raise HTTPException(503, "the local LLM is off: tap LLM up first")
    chars = []
    for s_ in (body.get("chars") or [])[:4]:
        ch = db.one("SELECT name, traits FROM characters WHERE slug=? AND status='ready'", (s_,))
        if ch:
            chars.append(ch)
    if body.get("chars") is not None:
        db.update("dchats", cid, chars=[str(x) for x in body.get("chars")][:4])
    if not c["title"]:
        db.update("dchats", cid, title=text.splitlines()[0][:60])
    aid = director.send(cid, text, chars)
    return db.get("dmsgs", aid)


@app.post("/api/director/messages/{mid}/shotlist")
def dsave_shotlist(mid: int, body: dict = Body(...)):
    """The user's edits to a shot list (the next turn sends them back to the model)."""
    m = db.get("dmsgs", mid)
    if not m or m["role"] != "assistant":
        raise HTTPException(404, "no such answer")
    sl = body.get("shotlist")
    if not isinstance(sl, dict) or not isinstance(sl.get("panels"), list):
        raise HTTPException(400, "bad shot list")
    db.update("dmsgs", mid, shotlist=sl)
    return {"ok": True}


@app.post("/api/director/messages/{mid}/page")
def dpage(mid: int):
    """Shot list -> what Make page needs: 4 lines + the scene bible."""
    m = db.get("dmsgs", mid)
    if not m or not m.get("shotlist"):
        raise HTTPException(404, "no shot list")
    lines, bible = director.page_lines(m["shotlist"])
    return {"lines": lines, "bible": bible}


@app.get("/api/director/skills")
def dskills():
    return {"text": director.skills(), "custom": director.skills_path().exists()}


@app.put("/api/director/skills")
def dset_skills(body: dict = Body(...)):
    t = body.get("text")
    if t is not None and (not isinstance(t, str) or len(t) > 50000):
        raise HTTPException(400, "bad skills text")
    director.set_skills(t)
    return dskills()


# ---------- GPU line ----------
_gpu_cache = {"t": 0, "v": None}


@app.get("/api/gpu")
def gpu():
    if time.time() - _gpu_cache["t"] > 2:
        try:
            out = subprocess.run(["nvidia-smi", "-i", "0", "--query-gpu=utilization.gpu,temperature.gpu,memory.used,"
                                  "memory.total", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=5).stdout
            u, t, used, tot = [int(x.strip()) for x in out.strip().splitlines()[0].split(",")]
            _gpu_cache["v"] = {"util": u, "temp": t, "used": used, "total": tot}
        except Exception:
            _gpu_cache["v"] = None
        _gpu_cache["t"] = time.time()
    return _gpu_cache["v"]  # null when nvidia-smi is not available


@app.get("/healthz")
def healthz():
    return Response("ok")
