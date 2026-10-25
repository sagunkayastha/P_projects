"""Panel adherence bench (user priority 2026-10-25: panels do not follow the line, same angles/poses, random
backgrounds). Fixed 8-line set (panelset.py), test characters only, same seed per line; one variant per hypothesis.
Runs inside the test app container (uses the app's modules and the shared ComfyUI):

  docker cp tests/panelset.py tests/bench_quality.py tests/bench_panels.py manga-app-test:/app/
  docker exec manga-app-test python bench_panels.py <round> <variant,...>
Output: APP_DIR/../bench/panels/<round>/<variant>_<k>_<name>.png (+ _comp.png for two-stage), contact.png,
prompts.json (with seconds per panel).

Variants
  base      the app today: template + sheets + shot/once/ink wording (pages._extras)        (reference)
  order     (d) short prompt, the shot + pose + place first, one action, then the cast
  noref     (a) diagnostic: klein text-to-image, no character pictures (does the ref anchor the composition?)
  two_klein (a) compose without refs (klein), then klein edit: composition = image 1, put the character(s) in
  two_anima (a) same, composition by Anima (beretMix; Danbooru-trained, see licence note in the report)
  stick     (b) sheets + a stick-figure pose/camera guide as the last reference picture
  cfg3      (c) base prompt, cfg 3 + 8 steps (the distilled klein; no non-distilled klein on disk)
"""
import json
import sys
import time

import db
import graphs
import pages
import workflows
import writer
from bench_quality import FONT, chars_of, ref_names, run, up
from panelset import LOOKS, SET, stick_png

SEED = 9100
DESC = {"nori": "a young woman with a short black bob, round glasses, a striped scarf, a long cardigan and a pleated "
                "skirt",
        "bram": "an old man with a long white beard, a black flat cap, a dark vest over a light shirt and dark trousers"}


def size(item):
    return graphs.SHAPES[item["shape"]]


def generic(line, chs):
    """The line with each name replaced by a plain description (no reference pictures)."""
    for c in chs:
        line = line.replace(c["name"] + "'s", DESC[c["slug"]] + "'s").replace(c["name"], DESC[c["slug"]])
    return line


def klein_t2i(prompt, w, h, seed, steps=4, cfg=1.0):
    wf = workflows.klein9_refs(prompt, ["none.png"], w, h, seed, "p")
    for k in [k for k in wf if k.startswith("6")]:  # drop the dummy reference
        del wf[k]
    wf["15"]["inputs"]["positive"], wf["15"]["inputs"]["negative"] = ["7", 0], ["8", 0]
    wf["12"]["inputs"]["steps"], wf["15"]["inputs"]["cfg"] = steps, cfg
    return graphs._preview(workflows.bw_finish(wf, ["17", 0], w, h, "p", save_id="18"))


def klein_r(prompt, names, w, h, seed, steps=4, cfg=1.0):
    wf = workflows.klein9_refs(prompt, names, w, h, seed, "p")
    wf["12"]["inputs"]["steps"], wf["15"]["inputs"]["cfg"] = steps, cfg
    return graphs._preview(workflows.bw_finish(wf, ["17", 0], w, h, "p", save_id="18"))


def base_prompt(item, chs):
    line = item["line"]
    p = writer.template(line, [{"name": c["name"], "n": 1, "sheet": True} for c in chs], None)
    return p.replace(graphs.STYLE, pages._extras(None, None, None, [c["name"] for c in chs], line) + " " +
                     graphs.STYLE, 1)


def order_prompt(item, chs):
    """Shot + action + place first and short; who is who after; style last."""
    cast = writer.cast_text([{"name": c["name"], "n": 1, "sheet": True} for c in chs])
    shot = pages.shot_text(item["line"])
    return (f"{item['line']}. {shot} {cast} Same face, hair and clothes as the reference sheets; the pose and camera "
            f"come only from this text. {pages.once_text([c['name'] for c in chs])} {pages.ONE} {pages.INK} "
            f"{graphs.STYLE} No text, no speech bubbles.").replace("  ", " ")


def compose_prompt(item, chs):
    return (f"Manga panel. {generic(item['line'], chs)}. {pages.shot_text(item['line'])} {pages.ONE} {pages.INK} "
            f"{graphs.STYLE} No text, no speech bubbles.").replace("  ", " ")


def insert_prompt(item, chs, first_ref):
    who = " and ".join(f"{c['name']} (the person in image {first_ref + i})" for i, c in enumerate(chs))
    desc = " and ".join(LOOKS[c["slug"]] for c in chs)
    return (f"Image 1 is the finished panel layout: keep its camera angle, framing, background and every pose exactly. "
            f"Redraw {desc} in image 1 as {who}: their face, hair and clothes from the reference sheet(s), nothing "
            f"else changes. {pages.once_text([c['name'] for c in chs])} {pages.INK} {graphs.STYLE} "
            f"No text, no speech bubbles.").replace("  ", " ")


