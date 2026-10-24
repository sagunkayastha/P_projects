"""Character studio: grid -> keep -> more like this / inpaint -> save as character -> variation set.

Jobs live in the app's RAM database (table `studio`). Everything the user keeps is written to
MANGA_DIR (bind mount of ~/Documents/Personal/manga, mode 700):
  work/kept/<kid>.png + .json            pictures marked "keep"
  characters/<name>/character.png + .json  the saved character (image + seed + prompt + settings)
  characters/<name>/variations/<model>/<run>/NN_<label>.png + run.json   variation sets
"""
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path

MANGA = Path(os.environ.get("MANGA_DIR", "/data/manga"))
INPUT = Path(os.environ.get("INPUT_DIR", "/data/input"))  # = ComfyUI input/studio (RAM)
OUTPUT = Path(os.environ.get("OUTPUT_DIR", "/data/output"))

SIZE = (896, 1152)  # portrait, ~1 MP
ANIMA_SETTINGS = {"model": "beretMixAnimaManga_v20", "steps": 32, "cfg": 4.0, "sampler": "er_sde",
                  "scheduler": "beta", "prefix": "masterpiece, best quality, ", "width": SIZE[0], "height": SIZE[1]}

EDIT_MODELS = {
    "klein9": {"label": "FLUX.2 klein 9B", "files": ["diffusion_models/flux-2-klein-9b-nvfp4.safetensors",
                                                      "text_encoders/qwen_3_8b_fp4mixed.safetensors",
                                                      "vae/flux2-vae.safetensors"]},
    "qwen2511": {"label": "Qwen-Image-Edit-2511", "files": ["diffusion_models/qwen_image_edit_2511_fp8mixed.safetensors",
                                                             "text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
                                                             "vae/qwen_image_vae.safetensors",
                                                             "loras/Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"]},
}
MODELS_DIR = Path(os.environ.get("MODELS_DIR", "/models"))

# The variation set: 8 angles x 3 expressions + 3 outfits = 27 pictures. Wording is generic
# ("the character") so it fits a person or a creature; the character's own traits go in front.
ANGLES = [  # camera moves, said as camera moves: klein ignored "three-quarter view" / "low angle" as plain tags
    ("front", "Front view, the character faces the camera."),
    ("34left", "Rotate the camera 45 degrees around the character to the left: three-quarter view, body and face turned."),
    ("profile-left", "Rotate the camera 90 degrees: exact side profile view, the character faces left, only one eye visible."),
    ("34right", "Rotate the camera 45 degrees around the character to the right: three-quarter view, body and face turned."),
    ("profile-right", "Rotate the camera 90 degrees: exact side profile view, the character faces right, only one eye visible."),
    ("back34", "Camera behind the character: view from behind, the character looks back over the shoulder."),
    ("low", "Worm's-eye view: the camera is near the ground looking up at the character, strong perspective foreshortening."),
    ("high", "Bird's-eye view: the camera is high above looking down at the character, top of the head visible, "
             "strong perspective foreshortening."),
]
EXPRESSIONS = [("neutral", "calm neutral expression"), ("smile", "happy smile"),
               ("angry", "angry expression, frowning")]
OUTFITS = [("casual", "wearing plain casual clothes (hoodie and trousers) instead of the usual outfit"),
           ("coat", "wearing a long winter coat and a knitted scarf instead of the usual outfit"),
           ("sleep", "wearing striped pajamas instead of the usual outfit")]
STYLE = ("Keep the exact same black and white manga drawing style: monochrome, greyscale, clean ink lineart, "
         "screentone shading, plain white background.")


def variation_plan():
    items = [(f"{a}_{e}", f"{ad} The character has a {ed}.") for a, ad in ANGLES for e, ed in EXPRESSIONS]
    items += [(f"outfit-{o}", f"Show the same character in a three-quarter view, calm expression, {od}.")
              for o, od in OUTFITS]
    return items


def edit_prompt(model, change, traits):
    keep = f"Keep exactly the same character: {traits}" if traits else "Keep exactly the same character, face and outfit"
    if model == "klein9":
        return f"The character from image 1. {keep}. {change} {STYLE}"
    return f"{keep}. {change} {STYLE}"


# ---------- RAM job table ----------
_lock = threading.Lock()
_db = None
FIELDS = ["status", "progress", "total", "filename", "error", "elapsed", "kept"]


