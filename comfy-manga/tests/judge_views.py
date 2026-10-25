"""VLM checklist for round p2 (B) pages (qwen3-vl-8b, llama.cpp OpenAI API): per panel the line's checks, people
count, single picture, camera-angle label; against the plate: same place? copied its camera? Within a page: panels
1-2, 1-3, 1-4, 2-3 show the same place?

  python3 -I tests/judge_views.py <base url> <views dir>     -> <views dir>/judge_views.json + a table
"""
import json
import re
import sys
from pathlib import Path

from judge_continuity import ask, word
from judge_panels import ANGLES
from panelset import LOOKS
from viewset import PLACES

SAME = ("Do these two pictures show the same place (same room or location, same furniture and buildings)? Ignore the "
        "people and the camera angle. Answer SAME or DIFFERENT first.")
COPY = ("Is the second picture drawn from almost the same camera position, direction and framing as the first (the "
        "background composition copied)? Answer YES or NO first.")


def main():
    base, d = sys.argv[1], Path(sys.argv[2])
    out, summ = {}, {}
    for page, place in PLACES.items():
        plate = d / f"{page}_plate.png"
        vs = sorted({re.match(rf"{page}_(.+?)_\d+_", p.name).group(1) for p in d.glob(f"{page}_*_[0-9]_*.png")})
        for v in vs:
            rs, files = {}, []
            for k, item in enumerate(place["panels"]):
                p = d / f"{page}_{v}_{k + 1}_{item['name']}.png"
                files.append(p)
                r = {key: word(ask(base, [p], q + " Answer YES or NO first."), ["YES", "NO"]) == "YES"
                     for key, q in item["checks"].items()}
                r["single"] = word(ask(base, [p], "Is this picture ONE single scene, or is it split into several "
                                       "panels, insets or a grid? Answer SINGLE or SPLIT first."), ["SINGLE", "SPLIT"]) == "SINGLE"
                r["angle_label"] = word(ask(base, [p], "Which camera angle is this picture? Answer with exactly one of: "
                                            + ", ".join(ANGLES) + "."), ANGLES)
                cnt = []
                for s in item["who"]:
                    a = ask(base, [p], f"How many times does {LOOKS[s]} appear in this picture? Answer with a number first.")
                    n = re.search(r"\d+", a)
                    cnt.append(int(n.group(0)) if n else -1)
                r["count_ok"], r["count"] = all(c == 1 for c in cnt), cnt
                r["plate_same"] = word(ask(base, [plate, p], SAME), ["SAME", "DIFFERENT"]) == "SAME"
                r["plate_copy"] = word(ask(base, [plate, p], COPY), ["YES", "NO"]) == "YES"
                rs[item["name"]] = r
                print(page, v, item["name"], json.dumps(r), flush=True)
            pairs = {f"{a + 1}-{b + 1}": word(ask(base, [files[a], files[b]], SAME), ["SAME", "DIFFERENT"]) == "SAME"
                     for a, b in ((0, 1), (0, 2), (0, 3), (1, 2))}
            out.setdefault(v, {})[page] = {"panels": rs, "pairs": pairs}
    for v, pg in out.items():
        rs = [r for x in pg.values() for r in x["panels"].values()]
        prs = [b for x in pg.values() for b in x["pairs"].values()]
        checks = [r[k] for r in rs for k in ("angle", "pose", "place")]
        summ[v] = {"adherence_%": round(100 * sum(checks) / len(checks)),
                   "angle_%": round(100 * sum(r["angle"] for r in rs) / len(rs)),
                   "place_part_%": round(100 * sum(r["place"] for r in rs) / len(rs)),
                   "same_place_as_plate": f"{sum(r['plate_same'] for r in rs)}/{len(rs)}",
                   "copies_plate_camera": f"{sum(r['plate_copy'] for r in rs)}/{len(rs)}",
                   "same_place_pairs": f"{sum(prs)}/{len(prs)}",
                   "people_ok": f"{sum(r['count_ok'] for r in rs)}/{len(rs)}",
                   "split": sum(not r["single"] for r in rs),
                   "distinct_angles": len({r["angle_label"] for r in rs})}
    (d / "judge_views.json").write_text(json.dumps({"summary": summ, "panels": out}, indent=1))
    for v, s in summ.items():
        print(v, s)


if __name__ == "__main__":
    main()
