"""Background-consistency bench (hypothesis e): one named place, 4 panels, same seeds; how the place reaches
klein. Runs inside the test app container (after bench_panels.py is copied in):

  docker cp tests/bench_bg.py manga-app-test:/app/ && docker exec manga-app-test python bench_bg.py <round> <variant,...>
Variants
  text   no place picture, the place words only (bible text in every prompt)
  plate  the app today: Anima place plate as a reference, "only a reference for the place, do not copy composition"
  turn   plate as image 1 + "same location as image 1, the camera is turned toward <part of the room>"
  crop   the part of the wide plate this panel looks at, cropped, as the background reference
Output: APP_DIR/../bench/panels/<round>/bg_<variant>_<k>_<name>.png, plate.png, contact_bg.png
"""
import io
import json
import sys

import db
import graphs
import pages
import writer
from bench_panels import free, klein_r, run, sheet
from bench_quality import chars_of, ref_names, up
from PIL import Image

BIBLE = ("location: small old clock shop, long wooden counter in the middle, a workbench with tools on the left wall, "
         "a wall of cuckoo clocks on the right wall, a front door with a big shop window; time and light: afternoon "
         "sun through the shop window")
# (name, line, who, shape, camera direction, crop box of the wide plate as fractions (x0, y0, x1, y1))
LINES = [("enter", "Wide shot: Nori steps into the clock shop, Bram stands behind the counter", ["nori", "bram"],
          "wide", "toward the counter in the middle of the shop", (0.0, 0.0, 1.0, 1.0)),
         ("bench", "Medium shot: Bram looks up from his workbench, a magnifier in his hand", ["bram"], "tall",
          "toward the workbench on the left wall", (0.0, 0.0, 0.45, 1.0)),
         ("clocks", "Nori stares at the wall of cuckoo clocks, amazed", ["nori"], "tall",
          "toward the wall of cuckoo clocks on the right", (0.55, 0.0, 1.0, 1.0)),
         ("door", "Over-the-shoulder shot from behind Bram at the counter, Nori waiting by the door", ["bram", "nori"],
          "wide", "toward the front door and the big shop window", (0.2, 0.0, 0.8, 1.0))]
SEED = 9300


def main():
    rnd, variants = sys.argv[1], sys.argv[2].split(",")
    db.init()
    out = db.APP_DIR.parent / "bench" / "panels" / rnd
    out.mkdir(parents=True, exist_ok=True)
    pf = out / "plate.png"
    if not pf.exists():
        w, h = graphs.SHAPES["wide"]
        pf.write_bytes(run(graphs.anima_bw(pages.scene_prompts(BIBLE)["plate"], w, h, SEED)))
        free()  # one model family at a time
    plate = pf.read_bytes()
    rows, prompts = [], {}
    for v in variants:
        pics = []
        for k, (name, line, who, shape, toward, box) in enumerate(LINES):
            f = out / f"bg_{v}_{k + 1}_{name}.png"
            if f.exists():
                pics.append(f.read_bytes())
                continue
            chs = chars_of(who)
            w, h = graphs.SHAPES[shape]
            names, _ = ref_names(chs, line, "sheet")
            cast = [{"name": c["name"], "n": 1, "sheet": True} for c in chs]
            bible = BIBLE if v == "text" else ""
            pr = writer.template(line, cast, None, bible)
            extra = pages._extras(None, None, None, [c["name"] for c in chs], line)
            if v == "plate":
                names.append(up(plate))
                extra = pages._extras(len(names), None, None, [c["name"] for c in chs], line)
            elif v == "turn":
                names.append(up(plate))
                extra = (f"Image {len(names)} shows the same location: keep its furniture, walls, light and time of "
                         f"day; the camera is turned {toward}, so show that part of the room as the scene says. "
                         + extra)
            elif v == "crop":
                im = Image.open(io.BytesIO(plate))
                x0, y0, x1, y1 = box
                c = im.crop((int(x0 * im.width), int(y0 * im.height), int(x1 * im.width), int(y1 * im.height)))
                buf = io.BytesIO()
                c.save(buf, "PNG")
                names.append(up(buf.getvalue()))
                extra = (f"Image {len(names)} is the background of this panel ({toward}): draw the scene in front of "
                         f"exactly this background, from the camera angle the scene says. " + extra)
            pr = pr.replace(graphs.STYLE, extra + " " + graphs.STYLE, 1)
            data = run(klein_r(pr, names, w, h, SEED + k))
            f.write_bytes(data)
            pics.append(data)
            prompts[f"{v}/{name}"] = pr
            print(v, name, flush=True)
        rows.append(pics)
    sheet_bg(rows, variants, plate, out / "contact_bg.png")
    (out / "prompts_bg.json").write_text(json.dumps({"bible": BIBLE, "lines": LINES, "prompts": prompts}, indent=1))


def sheet_bg(rows, labels, plate, path):
    """Contact sheet: the plate in the first column, then the 4 panels per variant."""
    buf = io.BytesIO()
    Image.open(io.BytesIO(plate)).convert("RGB").save(buf, "PNG")
    sheet([[buf.getvalue()] + r for r in rows], [f"bg_{v}" for v in labels], path,
          ["plate"] + [f"{k + 1} {x[0]}" for k, x in enumerate(LINES)])


if __name__ == "__main__":
    main()