def free():
    """Drop cached models in ComfyUI (RAM guard: klein 9B alone holds ~12.7 GB)."""
    import urllib.request

    import comfy
    req = urllib.request.Request(comfy.COMFY + "/free", json.dumps({"unload_models": True, "free_memory": True}).encode(),
                                 {"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=60).read()


def anima_comps(out, v):
    """Anima compositions for all lines in one block (one model family at a time), then free it."""
    made = False
    for k, item in enumerate(SET):
        f = out / f"{v}_{k + 1}_{item['name']}_comp.png"
        if f.exists():
            continue
        chs = chars_of(item["who"])
        w, h = size(item)
        f.write_bytes(run(graphs.anima_bw(generic(item["line"], chs) + ", " +
                                          pages.shot_text(item["line"]) + ", detailed manga illustration",
                                          w, h, SEED + k)))
        made = True
        print(v, "comp", item["name"], flush=True)
    if made:
        free()


def main():
    rnd, variants = sys.argv[1], sys.argv[2].split(",")
    db.init()
    out = db.APP_DIR.parent / "bench" / "panels" / rnd
    out.mkdir(parents=True, exist_ok=True)
    rows, prompts, times = [], {}, {}
    for v in variants:
        pics, t0 = [], time.time()
        if v == "two_anima":
            anima_comps(out, v)
        for k, item in enumerate(SET):
            f = out / f"{v}_{k + 1}_{item['name']}.png"
            chs = chars_of(item["who"])
            w, h = size(item)
            seed = SEED + k
            if f.exists():
                pics.append(f.read_bytes())
                continue
            if v in ("base", "cfg3", "stick", "order"):
                names, _ = ref_names(chs, item["line"], "sheet")
                pr = order_prompt(item, chs) if v == "order" else base_prompt(item, chs)
                if v == "stick":
                    st = stick_png(item["name"], w, h)
                    if st:
                        names.append(up(st))
                        pr = pr.replace(graphs.STYLE, f"Image {len(names)} is a stick-figure guide for the camera "
                                        f"and the pose: place the character(s) in exactly that pose, position and "
                                        f"size in the frame, drawn as real people, no stick figure. " + graphs.STYLE, 1)
                wf = klein_r(pr, names, w, h, seed, *((8, 3.0) if v == "cfg3" else (4, 1.0)))
                data = run(wf)
            elif v == "noref":
                pr = compose_prompt(item, chs)
                data = run(klein_t2i(pr, w, h, seed))
            elif v in ("two_klein", "two_anima"):
                cp = compose_prompt(item, chs)
                cf = out / f"{v}_{k + 1}_{item['name']}_comp.png"
                if v == "two_klein":
                    comp = run(klein_t2i(cp, w, h, seed))
                    cf.write_bytes(comp)
                else:
                    comp = cf.read_bytes()
                names, _ = ref_names(chs, item["line"], "sheet")
                pr = insert_prompt(item, chs, 2)
                data = run(klein_r(pr, [up(comp)] + names, w, h, seed))
                prompts[f"{v}/{item['name']}/compose"] = cp
            else:
                raise ValueError(v)
            f.write_bytes(data)
            pics.append(data)
            prompts[f"{v}/{item['name']}"] = pr
            print(v, item["name"], flush=True)
        times[v] = round((time.time() - t0) / len(SET), 1)
        rows.append(pics)
    sheet(rows, [f"{v}\n{times[v]} s" for v in variants], out / "contact.png")
    old = json.loads((out / "prompts.json").read_text()) if (out / "prompts.json").exists() else {}
    old.setdefault("prompts", {}).update(prompts)
    old.setdefault("sec_per_panel", {}).update({v: t for v, t in times.items() if t > 1})
    old["set"] = SET
    (out / "prompts.json").write_text(json.dumps(old, indent=1))
    print(json.dumps(times))


def sheet(rows, labels, path, heads=None):
    import io

    from PIL import Image, ImageDraw, ImageFont
    cell, left = 260, 150
    font = ImageFont.truetype(FONT, 16)
    heads = heads or [f"{k + 1} {item['name']}" for k, item in enumerate(SET)]
    im = Image.new("RGB", (left + cell * max(len(heads), max(len(r) for r in rows)), 26 + cell * len(rows)), "white")
    d = ImageDraw.Draw(im)
    for k, t in enumerate(heads):
        d.text((left + k * cell + 4, 4), t, fill="black", font=font)
    for r, (lab, pics) in enumerate(zip(labels, rows)):
        d.text((6, 26 + r * cell + cell // 2 - 10), lab, fill="black", font=font)
        for k, data in enumerate(pics):
            t = Image.open(io.BytesIO(data)).convert("RGB")
            t.thumbnail((cell - 6, cell - 6))
            im.paste(t, (left + k * cell + (cell - t.width) // 2, 26 + r * cell + (cell - t.height) // 2))
    im.save(path)


if __name__ == "__main__":
    main()
