"""Manga Studio — one page: type a prompt, get a manga illustration.

FastAPI app; talks to the ComfyUI container in this folder (service `comfyui`, :8188).
"""
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import comfy
import routing
import store
import studio
import workflows

OUTPUT = Path(os.environ.get("OUTPUT_DIR", "/data/output"))
SUB = os.environ.get("CHAT_SUBDIR", "manga")
STATIC = Path(__file__).resolve().parent / "static"

JOBS: "queue.Queue[int]" = queue.Queue()
CANCELLING: set[int] = set()
_cancel_lock = threading.Lock()


def _is_cancelling(mid):
    with _cancel_lock:
        return mid in CANCELLING


def _clear_cancel(mid):
    with _cancel_lock:
        CANCELLING.discard(mid)


def process(mid):
    job = store.get(mid)
    if job is None:
        return
    plan = json.loads(job["params"])
    store.update(mid, status="running")
    t0 = time.time()
    try:
        wf = workflows.anima(job["prompt"], plan["width"], plan["height"], plan["seed"], plan["prefix"])
        entry = comfy.run_job(
            wf,
            cancel_check=lambda: _is_cancelling(mid),
            on_progress=lambda v, m: store.update(mid, progress=v, total=m))
        files = comfy.result_files(entry)
        if not files:
            raise RuntimeError("finished but produced no image")
        sub, name = files[-1]
        final = (OUTPUT / sub / name).resolve()
        rel = str(final.relative_to(OUTPUT.resolve()))
        store.update(mid, status="done", filename=rel, elapsed=time.time() - t0, progress=1, total=1)
    except comfy.JobCancelled:
        store.update(mid, status="cancelled", elapsed=time.time() - t0)
    except Exception as e:  # noqa: BLE001 - show the failure in the feed
        store.update(mid, status="failed", error=str(e)[:400], elapsed=time.time() - t0)
    finally:
        _clear_cancel(mid)


def worker():
    comfy.wait_ready()
    while True:
        mid = JOBS.get()
        try:
            if isinstance(mid, tuple):  # ("s", id): character studio job
                process_studio(mid[1])
            else:
                process(mid)
        except Exception as e:  # noqa: BLE001 - never let the worker die
            if isinstance(mid, tuple):
                studio.update(mid[1], status="failed", error=str(e)[:400])
            else:
                store.update(mid, status="failed", error=str(e)[:400])


