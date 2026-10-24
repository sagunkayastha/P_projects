"""Manga maker: chat -> pictures, characters from any picture, 4-panel pages. Mobile first, fully local.

FastAPI app; ComfyUI runs in its own container (COMFY_URL). Everything is stored on disk in APP_DIR
(~/Documents/Personal/manga/app): SQLite (chats, jobs, images, characters, pages) + image files.
"""
import asyncio
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
import graphs
import layout
import media
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
    return out


@app.post("/api/jobs/{jid}/cancel")
def cancel_job(jid: int):
    if not db.get("jobs", jid):
        raise HTTPException(404, "no such job")
    worker.cancel(jid)
    return {"ok": True}


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


def _char_refs(ch, text, n):
    """n pictures of a character for klein: the source + the saved views that fit this picture's camera
    angle, outfit and expression (refs.py)."""
    return refpick.pick(ch, text, n)


def _cast(chars, text):
    """(reference picture ids, cast dicts for writer.cast_text) for the characters in one picture."""
    n = refpick.per_char(len(chars))
    ids, cast = [], []
    for ch in chars:
        r = _char_refs(ch, text, n)
        ids += r
        cast.append({"name": ch["name"], "n": len(r), "traits": ch.get("traits") or ""})
    return ids, cast


def _chat_job(text, shape, chars, owner, seed=None):
    w, h = graphs.SHAPES.get(shape, graphs.SHAPES["tall"])
    if chars:
        refs, cast = _cast(chars, text)
        prompt = (f"{writer.cast_text(cast)} {text}. Keep each character's face, hair, body and outfit exactly as in "
                  f"the reference pictures. {graphs.STYLE} No text, no letters, no speech bubbles.")
        params = {"prompt": prompt, "text": text, "w": w, "h": h, "seed": seed or worker.seed(), "refs": refs,
                  "chars": [c["slug"] for c in chars]}
    else:
        params = {"prompt": text, "text": text, "w": w, "h": h, "seed": seed or worker.seed()}
    return worker.add_job("image", params, owner)


@app.post("/api/chats/{cid}/messages")
def send(cid: int, body: dict = Body(...)):
    c = db.get("chats", cid)
    if not c:
        raise HTTPException(404, "no such chat")
    text = (body.get("text") or "").strip()
    if not text:
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
    mid = db.insert("messages", chat_id=cid, text=text, shape=shape, chars=[ch["slug"] for ch in chars], ckey=ckey)
    jid = _chat_job(text, shape, chars, f"msg:{mid}")
    db.update("messages", mid, job_id=jid)
    if not c["title"]:
        db.update("chats", cid, title=text[:60])
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
    nid = db.insert("messages", chat_id=m["chat_id"], text=m["text"], shape=m["shape"], chars=m["chars"] or [])
    jid = _chat_job(m["text"], m["shape"], chars, f"msg:{nid}", seed)
    db.update("messages", nid, job_id=jid)
    return _msg_view(db.get("messages", nid))


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
    run = db.one("SELECT id, progress, total FROM jobs WHERE owner=? AND status='running'", (owner,))
    out["step"] = run if run else None
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


@app.post("/api/characters")
def make_character(body: dict = Body(...)):
    name = (body.get("name") or "").strip()
    if not name or len(name) > 40:
        raise HTTPException(400, "give the character a name (max 40 characters)")
    iid = body.get("image_id")
    if not isinstance(iid, int) or not db.get("images", iid):
        raise HTTPException(404, "no such picture")
    slug = _slug(name)
    cid = db.insert("characters", slug=slug, name=name, source_image=iid, status="building", refs=[])
    # first a trait list from the picture (local vision LLM, only if it is running), used in every prompt
    if refpick.ON:
        worker.add_job("traits", {"char": cid}, f"char:{cid}")
    w, h = studio.SIZE
    s = worker.seed()  # one seed for the whole set: same noise, only the instruction changes
    for label, change in worker.char_plan():
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
    out = {k: pg[k] for k in ("id", "ts", "chars", "lines", "image_id", "status", "error", "writer")}
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


def _panel_job(pid, idx, panel, chars):
    w, h = graphs.fit_size(layout.aspects()[idx], 1.0)
    params = {"prompt": panel["prompt"], "w": w, "h": h, "seed": worker.seed(), "page": pid, "idx": idx,
              "line": panel["line"], "quotes": panel.get("quotes", [])}
    if "cast" in panel:
        chars = [chars[i] for i in panel["cast"] if i < len(chars)]
    if chars:
        params["refs"], _ = _cast(chars, panel["line"] + " " + panel["prompt"])
        params["check_ref"], params["check_name"] = chars[0]["source_image"], chars[0]["name"]
    return worker.add_job("panel", params, f"page:{pid}:{idx}")


@app.post("/api/pages")
def make_page(body: dict = Body(...)):
    lines = [str(x).strip()[:400] for x in (body.get("lines") or [])]
    if len(lines) != 4 or not all(lines):
        raise HTTPException(400, "write one line for each of the 4 panels")
    chars = _ready_chars(body.get("chars"))
    prompts, quotes, casts, who, fixed = writer.write(lines, _wchars(chars))
    panels = [{"line": lines[i], "prompt": prompts[i], "quotes": quotes[i], "cast": casts[i]} for i in range(4)]
    for i in range(4):
        if fixed[i]:  # spelling fixed by the local LLM writer: used, and the user sees what it was
            panels[i]["fixed"] = lines[i]
            panels[i]["line"] = lines[i] = fixed[i]
    pid = db.insert("pages", chars=[c["slug"] for c in chars], lines=lines, panels=panels, status="working",
                    writer=who)
    for i in range(4):
        panels[i]["job_id"] = _panel_job(pid, i, panels[i], chars)
    db.update("pages", pid, panels=panels)
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
        line = str(line).strip()[:400]
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
        prompt, quotes, cast = writer.panel(new_line, _wchars(chars), idx, cast)
        pn.update(line=new_line, prompt=prompt, quotes=quotes, cast=cast, fixed=None, warn=None)
        lines = pg["lines"]
        lines[idx] = new_line
        db.update("pages", pid, lines=lines)
    pn["job_id"] = _panel_job(pid, idx, pn, chars)
    pn["warn"] = None
    db.update("pages", pid, panels=panels, status="working", error=None)
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
    if not worker.page_busy(db.get("pages", pid)):
        worker.compose_page(pid)
    return _page_view(db.get("pages", pid))


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
