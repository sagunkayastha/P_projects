"""Round p2 (B): several empty views of the place, each panel gets the view its camera faces, vs today's one wide
plate. Two 4-panel pages (viewset.PLACES), the shipped panel prompt, same seeds. Runs inside the test app container:

  docker cp tests/{panelset,viewset,bench_quality,bench_panels,bench_views}.py manga-app-test:/app/
  docker exec manga-app-test python bench_views.py <round> <variant,...>
Variants
  plate        the app today: one Anima wide plate in every panel ("only a reference for the place")
  views_anima  4 views, each drawn by Anima from the words (view 1 = the plate); panel gets its view
  views_klein  the plate, then klein turns the camera of the plate to each other view (same room); panel gets its view
Output: APP_DIR/../bench/panels/<round>/views/<page>_<variant>_<k>_<name>.png, <page>_view_<src>_<key>.png,
contact_views.png, prompts_views.json
"""
import json
import sys
import time

import db
import graphs
import pages
import writer
from bench_panels import free, klein_r, run, sheet
from bench_quality import chars_of, ref_names, up
from viewset import PLACES, pick_view

SEED = 9500
VIEW_TEXT = ("Image {n} is the background this camera faces ({desc}): keep that place, its furniture, walls and light; "
             "the camera angle and framing come from the scene, not from image {n}.")


def view_prompt(bible, desc):
    b = pages.parse_bible(bible)
    return (f"Background drawing of {b['location']}, the view {desc}. {b.get('time_light', '')}. Empty scene with no "
            f"people, nobody, detailed manga background art.").replace(" . ", " ")


def turn_prompt(desc):
    return (f"Image 1 shows a place. Draw the same place, empty, with the camera turned to face {desc}: the same "
            f"building, furniture, walls, materials, light and time of day, seen from a new direction; not a copy of "
            f"image 1. No people, nobody. Detailed manga background art. {graphs.STYLE}")


def views(out, page, src, place):
    """The view pictures for one page (view 0 = the wide plate)."""
    pf = out / f"{page}_plate.png"
    if not pf.exists():
        w, h = graphs.SHAPES["wide"]
        pf.write_bytes(run(graphs.anima_bw(pages.scene_prompts(place["bible"])["plate"], w, h, SEED)))
    res, w, h = [pf.read_bytes()], *graphs.SHAPES["wide"]
    for i, (key, desc, _) in enumerate(place["views"][1:], 1):
        f = out / f"{page}_view_{src}_{key}.png"
        if not f.exists():
            if src == "anima":
                f.write_bytes(run(graphs.anima_bw(view_prompt(place["bible"], desc), w, h, SEED + i)))
            else:
                f.write_bytes(run(klein_r(turn_prompt(desc), [up(res[0])], w, h, SEED + i)))
            print(page, "view", src, key, flush=True)
        res.append(f.read_bytes())
    return res


def main():
    rnd, variants = sys.argv[1], sys.argv[2].split(",")
    db.init()
    out = db.APP_DIR.parent / "bench" / "panels" / rnd / "views"
    out.mkdir(parents=True, exist_ok=True)
    # Anima pictures first (one model family at a time), then klein
    for page, place in PLACES.items():
        views(out, page, "anima", place if "views_anima" in variants else {**place, "views": place["views"][:1]})
    free()
    rows, labels, prompts, times = [], [], {}, {}
    for page, place in PLACES.items():
        vs = {"plate": None, "views_anima": views(out, page, "anima", place) if "views_anima" in variants else None,
              "views_klein": views(out, page, "klein", place) if "views_klein" in variants else None}
        plate = (out / f"{page}_plate.png").read_bytes()
        for v in [v for v in vs if vs[v] and v in variants]:  # the view each panel gets, above its panels
            rows.append([plate] + [vs[v][pick_view(it["line"], place["views"])] for it in place["panels"]])
            labels.append(f"{page}\n{v}\n(given)")
        for v in variants:
            pics, t0 = [], time.time()
            for k, item in enumerate(place["panels"]):
                f = out / f"{page}_{v}_{k + 1}_{item['name']}.png"
                if f.exists():
                    pics.append(f.read_bytes())
                    continue
                chs = chars_of(item["who"])
                w, h = graphs.SHAPES[item["shape"]]
                names, _ = ref_names(chs, item["line"], "sheet")
                pr = writer.template(item["line"], [{"name": c["name"], "n": 1, "sheet": True} for c in chs], None,
                                     place["bible"])
                st = pages.shot_text(item["line"])
                scene = "" if st and st in pr else item["line"]
                if v == "plate":
                    names.append(up((out / f"{page}_plate.png").read_bytes()))
                    ex = pages._extras(len(names), None, None, [c["name"] for c in chs], scene)
                else:
                    i = pick_view(item["line"], place["views"])
                    names.append(up(vs[v][i]))
                    ex = (VIEW_TEXT.format(n=len(names), desc=place["views"][i][1]) + " " +
                          pages._extras(None, None, None, [c["name"] for c in chs], scene))
                    prompts[f"{page}/{v}/{item['name']}/view"] = place["views"][i][0]
                pr = pr.replace(graphs.STYLE, ex + " " + graphs.STYLE, 1)
                data = run(klein_r(pr, names, w, h, SEED + 10 + k))
                f.write_bytes(data)
                pics.append(data)
                prompts[f"{page}/{v}/{item['name']}"] = pr
                print(page, v, item["name"], flush=True)
            times[f"{page}/{v}"] = round((time.time() - t0) / 4, 1)
            rows.append([plate] + pics)
            labels.append(f"{page}\n{v}")
    heads = ["plate", "panel 1", "panel 2", "panel 3", "panel 4"]
    sheet(rows, labels, out / "contact_views.png", heads)
    (out / "prompts_views.json").write_text(json.dumps({"places": PLACES, "prompts": prompts, "sec_per_panel": times},
                                                       indent=1))
    print(json.dumps(times))


if __name__ == "__main__":
    main()
