"""Modify / Sketch A/B round through the app's chat API (each try shows up as a chat message on the test app).

  python3 tests/bench_ab.py <base url> <round dir> modify|sketch [sketch dir]
  -> <round dir>/<case>_<seed>_<model>[_<mode>].png, src_<case>.png, run.json (message ids, seconds per picture)
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

from abset import MODIFY, SEEDS, SKETCH, SRC


def call(base, path, body=None, raw=None, ctype="application/json"):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(base + path, data, {"Content-Type": ctype} if data is not None else {})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def get(base, path, out):
    with urllib.request.urlopen(base + path, timeout=120) as r:
        Path(out).write_bytes(r.read())


def main():
    base, d, kind = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    d.mkdir(parents=True, exist_ok=True)
    chat = call(base, "/api/chats", {})["id"]
    sends = []  # (file stem, body)
    if kind == "modify":
        for model in ("klein", "qwen"):  # one model at a time: no model switch per picture
            for name, src, words, _ in MODIFY:
                for mode in ("small", "new"):
                    for seed in SEEDS:
                        sends.append((f"{name}_{seed}_{model}_{mode}",
                                      {"text": words, "sketch": SRC[src], "model": model, "edit": mode, "seed": seed}))
        for name, src, *_ in MODIFY:
            get(base, f"/api/images/{SRC[src]}", d / f"src_{name}.png")
    else:
        sk = Path(sys.argv[4])
        ids = {}
        for name, f, *_ in SKETCH:
            ids[name] = call(base, "/api/sketch", raw=(sk / f).read_bytes(), ctype="image/jpeg")["id"]
            get(base, f"/api/images/{ids[name]}", d / f"src_{name}.png")
        for model in ("klein", "qwen", "anima"):
            for name, _, words, _ in SKETCH:
                for seed in SEEDS:
                    sends.append((f"{name}_{seed}_{model}", {"text": words, "sketch": ids[name], "model": model, "seed": seed}))
    run = {"chat": chat, "items": {}}
    for stem, body in sends:
        m = call(base, f"/api/chats/{chat}/messages", {**body, "ckey": f"ab-{kind}-{stem}-{time.time():.0f}"})
        run["items"][stem] = {"msg": m["id"], "job": m["job_id"]}
    print(f"chat {chat}: {len(sends)} sent", flush=True)
    left = dict(run["items"])
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
        print(f"{len(sends) - len(left)}/{len(sends)} done", flush=True)
    (d / "run.json").write_text(json.dumps(run, indent=1))


if __name__ == "__main__":
    main()
