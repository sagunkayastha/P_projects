"""Picture-quality bench (inside the test app container): a fixed 6-panel test set with the test characters,
drawn with different settings / models / reference handling, same seeds. Writes PNGs, a labelled contact
sheet per round and prompts.json for the reviewers.

  docker cp tests/bench_quality.py manga-app-test:/app/ && docker exec manga-app-test python bench_quality.py <round> <variant,...>
Variants: see VARIANTS below. Output: APP_DIR/../bench/quality/<round>/
"""
import io
import json
import sys
import time
import uuid

from PIL import Image, ImageDraw, ImageFont

import comfy
import db
import graphs
import media
import pages
import refs
import sheets
import workflows
import writer

SET = [  # (name, line, characters, shape)
    ("wide", "Wide establishing shot: Nori walks down a busy shopping street at noon", ["nori"], (1344, 768)),
    ("closeup", "Close-up of Nori's face, she is surprised, eyes wide, mouth open", ["nori"], (1024, 1024)),
    ("action", "Nori jumps over a low fence in a park, dynamic action pose, speed lines", ["nori"], (832, 1216)),
    ("two", "Nori and Bram argue across a small kitchen table", ["nori", "bram"], (1344, 768)),
    ("interior", "Medium shot: Bram reads a newspaper in an old library with tall shelves", ["bram"], (832, 1216)),
    ("lowangle", "Low angle shot looking up at Bram standing on a rooftop at night, city lights below", ["bram"], (832, 1216)),
]
SEED = 5150
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def run(wf):
    cid = "q" + uuid.uuid4().hex[:6]
    pid = comfy.submit(wf, cid)
    imgs, _ = comfy.outputs(comfy.track(pid, cid))
    return comfy.view(imgs[-1])


def up(data):
    return comfy.upload(data, f"q_{uuid.uuid4().hex[:10]}.png")


def chars_of(slugs):
    return [db.one("SELECT * FROM characters WHERE slug=?", (s,)) for s in slugs]


def ref_names(chs, line, mode):
    if mode == "sheet":  # current app: one upper-body sheet per character
        n = 3 if len(chs) == 1 else 2
        return [up(sheets.sheet([media.read(i) for i in refs.pick(ch, line, n)])) for ch in chs], 1
    if mode == "full2":  # old app: source + best view, full pictures
        out = []
        for ch in chs:
            best = [r for r in ch["refs"] if r != ch["source_image"]][0]
            out += [up(media.read(ch["source_image"])), up(media.read(best))]
        return out, 2
    if mode == "src1":  # only the source picture, full
        return [up(media.read(ch["source_image"])) for ch in chs], 1
    raise ValueError(mode)


def prompt_for(line, chs, per, sheet, extra=""):
    cast = [{"name": c["name"], "n": per, "sheet": sheet, "traits": c.get("traits") or ""} for c in chs]
    p = writer.template(line, cast, None)
    pose = ("Draw new poses that fit the action; do not copy the pose or framing of any reference picture. "
            if sheet else "")
    return p.replace(graphs.STYLE, pose + pages.ONE + " " + extra + graphs.STYLE, 1)


def klein(prompt, names, w, h, seed, steps=4, bw=True, unet=None, clip=None, cfg=None, sampler=None):
    wf = workflows.klein9_refs(prompt, names, w, h, seed, "q")
    wf["12"]["inputs"]["steps"] = steps
    if unet:
        wf["1"]["inputs"]["unet_name"] = unet
    if clip:
        wf["2"]["inputs"]["clip_name"] = clip
    if cfg:
        wf["15"]["inputs"]["cfg"] = cfg
    if sampler:
        wf["14"]["inputs"]["sampler_name"] = sampler
    if bw:
        return graphs._preview(workflows.bw_finish(wf, ["17", 0], w, h, "q", save_id="18"))
    return graphs._preview(wf)


def size(shape, mp):
    w, h = shape
    return graphs.fit_size(w / h, mp)