def init():
    global _db
    for d in (MANGA / "work", MANGA / "work" / "kept", MANGA / "work" / "out", MANGA / "characters", MANGA / "frames"):
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
    os.chmod(MANGA, 0o700)
    # on disk (not RAM) so a grid survives an app restart while the user is picking on the phone
    _db = sqlite3.connect(str(MANGA / "work" / "studio.db"), check_same_thread=False)
    _db.row_factory = sqlite3.Row
    with _db:
        _db.execute("""CREATE TABLE IF NOT EXISTS studio (
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, batch TEXT, kind TEXT, prompt TEXT,
            params TEXT, status TEXT, progress INTEGER, total INTEGER, filename TEXT, error TEXT,
            elapsed REAL, kept TEXT)""")
        _db.execute("UPDATE studio SET status='failed', error='interrupted by restart' "
                    "WHERE status IN ('queued','running')")


def add(batch, kind, prompt, params):
    with _lock, _db:
        return _db.execute(
            "INSERT INTO studio (ts,batch,kind,prompt,params,status,progress,total) VALUES (?,?,?,?,?,?,0,0)",
            (time.time(), batch, kind, prompt, json.dumps(params), "queued")).lastrowid


def update(jid, **f):
    cols = [c for c in f if c in FIELDS]
    if cols:
        with _lock, _db:
            _db.execute(f"UPDATE studio SET {', '.join(c + '=?' for c in cols)} WHERE id=?",
                        [f[c] for c in cols] + [jid])


def get(jid):
    r = _db.execute("SELECT * FROM studio WHERE id=?", (jid,)).fetchone()
    return dict(r) if r else None


