"""Character consistency bench (runs INSIDE the test app container, on its own test data).

Same panel lines + same seeds, drawn with different reference choices, then each picture's face similarity
to the character's SOURCE picture (MangaRefScore: anime-face crop + SigLIP2 cosine).

  docker cp tests/bench_consistency.py manga-app-test:/app/ && \
  docker exec manga-app-test python bench_consistency.py <char slug> <variant,...> [seeds]

Variants: base = source + the best-scored view, 2 pictures (the old _char_refs), no trait list
          b1   = source + 2 views matched to the panel's angle/outfit/expression (refs.pick), no trait list
          b12  = b1 + the character's trait list in the prompt
Results: APP_DIR/../bench/<slug>/<variant>/*.png + results.json (appended).
"""
import json
import sys
import time
import uuid

import comfy
import db
import graphs
import refs
import worker
import writer

LINES = [
    "{n} seen in side profile, looking out of a train window",
    "low angle shot: {n} stands at the top of a staircase",
    "{n} laughs happily at a cafe table",
    "close-up of {n}'s face, angry",
    "{n} walks away down a street, seen from behind, looking back over the shoulder",
    "high angle shot from above: {n} sits on a park bench reading a book",
]
SEEDS = [11, 22]


def run(wf):
    cid = uuid.uuid4().hex
    pid = comfy.submit(wf, cid)
    return comfy.outputs(comfy.track(pid, cid))


def main():
    db.init()
    slug, variants = sys.argv[1], sys.argv[2].split(",")
    seeds = [int(x) for x in sys.argv[3].split(",")] if len(sys.argv) > 3 else SEEDS
    ch = db.one("SELECT * FROM characters WHERE slug=?", (slug,))
    out = db.APP_DIR.parent / "bench" / slug
    w, h = graphs.SHAPES["tall"]
    src = worker._upload(ch["source_image"])
    rows = []
    for var in variants:
        d = out / var
        d.mkdir(parents=True, exist_ok=True)
        names, meta = [], []
        for li, line in enumerate(LINES):
            text = line.format(n=ch["name"])
            if var == "base":
                best = [r for r in (ch["refs"] or []) if r != ch["source_image"]]
                ids = [ch["source_image"], best[0] if best else ch["source_image"]]
                cast = [{"name": ch["name"], "n": 2}]
            else:
                ids = refs.pick(ch, text, 3)
                cast = [{"name": ch["name"], "n": 3, "traits": (ch.get("traits") or "") if var == "b12" else ""}]
            prompt = writer.template(text, cast, None)
            up = [worker._upload(i) for i in ids]
            for s in seeds:
                t = time.time()
                imgs, _ = run(graphs.klein_refs(prompt, up, w, h, s))
                data = comfy.view(imgs[-1])
                fn = d / f"l{li}_s{s}.png"
                fn.write_bytes(data)
                names.append(comfy.upload(data, f"bench_{slug}_{var}_{li}_{s}.png"))
                meta.append({"variant": var, "line": li, "seed": s, "refs": ids,
                             "labels": [(ch["scores"] or {}).get(str(i), {}).get("label", "source") for i in ids],
                             "sec": round(time.time() - t, 1)})
                print(var, li, s, meta[-1]["labels"], meta[-1]["sec"], flush=True)
        _, ui = run(graphs.score(src, names))
        res = json.loads(ui["scores"][0])["items"]
        for m, r in zip(meta, res):
            m.update(face_sim=r["face_sim"], whole_sim=r["whole_sim"])
        rows += meta
        fsl = [m["face_sim"] for m in meta if m["face_sim"] is not None]
        print(f"== {var}: faces found {len(fsl)}/{len(meta)}, mean face_sim "
              f"{sum(fsl) / max(1, len(fsl)):.4f}, min {min(fsl) if fsl else None}, "
              f"mean whole {sum(m['whole_sim'] for m in meta) / len(meta):.4f}", flush=True)
    with open(out / "results.json", "a") as f:
        f.write(json.dumps({"ts": time.strftime("%F %T"), "traits": ch.get("traits"), "rows": rows}) + "\n")


if __name__ == "__main__":
    main()
