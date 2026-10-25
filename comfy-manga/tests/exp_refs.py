"""One-off: which reference layout keeps place/props without split panels or copied framing (bike story, page id arg)."""
import json, sys, uuid
import comfy, db, graphs, layout, media, sheets, worker
db.init()
pid = int(sys.argv[1]); out = db.APP_DIR.parent / "bench" / "exp"; out.mkdir(parents=True, exist_ok=True)
pg = db.get("pages", pid); sc = pg["scene"]; plate, props = sc["plate"]["image_id"], sc["props"]["image_id"]
nori = db.one("SELECT * FROM characters WHERE slug='nori'")
import refs
def up(data): return comfy.upload(data, f"exp_{uuid.uuid4().hex[:8]}.png")
def run(prompt, names, w, h, seed):
    cid = "exp"; p = comfy.submit(graphs.klein_refs(prompt, names, w, h, seed), cid)
    imgs, _ = comfy.outputs(comfy.track(p, cid)); return comfy.view(imgs[-1])
ONE = "One single picture filling the whole frame: not a comic page, no split screen, no grid, no inset panels."
for idx in (2, 3):
    pn = pg["panels"][idx]; w, h = graphs.fit_size(layout.aspects()[idx], 1.0)
    prev = pg["panels"][idx - 1]["image_id"]
    ids = refs.pick(nori, pn["line"], 3)
    sheet_up = up(sheets.sheet([media.read(i) for i in ids]))
    src_up = up(sheets.upper(__import__("PIL.Image").Image.open(__import__("io").BytesIO(media.read(nori["source_image"])))).tobytes()) if False else None
    base = pn["prompt"].split(" Image ")[0]  # template prompt without the old extras
    base = pn["prompt"][:pn["prompt"].find("Image 2")] if "Image 2" in pn["prompt"] else pn["prompt"]
    tail = " Keep each character's face, hair and clothes exactly as in the reference pictures. " + graphs.STYLE + " No text, no letters, no speech bubbles, no panel borders."
    V = {
      "A_stack_prev": ([sheet_up, up(sheets.stack([media.read(plate), media.read(props)])), worker._upload(prev)],
          "Image 2 shows the place and the objects of this scene (no people): same place and objects. Image 3 is the previous panel: same place, objects, light; new camera angle and new poses."),
      "B_plate_props": ([sheet_up, worker._upload(plate), worker._upload(props)],
          "Image 2 is only a reference for what the place looks like and image 3 only for what the bike looks like; frame this panel as the scene says, do not copy their composition."),
      "C_props_prev": ([sheet_up, worker._upload(props), worker._upload(prev)],
          "Image 2 is only a reference for what the bike looks like. Image 3 is the previous panel: same place, light and time of day, but frame this panel as the scene says; do not copy its composition."),
      "D_props_prev_one": ([sheet_up, worker._upload(props), worker._upload(prev)],
          "Image 2 is only a reference for what the bike looks like. Image 3 is the previous panel: same place, light and time of day, but frame this panel as the scene says; do not copy its composition. " + ONE),
      "E_plate_props_one": ([sheet_up, worker._upload(plate), worker._upload(props)],
          "Image 2 is only a reference for what the place looks like and image 3 only for what the bike looks like; frame this panel as the scene says, do not copy their composition. " + ONE),
    }
    for k, (names, extra) in V.items():
        prompt = base.strip() + " " + extra + tail
        data = run(prompt, names, w, h, 4242 + idx)
        (out / f"p{idx+1}_{k}.png").write_bytes(data); print(idx + 1, k, flush=True)
