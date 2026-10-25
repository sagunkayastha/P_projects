"""Local VLM (qwen3-vl-8b on judge-3060) yes/no checks for an A/B round from bench_ab.py.

  python3 tests/judge_ab.py <base url> <round dir> modify|sketch   -> <round dir>/judge.json + a table
Modify: change done, identity kept, layout kept (Small change only), manga quality.
Sketch: layout follows the sketch, content matches the words, manga quality.
"""
import json
import re
import sys
from pathlib import Path

from abset import MODIFY, SKETCH
from judge_continuity import ask, word

Q = ("Is this a clean black-and-white manga drawing with correct anatomy (no extra or missing limbs or fingers, "
     "no melted or broken face) and no stray text or letters? Answer YES or NO first.")


def yes(base, imgs, q):
    return word(ask(base, imgs, q + ("" if "Answer YES or NO" in q else " Answer YES or NO first.")), ["YES", "NO"]) == "YES"


def main():
    base, d, kind = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    cases = {c[0]: c for c in (MODIFY if kind == "modify" else SKETCH)}
    out = {}
    for p in sorted(d.glob("*.png")):
        m = re.match(r"([a-z]+)_(\d+)_([a-z0-9]+)(?:_([a-z]+))?\.png$", p.name)
        if not m or m.group(1) not in cases:
            continue
        name, seed, model, mode = m.groups()
        src = d / f"src_{name}.png"
        r = {}
        if kind == "modify":
            _, _, words, what = cases[name]
            r["change"] = yes(base, [src, p], f"Picture 1 is the original, picture 2 the edited version. In picture 2, is it "
                                              f"true that {what}?")
            r["identity"] = yes(base, [src, p], "Is the main character in picture 2 the same character as in picture 1 (same "
                                                f"face, age and gender)? Ignore this asked change: {words}.")
            if mode == "small":
                r["layout"] = yes(base, [src, p], f"Apart from the asked change ({words}), does picture 2 keep the framing, "
                                                  "camera angle and background of picture 1?")
        else:
            _, _, words, layout = cases[name]
            r["layout"] = yes(base, [src, p], f"Picture 1 is a rough sketch, picture 2 a finished drawing. Does picture 2 follow "
                                              f"the layout of the sketch: {layout}?")
            r["content"] = yes(base, [p], f"Does this picture show: {words}?")
        r["quality"] = yes(base, [p], Q)
        key = f"{model}" + (f"/{mode}" if mode else "")
        out.setdefault(key, {})[f"{name}_{seed}"] = r
        print(key, name, seed, json.dumps(r), flush=True)
    summ = {}
    for k, rs in out.items():
        ks = sorted({c for r in rs.values() for c in r})
        summ[k] = {c: f"{sum(r[c] for r in rs.values() if c in r)}/{sum(1 for r in rs.values() if c in r)}" for c in ks}
        allc = [x for r in rs.values() for x in r.values()]
        summ[k]["all_%"] = round(100 * sum(allc) / len(allc))
    (d / "judge.json").write_text(json.dumps({"summary": summ, "items": out}, indent=1))
    for k, s in summ.items():
        print(k, s)


if __name__ == "__main__":
    main()
