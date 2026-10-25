"""VLM checklist for a panel-bench round (qwen3-vl-8b, llama.cpp OpenAI API): per panel the line's yes/no checks
(angle, pose, place), how often each character appears, single picture or split, and a camera-angle label (variety).
Two-stage compositions (<v>_<k>_<name>_comp.png) are judged as variant "<v>:comp".

  python3 tests/judge_panels.py <base url> <round dir>       -> <round dir>/judge.json + a table
"""
import json
import re
import sys
from pathlib import Path

from judge_continuity import ask, word
from panelset import HARD, LOOKS, SET

BY = {s["name"]: s for s in SET + HARD}
ANGLES = ["EYE-LEVEL", "LOW-ANGLE", "HIGH-ANGLE", "TOP-DOWN", "OVER-THE-SHOULDER", "BACK-VIEW", "CLOSE-UP"]


def main():
    base, d = sys.argv[1], Path(sys.argv[2])
    out = {}
    for p in sorted(d.glob("*.png")):
        m = re.match(r"(.+?)_(\d+)_([a-z]+)(_comp)?\.png$", p.name)
        if not m or m.group(3) not in BY:
            continue
        v = m.group(1) + (":comp" if m.group(4) else "")
        item = BY[m.group(3)]
        r = {}
        for key, q in item["checks"].items():
            r[key] = word(ask(base, [p], q + " Answer YES or NO first."), ["YES", "NO"]) == "YES"
        r["single"] = word(ask(base, [p], "Is this picture ONE single scene, or is it split into several panels, "
                                "insets or a grid? Answer SINGLE or SPLIT first."), ["SINGLE", "SPLIT"]) == "SINGLE"
        r["angle_label"] = word(ask(base, [p], "Which camera angle is this picture? Answer with exactly one of: "
                                    + ", ".join(ANGLES) + "."), ANGLES)
        if not m.group(4):
            cnt = []
            for s in item["who"]:
                a = ask(base, [p], f"How many times does {LOOKS[s]} appear in this picture? Answer with a number first.")
                n = re.search(r"\d+", a)
                cnt.append(int(n.group(0)) if n else -1)
            r["count_ok"] = all(c == 1 for c in cnt)
            r["count"] = cnt
        out.setdefault(v, {})[item["name"]] = r
        print(v, item["name"], json.dumps(r), flush=True)
    summ = {}
    for v, rs in out.items():
        checks = [x for r in rs.values() for k, x in r.items() if k in ("angle", "pose", "place")]
        summ[v] = {"adherence_%": round(100 * sum(checks) / max(1, len(checks))),
                   "angle_%": round(100 * sum(r["angle"] for r in rs.values()) / len(rs)),
                   "pose_%": round(100 * sum(r["pose"] for r in rs.values()) / len(rs)),
                   "place_%": round(100 * sum(r["place"] for r in rs.values()) / len(rs)),
                   "people_ok": f"{sum(r.get('count_ok', True) for r in rs.values())}/{len(rs)}",
                   "split": sum(not r["single"] for r in rs.values()),
                   "distinct_angles": len({r["angle_label"] for r in rs.values()})}
    (d / "judge.json").write_text(json.dumps({"summary": summ, "panels": out}, indent=1))
    for v, s in summ.items():
        print(v, s)


if __name__ == "__main__":
    main()