def jobs(limit=300):
    rows = _db.execute("SELECT * FROM studio ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in reversed(rows):
        d = dict(r)
        d["params"] = json.loads(d["params"])
        out.append(d)
    return out


def batch_ids(batch):
    return [r["id"] for r in _db.execute("SELECT id FROM studio WHERE batch=? AND status IN ('queued','running')",
                                         (batch,))]


def new_batch():
    return uuid.uuid4().hex[:10]


# ---------- files ----------
def _safe(base, rel):
    p = (base / rel).resolve()
    if not str(p).startswith(str(base.resolve()) + os.sep) or not p.is_file():
        raise FileNotFoundError(rel)
    return p


def resolve(ref):
    """ref = 'out/<rel>' (RAM result) or 'manga/<rel>' (kept/character file)."""
    kind, _, rel = ref.partition("/")
    if kind == "out":
        return _safe(OUTPUT, rel)
    if kind == "manga":
        return _safe(MANGA, rel)
    raise FileNotFoundError(ref)


def stage(ref):
    """Copy a picture into ComfyUI's input (RAM) and return the LoadImage name."""
    name = f"{uuid.uuid4().hex[:12]}.png"
    shutil.copyfile(resolve(ref), INPUT / name)
    return f"studio/{name}"


def stage_bytes(data):
    name = f"{uuid.uuid4().hex[:12]}_mask.png"
    (INPUT / name).write_bytes(data)
    return f"studio/{name}"


def meta_for(ref):
    """Settings/lineage stored next to a kept or saved picture, or the job params for a RAM result."""
    p = resolve(ref)
    side = p.with_suffix(".json")
    if ref.startswith("manga/") and side.is_file():
        return json.loads(side.read_text())
    return {}


def keep(jid):
    job = get(jid)
    if not job or job["status"] != "done":
        raise ValueError("not finished")
    if job["kept"]:
        return job["kept"]
    kid = f"{time.strftime('%Y%m%d-%H%M%S')}-{jid}"
    dst = MANGA / "work" / "kept" / f"{kid}.png"
    shutil.copyfile(resolve(job["filename"]), dst)
    params = json.loads(job["params"])
    meta = {"kid": kid, "kind": job["kind"], "prompt": job["prompt"], "seed": params.get("seed"),
            "settings": params.get("settings", ANIMA_SETTINGS), "denoise": params.get("denoise"),
            "parent": params.get("parent"), "kept_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    dst.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    ref = f"manga/work/kept/{kid}.png"
    update(jid, kept=ref)
    return ref


def kept_list():
    out = []
    for j in sorted((MANGA / "work" / "kept").glob("*.json")):
        m = json.loads(j.read_text())
        if not m.get("hidden"):
            out.append({"ref": f"manga/work/kept/{j.stem}.png", **m})
    return out


def hide(ref):
    """Take a kept picture off the strip. Nothing is deleted: the file stays, its .json gets hidden=true."""
    side = resolve(ref).with_suffix(".json")
    m = json.loads(side.read_text())
    m["hidden"] = True
    side.write_text(json.dumps(m, indent=2))


NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


def save_character(ref, name, traits=""):
    name = name.strip().lower()
    if not NAME_RE.match(name):
        raise ValueError("name: a-z, 0-9, - or _ (max 40)")
    d = MANGA / "characters" / name
    if (d / "character.png").exists():
        raise ValueError(f"character '{name}' already exists")
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    shutil.copyfile(resolve(ref), d / "character.png")
    meta = meta_for(ref)
    meta.update({"name": name, "source": ref, "traits": traits.strip(), "saved_at": time.strftime("%Y-%m-%d %H:%M:%S")})
    (d / "character.json").write_text(json.dumps(meta, indent=2))
    return name


def characters():
    out = []
    for d in sorted((MANGA / "characters").iterdir()):
        if not (d / "character.png").is_file():
            continue
        m = json.loads((d / "character.json").read_text())
        runs = []
        for rj in sorted(d.glob("variations/*/*/run.json"), reverse=True):
            r = json.loads(rj.read_text())
            rel = rj.parent.relative_to(MANGA)
            r["dir"] = f"manga/{rel}"
            runs.append(r)
        out.append({"name": d.name, "ref": f"manga/characters/{d.name}/character.png", "meta": m, "runs": runs})
    return out


def model_ready(model):
    return all((MODELS_DIR / f).is_file() for f in EDIT_MODELS[model]["files"])


def start_run(name, model):
    d = MANGA / "characters" / name
    if not (d / "character.png").is_file():
        raise ValueError("no such character")
    run = time.strftime("%Y%m%d-%H%M%S")
    rd = d / "variations" / model / run
    rd.mkdir(parents=True, exist_ok=True)
    for p in (d / "variations", d / "variations" / model, rd):
        os.chmod(p, 0o700)
    info = {"model": model, "label": EDIT_MODELS[model]["label"], "run": run, "character": name,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"), "items": []}
    (rd / "run.json").write_text(json.dumps(info, indent=2))
    traits = json.loads((d / "character.json").read_text()).get("traits", "")
    return rd, f"manga/characters/{name}/character.png", traits


_run_lock = threading.Lock()


def record_variation(rd, item):
    with _run_lock:
        rj = Path(rd) / "run.json"
        info = json.loads(rj.read_text())
        info["items"].append(item)
        info["items"].sort(key=lambda x: x["file"])
        rj.write_text(json.dumps(info, indent=2))


# ---------- Frames (one standalone picture per script line; no page layout yet) ----------
FRAME_SHAPES = {"wide": (1344, 768), "square": (1024, 1024), "tall": (832, 1216), "strip": (1536, 640)}
FRAME_METHODS = {"anima": "Anima (character tags)", "klein9": "klein 9B + saved character pictures",
                 "restyle": "Anima redraw of a picture (img2img)"}


def _frames_file(project):
    if not NAME_RE.match(project):
        raise ValueError("project: a-z, 0-9, - or _")
    d = MANGA / "frames" / project
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d / "frames.json"


def frames_get(project):
    f = _frames_file(project)
    return json.loads(f.read_text()) if f.is_file() else {"project": project, "lines": []}


def frames_put(project, data):
    f = _frames_file(project)
    lines = []
    for ln in data.get("lines", [])[:40]:
        lines.append({k: ln[k] for k in ("text", "shape", "prompt", "method", "chars", "chosen", "chosen_meta",
                                          "variants", "final") if ln.get(k) is not None})
    out = {"project": project, "lines": lines, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    f.write_text(json.dumps(out, indent=2))
    return out


def frame_pick(project, line, jid, slot=""):
    job = get(jid)
    if not job or job["status"] != "done":
        raise ValueError("not finished")
    data = frames_get(project)
    if not 0 <= line < len(data["lines"]):
        raise ValueError("no such line")
    d = _frames_file(project).parent
    name = f"line-{line + 1:02d}{'-' + slot if slot else ''}.png"
    if (d / name).exists():  # never overwrite an earlier pick: keep it under a numbered name
        n = 2
        while (d / f"line-{line + 1:02d}-v{n}.png").exists():
            n += 1
        name = f"line-{line + 1:02d}{'-' + slot if slot else ''}-v{n}.png"
    shutil.copyfile(resolve(job["filename"]), d / name)
    params = json.loads(job["params"])
    meta = {"prompt": job["prompt"], "seed": params.get("seed"), "method": params.get("method"),
            "denoise": params.get("denoise"), "src": params.get("src"), "job": jid}
    if slot:  # a comparison variant (e.g. A = Anima restyle); the chosen frame stays as it is
        if not data["lines"][line].get("variants"):
            data["lines"][line]["variants"] = {}
        data["lines"][line]["variants"][slot] = {"ref": f"manga/frames/{project}/{name}", **meta}
        return frames_put(project, data)
    data["lines"][line]["chosen"] = f"manga/frames/{project}/{name}"
    data["lines"][line]["chosen_meta"] = {"prompt": job["prompt"], "seed": params.get("seed"),
                                          "method": params.get("method"), "shape": params.get("shape"),
                                          "chars": params.get("chars"), "job": jid}
    return frames_put(project, data)
