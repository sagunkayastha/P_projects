"""Pose-copy bench (inside the test app container): same action lines + seeds, old references (source + best view,
full pictures) vs new (one upper-body sheet + "new pose" wording). Saves pictures for the VLM judge.

  docker cp tests/bench_pose.py manga-app-test:/app/ && docker exec manga-app-test python bench_pose.py nori
"""
import io
import json
import sys
import uuid

import PIL.Image

import comfy
import db
import graphs
import media
import refs
import sheets
import worker
import writer

VAGUE = ["{n} waits at a bus stop in the evening", "{n} talks with a friend in a classroom",
         "{n} at the beach on a windy day", "{n} in a library"]
LINES = ["{n} sits cross-legged on the floor reading a book", "{n} jumps over a puddle, arms spread",
         "{n} lies on her back in the grass looking at the sky", "{n} crouches down to pet a small cat"]
SEEDS = [7, 8]
ONE = "One single picture filling the whole frame: not a comic page, no split screen, no grid, no inset panels."


def mixed(uppers, full, tile_h=640, gap=24):  # tested 2026-10-24: brings the pose copying back
    """Upper-body crops of some views + the whole source figure at the same height (so it is small): the face
    and clothes stay big, the full outfit (shoes, skirt) stays visible, the full-body pose is a minor part."""
    a = sheets.sheet(uppers, tile_h, gap, crop=True)
    b = sheets.sheet([full], tile_h, gap, crop=False)
    ia, ib = PIL.Image.open(io.BytesIO(a)), PIL.Image.open(io.BytesIO(b))
    out = PIL.Image.new("RGB", (ia.width + ib.width - gap, ia.height), "white")
    out.paste(ia, (0, 0))
    out.paste(ib, (ia.width - gap, 0))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def run(prompt, names, seed):
    w, h = graphs.SHAPES["tall"]
    pid = comfy.submit(graphs.klein_refs(prompt, names, w, h, seed), "pose")
    imgs, _ = comfy.outputs(comfy.track(pid, "pose"))
    return comfy.view(imgs[-1])


def main():
    db.init()
    ch = db.one("SELECT * FROM characters WHERE slug=?", (sys.argv[1],))
    out = db.APP_DIR.parent / "bench" / "pose"
    out.mkdir(parents=True, exist_ok=True)
    (out / "source.png").write_bytes(media.read(ch["source_image"]))
    lines = VAGUE if len(sys.argv) > 2 and sys.argv[2] == "vague" else LINES
    pre = "vague_" if lines is VAGUE else ""
    for li, line in enumerate(lines):
        text = line.format(n=ch["name"])
        best = [r for r in ch["refs"] if r != ch["source_image"]][0]
        old_names = [worker._upload(ch["source_image"]), worker._upload(best)]
        old_prompt = (f"{writer.cast_text([{'name': ch['name'], 'n': 2}])} {text}. Keep each character's face, hair, "
                      f"body and outfit exactly as in the reference pictures. {graphs.STYLE} No text, no letters, no speech bubbles.")
        ids = refs.pick(ch, text, 3)
        data = sheets.sheet([media.read(i) for i in ids])
        new_names = [comfy.upload(data, f"pose_{uuid.uuid4().hex[:8]}.png")]
        mix = mixed([media.read(i) for i in ids[:2]], media.read(ch["source_image"]))
        mix_names = [comfy.upload(mix, f"pose_{uuid.uuid4().hex[:8]}.png")]
        new_prompt = (f"{writer.cast_text([{'name': ch['name'], 'n': 1, 'sheet': True}])} {text}. Keep each character's "
                      f"face, hair and clothes exactly as in the reference pictures. Draw a new pose that fits the text; do "
                      f"not copy the pose or framing of the reference pictures. {ONE} {graphs.STYLE} No text, no letters, no speech bubbles.")
        for s in SEEDS[:1]:
            (out / f"{pre}old_l{li}_s{s}.png").write_bytes(run(old_prompt, old_names, s))
            (out / f"{pre}new_l{li}_s{s}.png").write_bytes(run(new_prompt, new_names, s))
            (out / f"{pre}mix_l{li}_s{s}.png").write_bytes(run(new_prompt, mix_names, s))
            print(li, s, flush=True)
    (out / "sheet_example.png").write_bytes(data)
    (out / "mix_example.png").write_bytes(mix)
    print(json.dumps({"done": True}))


if __name__ == "__main__":
    main()
