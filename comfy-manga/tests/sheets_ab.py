"""Blind contact sheets for an A/B round: fixed columns (same model = same letter in every row); the model->letter
key goes to <round dir>/key.json only. Also writes prompts.json (row ids, words, checks) for Codex / Gemini.

  python3 tests/sheets_ab.py <round dir> modify|sketch      (run inside an image with Pillow)
"""
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from abset import MODIFY, SEEDS, SKETCH

d, kind = Path(sys.argv[1]), sys.argv[2]
models = ["klein", "qwen"] if kind == "modify" else ["klein", "qwen", "anima"]
rng = random.Random(20261026 if kind == "modify" else 20261027)
letters = "ABC"[:len(models)]
order = models[:]
rng.shuffle(order)
key = dict(zip(letters, order))  # letter -> model
(d / "key.json").write_text(json.dumps(key, indent=1))
rows = []  # (row id, case, seed, mode)
if kind == "modify":
    for mode in ("small", "new"):
        for name, src, words, what in MODIFY:
            for seed in SEEDS:
                rows.append((f"{name}-{mode}-{seed}", name, seed, mode, {"words": words, "mode": "Small change" if mode == "small" else "New picture", "expected": what}))
else:
    for name, f, words, layout in SKETCH:
        for seed in SEEDS:
            rows.append((f"{name}-{seed}", name, seed, None, {"words": words, "layout": layout}))
(d / "prompts.json").write_text(json.dumps({"kind": kind, "columns": letters, "rows": {r[0]: r[4] for r in rows}}, indent=1))
tw, th, lab = 240, 340, 210
per = 8
sheets = []
for i in range(0, len(rows), per):
    chunk = rows[i:i + per]
    c = Image.new("RGB", (lab + tw * (1 + len(letters)), 26 + len(chunk) * (th + 6)), "white")
    g = ImageDraw.Draw(c)
    for k, t in enumerate(["source" if kind == "modify" else "sketch"] + list(letters)):
        g.text((lab + k * tw + 6, 6), t, fill="black")
    for r, (rid, name, seed, mode, info) in enumerate(chunk):
        y = 26 + r * (th + 6)
        g.text((4, y + 6), rid, fill="black")
        txt = info["words"]
        for j in range(0, len(txt), 30):
            g.text((4, y + 24 + j // 30 * 14), txt[j:j + 30], fill="black")
        files = [d / f"src_{name}.png"] + [d / (f"{name}_{seed}_{key[L]}" + (f"_{mode}" if mode else "") + ".png") for L in letters]
        for k, f in enumerate(files):
            if not f.exists():
                g.text((lab + k * tw + 6, y + 40), "missing", fill="red")
                continue
            im = Image.open(f).convert("RGB")
            im.thumbnail((tw - 6, th))
            c.paste(im, (lab + k * tw + (tw - im.width) // 2, y + (th - im.height) // 2))
    out = d / f"sheet_{i // per + 1}.png"
    c.save(out)
    sheets.append(out.name)
print(key, sheets)
