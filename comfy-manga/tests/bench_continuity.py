"""Continuity + pose bench (runs INSIDE the test app container; makes pages through the app's own API).

  docker cp tests/bench_continuity.py manga-app-test:/app/ && docker exec manga-app-test python bench_continuity.py <tag>

Same 3 neutral stories with fixed seeds; run once with MANGA_CONT=0 (old) and once with MANGA_CONT=1 (new).
Per page: face similarity of each panel to its character's source, whole-picture similarity to the source
(high = pose/framing copied from the reference), and panel-to-panel whole similarity (high = same place/props).
Results: APP_DIR/../bench/continuity/<tag>.json + the page pictures.
"""
import json
import sys
import time
import urllib.request

import comfy
import db
import graphs
import media
import worker

BASE = "http://127.0.0.1:8189"
STORIES = [
    {"name": "bike", "chars": ["nori"], "seed": 1000,
     "lines": ["Nori rides her red cargo bike down a narrow market street at dusk",
               "smoke drifts from a food stall as Nori brakes hard",
               "close-up: Nori looks back over her shoulder, worried",
               'Nori pushes the bike into a small alley. "Almost home."'],
     "bible": "location: narrow market street with paper lanterns and food stalls, a small alley on the right; "
              "time and light: dusk, orange lantern light, long shadows; props: Nori's cargo bike with a wooden "
              "front box and a round headlight"},
    {"name": "cafe", "chars": ["nori", "bram"], "seed": 2000,
     "lines": ["Nori runs into the cafe out of the rain, holding a black umbrella",
               'Bram looks up from the counter. "You forgot to close it again."',
               "Nori shakes the water off her scarf, embarrassed",
               'Bram slides a hot cup to Nori across the counter. "On the house."'],
     "bible": "location: small wooden cafe, long counter, shelf of glass jars behind it, rainy window; "
              "time and light: rainy evening, warm lamp over the counter; props: a black folding umbrella with a "
              "curved wooden handle"},
    {"name": "platform", "chars": ["bram"], "seed": 3000,
     "lines": ["Bram waits alone on an empty train platform at dawn, holding an old lantern",
               "the train arrives, steam everywhere, Bram raises the lantern",
               "Bram sits down on the bench, tired",
               'Bram smiles and waves at the train window. "Safe travels."'],
     "bible": "location: small countryside train station, wooden bench, station clock, rails; time and light: "
              "dawn, cold mist, low sun from the left; props: Bram's brass oil lantern with a glass globe"},
]


def api(path, body=None):
    req = urllib.request.Request(BASE + path, json.dumps(body).encode() if body is not None else None,
                                 {"Content-Type": "application/json"} if body is not None else {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def score(ref_iid, iids):
    src = worker._upload(ref_iid)
    names = [worker._upload(i) for i in iids]
    cid = "bench"
    pid = comfy.submit(graphs.score(src, names), cid)
    _, ui = comfy.outputs(comfy.track(pid, cid))
    return json.loads(ui["scores"][0])["items"]


def main():
    tag = sys.argv[1]
    db.init()
    out = db.APP_DIR.parent / "bench" / "continuity"
    out.mkdir(parents=True, exist_ok=True)
    res = {"tag": tag, "stories": []}
    for st in STORIES:
        t = time.time()
        pg = api("/api/pages", {"lines": st["lines"], "chars": st["chars"], "bible": st["bible"], "seed": st["seed"]})
        pid = pg["id"]
        while pg["status"] == "working":
            time.sleep(3)
            pg = api(f"/api/pages/{pid}")
        sec = round(time.time() - t)
        ids = [p.get("image_id") for p in pg["panels"]]
        (out / f"{tag}_{st['name']}_page.png").write_bytes(media.read(pg["image_id"]))
        for k, i in enumerate(ids):
            if i:
                (out / f"{tag}_{st['name']}_p{k + 1}.png").write_bytes(media.read(i))
        for k, v in (pg.get("scene") or {}).items():
            if v.get("image_id"):
                (out / f"{tag}_{st['name']}_scene_{k}.png").write_bytes(media.read(v["image_id"]))
        rows = []
        chars = {s: db.one("SELECT * FROM characters WHERE slug=?", (s,)) for s in st["chars"]}
        for k, p in enumerate(pg["panels"]):
            if not p.get("image_id"):
                rows.append({"panel": k + 1, "missing": True})
                continue
            who = [pg["chars"][c] for c in p.get("cast", [])]
            r = {"panel": k + 1, "cast": who, "warn": p.get("warn"), "versions": len(p.get("versions") or [])}
            for s in who:
                it = score(chars[s]["source_image"], [p["image_id"]])[0]
                r[s] = {"face": it["face_sim"], "whole": it["whole_sim"]}
            rows.append(r)
        good = [i for i in ids if i]
        pair = []
        for a in range(len(good)):
            if a + 1 < len(good):
                its = score(good[a], good[a + 1:])
                pair += [it["whole_sim"] for it in its]
        res["stories"].append({"story": st["name"], "page": pid, "sec": sec, "panels": rows,
                               "pair_whole_mean": round(sum(pair) / len(pair), 4) if pair else None})
        print(json.dumps(res["stories"][-1]), flush=True)
    (out / f"{tag}.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
