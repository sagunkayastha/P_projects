"""Director model bench: 3 neutral test stories, each = first shot list + 2 edit turns, against an OpenAI-style
endpoint (llama.cpp). Uses chat/director-skills.md as the system prompt (same as the app).

  python3 tests/bench_director.py <base url> <model id> <out.json>
Prints times and simple quality checks; writes every answer to out.json for side-by-side reading.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = (HERE.parent / "chat" / "director-skills.md").read_text()
CHARS = [("Nori", "young woman, short black bob with straight bangs, round glasses, long striped scarf, "
                  "loose knitted cardigan, dark pleated skirt, ankle boots"),
         ("Bram", "old man, long white beard and moustache, flat cap, dark buttoned vest over a white shirt, "
                  "dark trousers, polished shoes")]
STORIES = [
    {"lines": ["Nori runs into the cafe out of the rain",
               'Bram looks up from the counter. "You forgot your umbrella again."',
               "she shakes the water off her scarf, embarrassed",
               'close-up: Bram slides a hot cup to her. "On the house."'],
     "notes": "cosy, late autumn evening, small wooden cafe, warm lamp light",
     "edits": ["make panel 2 a low angle", "add heavy rain outside the window in every panel"]},
    {"lines": ["Bram waits alone at an empty train platform at dawn",
               "the train arrives, steam everywhere",
               'Nori steps off with a big suitcase. "Grandpa!"',
               "they hug, his cap falls off"],
     "notes": "quiet countryside station, cold morning mist, emotional reunion",
     "edits": ["panel 1 should be an extreme wide shot from above", "Nori's suitcase is red-brown leather with a "
               "yellow luggage tag; keep it the same in every panel"]},
    {"lines": ["Nori reads a book under a tree in the park",
               "a gust of wind blows the pages",
               'a letter falls out of the book. "What is this?"',
               "zoom into the letter in her hand, her eyes go wide"],
     "notes": "sunny spring afternoon, cherry blossoms, mystery hook at the end",
     "edits": ["the man in the background of panel 1 should be Bram, sitting on a bench", "make the last panel more "
               "dramatic"]},
]


def chat(base, model, msgs):
    body = {"model": model, "messages": msgs, "temperature": 0.6, "max_tokens": 6000, "stream": False,
            "chat_template_kwargs": {"enable_thinking": False}}
    req = urllib.request.Request(base + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=1200) as r:
        d = json.load(r)
    text = re.sub(r"<think>.*?</think>", "", d["choices"][0]["message"]["content"], flags=re.S).strip()
    return text, time.time() - t, d.get("usage", {}), d.get("timings", {})


def parse(text):
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else text[text.find("{"):text.rfind("}") + 1]
    try:
        return json.loads(raw)
    except ValueError:
        return None


def checks(sl, n):
    if not sl:
        return {"json": False}
    ps = sl.get("panels") or []
    names = {c for p in ps for c in (p.get("characters") or [])}
    return {"json": True, "panels_ok": len(ps) == n, "names_exact": names <= {"Nori", "Bram"},
            "bible": all((sl.get("bible") or {}).get(k) for k in ("location", "time_light", "wardrobe"))}


def main():
    base, model, out = sys.argv[1], sys.argv[2], sys.argv[3]
    system = SKILLS + "\n\n## Saved characters (use these exact names)\n" + "\n".join(f"- {n}: {t}" for n, t in CHARS)
    res = []
    for si, st in enumerate(STORIES):
        user = ("Panel lines:\n" + "\n".join(f"{i + 1}. {ln}" for i, ln in enumerate(st["lines"])) +
                f"\nNotes: {st['notes']}\nCharacters in this page: Nori, Bram")
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for turn, ask in enumerate([None] + st["edits"]):
            if ask:
                msgs.append({"role": "user", "content": ask})
            text, sec, usage, tim = chat(base, model, msgs)
            msgs.append({"role": "assistant", "content": text})
            sl = parse(text)
            c = checks(sl, len(st["lines"]))
            row = {"story": si, "turn": turn, "ask": ask, "sec": round(sec, 1),
                   "tok": usage.get("completion_tokens"), "tps": round(tim.get("predicted_per_second", 0), 1),
                   "checks": c, "answer": text}
            res.append(row)
            print(f"story {si} turn {turn}: {sec:.1f}s {row['tok']} tok {row['tps']} tok/s {c}", flush=True)
    Path(out).write_text(json.dumps({"model": model, "base": base, "rows": res}, indent=1))


if __name__ == "__main__":
    main()
