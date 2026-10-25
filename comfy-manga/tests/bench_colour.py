"""Colour A/B round through the chat API: 6 cases x 2 seeds x klein / Qwen-Edit / Anima.

  python3 tests/bench_colour.py <base url> <round dir> <sketch dir>
  -> <case>_<seed>_<model>.png, src_<case>.png, run.json
"""
import json
import sys
import time
from pathlib import Path

from bench_ab import call, get

SEEDS = (3101, 4202)
MODELS = ("klein", "qwen", "anima")
# name, words, chars, look, source ("colsrc" = made first in colour, an image id, or a sketch file), edit mode
CASES = [
    ("cover1", "Rin standing in a city street at dusk, wind in her hair", ["rin"], "cover", None, None),
    ("cover2", "Rin and Kai back to back, ready for an adventure", ["rin", "kai"], "cover", None, None),
    ("chapter", "Rin and Kai walking across a rooftop at night above the city lights", ["rin", "kai"], "chapter", None, None),
    ("modcol", "give her a red scarf and make the sky a warm sunset", [], "colour", "colsrc", "small"),
    ("bw2col", "the same picture in full colour", [], "colour", 100, "small"),
    ("sketch", "Rin standing on a street", ["rin"], "cover", "s1_stand.jpg", None),
]


def wait(base, chat, items, d):
    left = dict(items)
    while left:
        time.sleep(10)
        msgs = {m["id"]: m for m in call(base, f"/api/chats/{chat}")["messages"]}
        for stem, it in list(left.items()):
            j = msgs[it["msg"]]["job"]
            if j["status"] in ("done", "failed", "cancelled"):
                it.update(status=j["status"], image=j.get("image_id"), error=j.get("error"),
                          secs=round((j.get("finished") or 0) - (j.get("started") or 0), 1))
                if j.get("image_id"):
                    get(base, f"/api/images/{j['image_id']}", d / f"{stem}.png")
                del left[stem]
        print(f"{len(items) - len(left)}/{len(items)} done", flush=True)


def main():
    base, d, sk = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    d.mkdir(parents=True, exist_ok=True)
    chat = call(base, "/api/chats", {})["id"]
    # the colour source for "modify a colour picture": klein, colour, Rin at a cafe
    m = call(base, f"/api/chats/{chat}/messages", {"text": "Rin sitting at a cafe table by the window, smiling",
             "chars": ["rin"], "model": "klein", "style": "colour", "seed": 999, "ckey": f"col-src-{time.time():.0f}"})
    pre = {"colsrc": {"msg": m["id"]}}
    wait(base, chat, pre, d)
    srcs = {"colsrc": pre["colsrc"]["image"]}
    for name, words, chars, look, src, edit in CASES:
        if isinstance(src, str) and src.endswith(".jpg"):
            srcs[name] = call(base, "/api/sketch", raw=(sk / src).read_bytes(), ctype="image/jpeg")["id"]
        elif src == "colsrc":
            srcs[name] = srcs["colsrc"]
        elif src:
            srcs[name] = src
        if name in srcs:
            get(base, f"/api/images/{srcs[name]}", d / f"src_{name}.png")
    items = {}
    for model in MODELS:
        for name, words, chars, look, src, edit in CASES:
            for seed in SEEDS:
                body = {"text": words, "chars": chars, "model": model, "style": look, "seed": seed}
                if name in srcs:
                    body["sketch"] = srcs[name]
                if edit:
                    body["edit"] = edit
                m = call(base, f"/api/chats/{chat}/messages", {**body, "ckey": f"col-{name}-{seed}-{model}-{time.time():.0f}"})
                items[f"{name}_{seed}_{model}"] = {"msg": m["id"]}
    print(f"chat {chat}: {len(items)} sent", flush=True)
    wait(base, chat, items, d)
    (d / "run.json").write_text(json.dumps({"chat": chat, "srcs": srcs, "items": items}, indent=1))


if __name__ == "__main__":
    main()
