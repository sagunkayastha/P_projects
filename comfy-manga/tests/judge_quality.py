"""VLM checks for a quality round (qwen3-vl-8b, llama.cpp OpenAI API): per panel, how often each character
appears (2+ = doubled), one scene or split/grid, stray text. Writes <round dir>/judge.json and prints per variant.

  python3 tests/judge_quality.py <base url> <round dir>
"""
import json
import re
import sys
from pathlib import Path

from judge_continuity import ask, word

WHO = {"wide": ["the young woman with glasses"], "closeup": ["the young woman with glasses"],
       "action": ["the young woman with glasses"],
       "two": ["the young woman with glasses", "the old bearded man"], "interior": ["the old bearded man"],
       "lowangle": ["the old bearded man"]}


def main():
    base, d = sys.argv[1], Path(sys.argv[2])
    out = {}
    for p in sorted(d.glob("*_[1-6]_*.png")):
        v, k, name = re.match(r"(.+)_(\d)_(\w+)\.png", p.name).groups()
        r = {"single": word(ask(base, [p], "Is this picture ONE single scene, or is it split into several panels, "
                                "insets or a grid? Answer SINGLE or SPLIT first."), ["SINGLE", "SPLIT"]),
             "text": word(ask(base, [p], "Are there any written letters, words or speech bubbles in this picture? "
                              "Answer YES or NO first."), ["YES", "NO"]), "count": []}
        for who in WHO[name]:
            a = ask(base, [p], f"How many times does {who} appear in this picture? Answer with a number first.")
            m = re.search(r"\d+", a)
            r["count"].append(int(m.group(0)) if m else -1)
        out.setdefault(v, {})[name] = r
        print(v, name, json.dumps(r), flush=True)
    summ = {v: {"doubled": sum(any(c >= 2 for c in r["count"]) for r in rs.values()),
                "missing": sum(any(c == 0 for c in r["count"]) for r in rs.values()),
                "split": sum(r["single"] == "SPLIT" for r in rs.values()),
                "text": sum(r["text"] == "YES" for r in rs.values())} for v, rs in out.items()}
    (d / "judge.json").write_text(json.dumps({"summary": summ, "panels": out}, indent=1))
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