@asynccontextmanager
async def lifespan(app):
    store.init()
    studio.init()
    for mid in store.unfinished_ids():
        store.update(mid, status="failed", error="interrupted by restart")
    threading.Thread(target=worker, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def no_store_static(request, call_next):
    # phones kept an old studio.js; static files are tiny, always fetch fresh
    resp = await call_next(request)
    if request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


@app.get("/")
def index():
    return FileResponse(str(STATIC / "index.html"), headers={"Cache-Control": "no-store"})


@app.get("/api/info")
def info():
    stats = None
    try:
        stats = comfy._get("/system_stats", timeout=5)
    except Exception:
        pass
    return {"models": [routing.MODEL], "label": routing.LABEL, "stats": stats}


@app.get("/api/feed")
def feed():
    return store.feed()


@app.post("/api/messages")
async def send(prompt: str = Form(...), shape: str = Form("tall"), seed: int = Form(0)):
    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(400, "empty prompt")
    if seed == 0:
        seed = int.from_bytes(os.urandom(4), "big")
    plan = routing.plan(shape, seed)
    plan["prefix"] = f"{SUB}/{int(time.time())}"
    mid = store.add(prompt, "picture", "anime", None, plan)
    JOBS.put(mid)
    return {"id": mid, "plan": plan, "describe": routing.describe(plan)}


@app.post("/api/messages/{mid}/again")
def again(mid: int, seed_mode: str = Form("new")):
    msg = store.get(mid)
    if msg is None:
        raise HTTPException(404, "no such message")
    old = json.loads(msg["params"])
    seed = old["seed"] if seed_mode == "same" else int.from_bytes(os.urandom(4), "big")
    plan = routing.plan(old.get("shape", "tall"), seed)
    plan["prefix"] = f"{SUB}/{int(time.time())}"
    new_id = store.add(msg["prompt"], "picture", "anime", None, plan)
    JOBS.put(new_id)
    return {"id": new_id, "plan": plan, "describe": routing.describe(plan)}


@app.post("/api/messages/{mid}/cancel")
def cancel(mid: int):
    if store.get(mid) is None:
        raise HTTPException(404, "no such message")
    with _cancel_lock:
        CANCELLING.add(mid)
    return {"ok": True}


@app.post("/api/free")
def free_gpu():
    comfy.free()
    return {"ok": True}


_gpu_cache = {"t": 0, "v": None}


@app.get("/api/gpu")
def gpu():
    if time.time() - _gpu_cache["t"] > 1:
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout
            row = [x.strip() for x in out.strip().splitlines()[0].split(",")]
            _gpu_cache["v"] = {"name": row[0].replace("NVIDIA GeForce ", "").replace("RTX ", ""),
                               "util": int(row[1]), "temp": int(row[2]),
                               "used": int(row[3]), "total": int(row[4])}
        except Exception:
            _gpu_cache["v"] = None
        _gpu_cache["t"] = time.time()
    if _gpu_cache["v"] is None:
        raise HTTPException(503, "nvidia-smi not available")
    return _gpu_cache["v"]


@app.get("/api/files/{path:path}")
def files(path: str):
    p = (OUTPUT / path).resolve()
    if not str(p).startswith(str(OUTPUT.resolve()) + os.sep) or not p.is_file():
        raise HTTPException(404, "no such file")
    return FileResponse(p, headers={"Cache-Control": "no-store"})


# ---------- Character studio (2026-10-24) ----------

_family = {"v": "anima"}  # model family loaded last; free VRAM when it changes (klein 9B fills the card)


def _studio_workflow(job, params, prefix):
    kind = job["kind"]
    w, h = params["width"], params["height"]
    if kind == "t2i":
        wf = workflows.anima(job["prompt"], w, h, params["seed"], prefix, workflows.NEG_BW)
        return "anima", workflows.bw_finish(wf, ["9", 0], w, h, prefix)
    if kind in ("i2i", "inpaint"):
        src = studio.stage(params["src"])
        mask = params.get("mask")
        wf = workflows.anima_i2i(job["prompt"], src, w, h, params["seed"], prefix, params["denoise"], mask)
        return "anima", workflows.bw_finish(wf, ["26", 0] if mask else ["9", 0], w, h, prefix)
    if kind == "var":
        src = studio.stage(params["src"])
        if params["model"] == "klein9":
            return "klein9", workflows.klein9_edit(job["prompt"], src, w, h, params["seed"], prefix)
        if params["model"] == "qwen2511":
            return "qwen2511", workflows.qwen2511_edit(job["prompt"], src, w, h, params["seed"], prefix)
    if kind == "frame":
        if params["method"] == "restyle":  # Anima img2img over a finished frame: keeps layout, gets Anima's ink look
            src = studio.stage(params["src"])
            wf = workflows.anima_i2i(job["prompt"], src, w, h, params["seed"], prefix, params["denoise"])
            return "anima", workflows.bw_finish(wf, ["9", 0], w, h, prefix)
        if params["method"] == "control":
            ctrl = studio.stage(params["src"])
            ref = studio.stage(params["ref"]) if params.get("ref") else None
            return "anima", workflows.anima_control(job["prompt"], ctrl, w, h, params["seed"], prefix,
                                                    params["ctrl_strength"], params["ctrl_end"], ref,
                                                    params["ip_strength"], params.get("loras"),
                                                    params.get("neg_extra", ""))
        if params["method"] == "klein9":
            refs = [studio.stage(f"manga/characters/{c}/character.png") for c in params["chars"]]
            wf = workflows.klein9_refs(job["prompt"], refs, w, h, params["seed"], prefix)
            return "klein9", workflows.bw_finish(wf, ["17", 0], w, h, prefix, save_id="18")
        wf = workflows.anima(job["prompt"], w, h, params["seed"], prefix, workflows.NEG_BW)
        return "anima", workflows.bw_finish(wf, ["9", 0], w, h, prefix)
    raise RuntimeError(f"unknown studio job {kind}")


def process_studio(jid):
    job = studio.get(jid)
    if job is None or job["status"] != "queued":
        return
    key = ("s", jid)
    params = json.loads(job["params"])
    studio.update(jid, status="running")
    t0 = time.time()
    try:
        family, wf = _studio_workflow(job, params, f"{SUB}/studio/{job['batch']}_{jid}")
        if family != _family["v"]:
            comfy.free()
            _family["v"] = family
        t_run = time.time()
        entry = comfy.run_job(wf, cancel_check=lambda: _is_cancelling(key),
                              on_progress=lambda v, m: studio.update(jid, progress=v, total=m))
        files = comfy.result_files(entry)
        if not files:
            raise RuntimeError("finished but produced no image")
        sub, name = files[-1]
        out = OUTPUT / sub / name
        elapsed = time.time() - t0
        if job["kind"] == "var":
            rd = Path(params["run_dir"])
            fname = f"{params['index']:02d}_{params['label']}.png"
            shutil.copyfile(out, rd / fname)
            studio.record_variation(rd, {"file": fname, "label": params["label"], "prompt": job["prompt"],
                                         "seed": params["seed"], "seconds": round(elapsed, 1),
                                         "gen_seconds": round(time.time() - t_run, 1)})
            rel = f"manga/{(rd / fname).relative_to(studio.MANGA)}"
        else:
            dst = studio.MANGA / "work" / "out" / f"{job['batch']}_{jid}.png"
            shutil.copyfile(out, dst)
            rel = f"manga/work/out/{dst.name}"
        studio.update(jid, status="done", filename=rel, elapsed=elapsed, progress=1, total=1)
    except comfy.JobCancelled:
        studio.update(jid, status="cancelled", elapsed=time.time() - t0)
    except Exception as e:  # noqa: BLE001
        studio.update(jid, status="failed", error=str(e)[:400], elapsed=time.time() - t0)
    finally:
        _clear_cancel(key)


def _seed():
    return int.from_bytes(os.urandom(4), "big")


def _queue(batch, kind, prompt, params):
    jid = studio.add(batch, kind, prompt, params)
    JOBS.put(("s", jid))
    return jid


@app.post("/api/studio/grid")
def studio_grid(prompt: str = Form(...), count: int = Form(16)):
    prompt = prompt.strip()
    if not prompt:
        raise HTTPException(400, "empty prompt")
    batch = studio.new_batch()
    w, h = studio.SIZE
    for _ in range(max(1, min(count, 16))):
        _queue(batch, "t2i", prompt, {"seed": _seed(), "width": w, "height": h, "settings": studio.ANIMA_SETTINGS})
    return {"batch": batch}


def _src_info(src):
    try:
        studio.resolve(src)
    except FileNotFoundError:
        raise HTTPException(404, "no such picture")
    return studio.meta_for(src)


@app.post("/api/studio/more")
def studio_more(src: str = Form(...), prompt: str = Form(...), denoise: float = Form(0.4), count: int = Form(4)):
    meta = _src_info(src)
    batch = studio.new_batch()
    w, h = studio.SIZE
    d = max(0.2, min(0.7, denoise))
    for _ in range(max(1, min(count, 8))):
        _queue(batch, "i2i", prompt.strip(), {"seed": _seed(), "width": w, "height": h, "src": src, "denoise": d,
                                              "settings": studio.ANIMA_SETTINGS,
                                              "parent": {"ref": src, "seed": meta.get("seed"), "kind": meta.get("kind")}})
    return {"batch": batch}


@app.post("/api/studio/inpaint")
async def studio_inpaint(src: str = Form(...), prompt: str = Form(...), denoise: float = Form(0.6),
                         count: int = Form(2), mask: UploadFile = File(...)):
    meta = _src_info(src)
    data = await mask.read()
    if not data or len(data) > 8_000_000:
        raise HTTPException(400, "bad mask")
    batch = studio.new_batch()
    w, h = studio.SIZE
    d = max(0.2, min(1.0, denoise))
    for _ in range(max(1, min(count, 4))):
        mname = studio.stage_bytes(data)
        _queue(batch, "inpaint", prompt.strip(), {"seed": _seed(), "width": w, "height": h, "src": src, "denoise": d,
                                                  "mask": mname, "settings": studio.ANIMA_SETTINGS,
                                                  "parent": {"ref": src, "seed": meta.get("seed"),
                                                             "kind": meta.get("kind")}})
    return {"batch": batch}


@app.post("/api/studio/cancel")
def studio_cancel(batch: str = Form(...)):
    for jid in studio.batch_ids(batch):
        job = studio.get(jid)
        if job["status"] == "queued":
            studio.update(jid, status="cancelled")
        else:
            with _cancel_lock:
                CANCELLING.add(("s", jid))
    return {"ok": True}


@app.get("/api/studio/state")
def studio_state():
    return {"jobs": studio.jobs(), "kept": studio.kept_list(), "characters": studio.characters(),
            "models": {k: {"label": v["label"], "ready": studio.model_ready(k)} for k, v in studio.EDIT_MODELS.items()},
            "plan": len(studio.variation_plan())}


@app.post("/api/studio/keep")
def studio_keep(job: int = Form(...)):
    try:
        return {"ref": studio.keep(job)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/studio/hide")
def studio_hide(ref: str = Form(...)):
    try:
        studio.hide(ref)
    except FileNotFoundError:
        raise HTTPException(404, "no such picture")
    return {"ok": True}


@app.post("/api/studio/save")
def studio_save(ref: str = Form(...), name: str = Form(...), traits: str = Form("")):
    _src_info(ref)
    try:
        return {"name": studio.save_character(ref, name, traits)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/studio/variations")
def studio_variations(name: str = Form(...), model: str = Form("klein9"), seed: int = Form(0)):
    if model not in studio.EDIT_MODELS:
        raise HTTPException(400, "unknown model")
    if not studio.model_ready(model):
        raise HTTPException(400, f"{studio.EDIT_MODELS[model]['label']} files are not downloaded")
    try:
        rd, src, traits = studio.start_run(name, model)
    except ValueError as e:
        raise HTTPException(404, str(e))
    seed = seed or _seed()  # one seed for the whole set: same noise, only the instruction changes
    batch = studio.new_batch()
    w, h = studio.SIZE
    for i, (label, change) in enumerate(studio.variation_plan(), 1):
        _queue(batch, "var", studio.edit_prompt(model, change, traits),
               {"seed": seed, "width": w, "height": h, "src": src, "model": model, "label": label, "index": i,
                "run_dir": str(rd)})
    return {"batch": batch, "run": rd.name}


@app.get("/api/studio/file/{ref:path}")
def studio_file(ref: str):
    try:
        return FileResponse(studio.resolve(ref), headers={"Cache-Control": "no-store"})
    except FileNotFoundError:
        raise HTTPException(404, "no such file")


@app.get("/api/frames/{project}")
def frames_get(project: str):
    try:
        data = studio.frames_get(project)
    except ValueError as e:
        raise HTTPException(400, str(e))
    video = studio.MANGA / "frames" / project / "video.mp4"
    return {**data, "shapes": studio.FRAME_SHAPES, "methods": studio.FRAME_METHODS,
            "video": f"manga/frames/{project}/video.mp4" if video.is_file() else None}


@app.post("/api/frames/{project}")
async def frames_put(project: str, data: dict):
    try:
        return studio.frames_put(project, data)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/frames/{project}/{line}/make")
def frames_make(project: str, line: int, prompt: str = Form(...), shape: str = Form("wide"),
                method: str = Form("anima"), chars: str = Form(""), count: int = Form(4)):
    if shape not in studio.FRAME_SHAPES or method not in studio.FRAME_METHODS:
        raise HTTPException(400, "bad shape or method")
    names = [c for c in chars.split(",") if c]
    for c in names:
        if not (studio.MANGA / "characters" / c / "character.png").is_file():
            raise HTTPException(400, f"no saved character '{c}'")
    if method == "klein9" and not names:
        raise HTTPException(400, "klein needs at least one saved character")
    w, h = studio.FRAME_SHAPES[shape]
    batch = studio.new_batch()
    for _ in range(max(1, min(count, 8))):
        _queue(batch, "frame", prompt.strip(), {"seed": _seed(), "width": w, "height": h, "shape": shape,
                                                "method": method, "chars": names, "project": project, "line": line})
    return {"batch": batch}


@app.post("/api/frames/{project}/{line}/restyle")
def frames_restyle(project: str, line: int, src: str = Form(...), prompt: str = Form(...),
                   denoise: float = Form(0.4), count: int = Form(2)):
    try:
        p = studio.resolve(src)
    except FileNotFoundError:
        raise HTTPException(404, "no such picture")
    w, h = _png_size(p)
    batch = studio.new_batch()
    for _ in range(max(1, min(count, 8))):
        _queue(batch, "frame", prompt.strip(), {"seed": _seed(), "width": w, "height": h, "method": "restyle",
                                                "src": src, "denoise": max(0.1, min(0.9, denoise)), "chars": [],
                                                "project": project, "line": line})
    return {"batch": batch}


@app.post("/api/frames/{project}/{line}/control")
def frames_control(project: str, line: int, src: str = Form(...), prompt: str = Form(...), ref: str = Form(""),
                   ctrl_strength: float = Form(1.0), ctrl_end: float = Form(0.6), ip_strength: float = Form(0.7),
                   count: int = Form(2), seed: int = Form(0), loras: str = Form(""), shape: str = Form(""),
                   neg_extra: str = Form("")):
    # loras: "file.safetensors:0.8,other.safetensors:0.5" (files in models/loras)
    lora_list = []
    for part in [x for x in loras.split(",") if x.strip()]:
        name, _, st = part.strip().rpartition(":")
        if not re.fullmatch(r"[\w.-]+\.safetensors", name):
            raise HTTPException(400, f"bad lora: {part}")
        lora_list.append((name, float(st)))
    for r in [src] + ([ref] if ref else []):
        try:
            studio.resolve(r)
        except FileNotFoundError:
            raise HTTPException(404, f"no such picture: {r}")
    w, h = studio.FRAME_SHAPES[shape] if shape in studio.FRAME_SHAPES else _png_size(studio.resolve(src))
    w, h = w // 16 * 16, h // 16 * 16
    batch = studio.new_batch()
    for i in range(max(1, min(count, 8))):
        _queue(batch, "frame", prompt.strip(), {"seed": (seed + i) if seed else _seed(), "width": w, "height": h,
                                                "method": "control", "src": src, "ref": ref,
                                                "ctrl_strength": ctrl_strength, "ctrl_end": ctrl_end,
                                                "ip_strength": ip_strength, "loras": lora_list, "neg_extra": neg_extra[:400], "chars": [],
                                                "project": project,
                                                "line": line})
    return {"batch": batch}


def _png_size(p):
    with open(p, "rb") as f:
        head = f.read(24)
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


@app.post("/api/frames/{project}/{line}/pick")
def frames_pick(project: str, line: int, job: int = Form(...), slot: str = Form("")):
    if slot and not studio.NAME_RE.match(slot):
        raise HTTPException(400, "bad slot")
    try:
        return studio.frame_pick(project, line, job, slot)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/demo")
def demo_page():
    return FileResponse(str(STATIC / "demo.html"), headers={"Cache-Control": "no-store"})


@app.get("/studio")
def studio_page():
    return FileResponse(str(STATIC / "studio.html"), headers={"Cache-Control": "no-store"})
