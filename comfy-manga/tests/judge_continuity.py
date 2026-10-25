"""VLM judge for the continuity bench pages (qwen3-vl-8b in a llama.cpp container, OpenAI API).

  python3 -I tests/judge_continuity.py <base url> <bench dir> <tag> [<tag> ...]
Per story: is it the same place / prop in panels 1-4 (pairs 1-2, 1-3, 1-4), per panel: one single scene or a
split / grid, and how often each character appears. Prints a table and writes <dir>/judge.json.
"""
import base64
import json
import re
import sys
import urllib.request
from pathlib import Path

PROP = {"bike": "the bicycle", "cafe": "the umbrella", "platform": "the lantern"}
PLACE = {"bike": "the market street", "cafe": "the cafe", "platform": "the train platform"}
WHO = {"bike": ["the young woman with glasses"], "cafe": ["the young woman with glasses", "the old bearded man"],
       "platform": ["the old bearded man"]}


def img(p):
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(Path(p).read_bytes()).decode()}}


def ask(base, images, q):
    body = {"model": "qwen3-vl-8b", "temperature": 0, "max_tokens": 3000,
            "messages": [{"role": "user", "content": [*map(img, images), {"type": "text", "text": q}]}]}
    req = urllib.request.Request(base + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        t = json.load(r)["choices"][0]["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", t, flags=re.S).strip()


def word(t, opts):
    u = t.upper()
    hits = [(u.find(o), o) for o in opts if o in u]
    return min(hits)[1] if hits else "?"


def main():
    base, d, tags = sys.argv[1], Path(sys.argv[2]), sys.argv[3:]
    out = {}
    for tag in tags:
        for st in ("bike", "cafe", "platform"):
            ps = [d / f"{tag}_{st}_p{k}.png" for k in range(1, 5)]
            r = {"same_prop": [], "same_place": [], "single": [], "count": []}
            for k in (1, 2, 3):
                r["same_prop"].append(word(ask(base, [ps[0], ps[k]], f"Look at {PROP[st]} in both pictures. Is it the same "
                                                  f"object (same type, shape and details)? If it is missing in one picture say MISSING. "
                                                  f"Answer SAME, DIFFERENT or MISSING first."), ["SAME", "DIFFERENT", "MISSING"]))
                r["same_place"].append(word(ask(base, [ps[0], ps[k]], f"Do both pictures show the same place ({PLACE[st]}), with "
                                                   f"the same buildings/furniture and the same time of day? Answer SAME or DIFFERENT first."),
                                            ["SAME", "DIFFERENT"]))
            for p in ps:
                r["single"].append(word(ask(base, [p], "Is this picture ONE single scene, or is it split into several panels, "
                                            "insets or a grid? Answer SINGLE or SPLIT first."), ["SINGLE", "SPLIT"]))
                n = []
                for who in WHO[st]:
                    a = ask(base, [p], f"How many times does {who} appear in this picture? Answer with a number first.")
                    m = re.search(r"\d+", a)
                    n.append(int(m.group(0)) if m else -1)
                r["count"].append(n)
            out[f"{tag}/{st}"] = r
            print(tag, st, json.dumps(r), flush=True)
    (d / "judge.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