VARIANTS = {
    # name: dict of options
    "base": {},                                   # the deployed app: klein 9B, 4 steps, 1 MP, sheet refs, greyscale
    "steps8": {"steps": 8},
    "steps12": {"steps": 12},
    "color": {"bw": False},                       # no greyscale conversion (see what klein draws)
    "mp16": {"mp": 1.6},                          # bigger picture
    "refs_full2": {"refs": "full2"},              # old reference handling
    "refs_src1": {"refs": "src1"},
    "klein4b": {"unet": "flux-2-klein-4b-nvfp4.safetensors", "clip": "qwen_3_4b_fp8_mixed.safetensors"},
    "inkwords": {"extra": "Bold confident G-pen ink lines with varied line weight, solid black fills, hatching and "
                          "screentone dots for shading, white paper, crisp high-contrast printed manga page look. "},
    "anima_pass35": {"anima": 0.35},               # klein picture, then an Anima img2img pass (manga linework)
    "anima_pass50": {"anima": 0.50},
}


def anima_pass(png, line, w, h, seed, denoise):
    name = up(png)
    wf = workflows.anima_i2i(graphs.ANIMA_PREFIX + line + ", detailed manga illustration", name, w, h, seed, "q",
                             denoise, neg=graphs.ANIMA_NEG)
    wf["8"]["inputs"]["model"] = workflows.with_loras(wf, [("Mangalike_Anima.safetensors", 0.8),
                                                           ("pearly_cross_hatching_animav2_style.safetensors", 0.6)])
    return run(graphs._preview(workflows.bw_finish(wf, ["9", 0], w, h, "q")))


def sheet_png(rows, labels, out):
    cell = 300
    font = ImageFont.truetype(FONT, 18)
    W = 170 + cell * len(SET)
    H = 30 + cell * len(rows)
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    for k, (name, *_x) in enumerate(SET):
        d.text((170 + k * cell + 6, 6), f"{k + 1} {name}", fill="black", font=font)
    for r, (lab, pics) in enumerate(zip(labels, rows)):
        d.text((6, 30 + r * cell + cell // 2 - 10), lab, fill="black", font=font)
        for k, data in enumerate(pics):
            t = Image.open(io.BytesIO(data)).convert("RGB")
            t.thumbnail((cell - 6, cell - 6))
            im.paste(t, (170 + k * cell + (cell - t.width) // 2, 30 + r * cell + (cell - t.height) // 2))
    im.save(out)


def main():
    rnd, names = sys.argv[1], sys.argv[2].split(",")
    db.init()
    out = db.APP_DIR.parent / "bench" / "quality" / rnd
    out.mkdir(parents=True, exist_ok=True)
    rows, prompts, times = [], {}, {}
    for v in names:
        o = VARIANTS[v]
        pics = []
        t0 = time.time()
        for k, (name, line, slugs, shape) in enumerate(SET):
            chs = chars_of(slugs)
            nm, per = ref_names(chs, line, o.get("refs", "sheet"))
            w, h = size(shape, o.get("mp", 1.0))
            pr = prompt_for(line, chs, per, o.get("refs", "sheet") == "sheet", o.get("extra", ""))
            data = run(klein(pr, nm, w, h, SEED + k, o.get("steps", 4), o.get("bw", True), o.get("unet"), o.get("clip")))
            if o.get("anima"):
                data = anima_pass(data, line, w, h, SEED + k, o["anima"])
            (out / f"{v}_{k + 1}_{name}.png").write_bytes(data)
            pics.append(data)
            prompts[f"{v}/{name}"] = pr
            print(v, name, flush=True)
        times[v] = round((time.time() - t0) / len(SET), 1)
        rows.append(pics)
    sheet_png(rows, [f"{v}\n{times[v]} s" for v in names], out / "contact.png")
    (out / "prompts.json").write_text(json.dumps({"set": SET, "variants": {v: VARIANTS[v] for v in names},
                                                  "sec_per_panel": times, "prompts": prompts}, indent=1))
    print(json.dumps(times))


if __name__ == "__main__":
    main()
