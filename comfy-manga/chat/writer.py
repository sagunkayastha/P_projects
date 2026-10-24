"""Panel prompts for a page: 4 plain lines -> 4 image prompts.

Uses the local LLM (llama.cpp router on the host, :11434) only when a model is already loaded there
(never starts or loads one: it would take the GPU from ComfyUI). Otherwise a fixed template. No cloud."""
import json
import os
import re
import urllib.request

import graphs
import layout

LLM = os.environ.get("LLM_URL", "http://host.docker.internal:11434")
FRAMING = ["Wide establishing shot that shows the place", "Medium shot", "Close-up on the face and hands",
           "Medium-wide shot"]


def cast_text(chars):
    """chars: list of {"name"}; each character has 2 reference pictures, in order."""
    parts = []
    for i, c in enumerate(chars):
        a, b = 2 * i + 1, 2 * i + 2
        parts.append(f"{c['name']} is the person shown in image {a} and image {b}")
    return "; ".join(parts) + "." if parts else ""


def template(scene, chars, framing):
    keep = ("Keep each character's face, hair, body and outfit exactly as in the reference pictures. "
            if chars else "")
    shot = f"{framing}. " if framing else ""
    scene = scene.strip().rstrip(".") + "."
    return (f"Manga panel. {shot}{cast_text(chars)} Scene: {scene} {keep}{graphs.STYLE} "
            "No text, no letters, no speech bubbles, no panel borders.").replace("  ", " ")


def _loaded_model():
    try:
        with urllib.request.urlopen(LLM + "/models", timeout=2) as r:
            data = json.load(r)
    except Exception:
        return None
    for m in data.get("data", []):
        st = m.get("status")
        if (st.get("value") if isinstance(st, dict) else st) == "loaded":
            return m.get("id")
    return None


def _llm(model, scenes, chars):
    names = ", ".join(c["name"] for c in chars) or "no named characters"
    ask = ("You write image prompts for 4 panels of one black-and-white manga page. Characters: " + names + ".\n"
           "For each panel line below, write ONE sentence describing only what the camera sees: shot type "
           "(vary them: wide, medium, close-up, over-the-shoulder), who is where, pose, action, facial expression, "
           "setting. Use the character names. No dialogue, no text, no style words.\n"
           + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(scenes)) +
           '\nAnswer with JSON only: {"panels": ["...", "...", "...", "..."]}')
    body = {"model": model, "messages": [{"role": "user", "content": ask}], "temperature": 0.4, "max_tokens": 600}
    req = urllib.request.Request(LLM + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        text = json.load(r)["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    panels = json.loads(m.group(0))["panels"]
    if len(panels) != 4 or not all(isinstance(p, str) and p.strip() for p in panels):
        raise ValueError("bad LLM answer")
    return [p.strip() for p in panels]


def who(scene, chars):
    """Indexes of the characters a panel line names (all of them when it names none)."""
    named = [i for i, c in enumerate(chars) if re.search(r"\b" + re.escape(c["name"].lower()) + r"\b", scene.lower())]
    return named or list(range(len(chars)))


def write(lines, chars):
    """Returns (prompts, quotes, cast per panel (indexes into chars), writer-name).
    Each panel gets only the characters its line names, so klein does not draw someone twice."""
    split = [layout.split_line(ln) for ln in lines]
    scenes = [s for s, _ in split]
    quotes = [q for _, q in split]
    casts = [who(s, chars) for s in scenes]
    model = _loaded_model()
    if model:
        try:
            shots = _llm(model, scenes, chars)
            return ([template(s, [chars[i] for i in casts[k]], None) for k, s in enumerate(shots)], quotes, casts,
                    f"local LLM ({model})")
        except Exception:
            pass
    return ([template(s, [chars[i] for i in casts[k]], FRAMING[k]) for k, s in enumerate(scenes)], quotes, casts,
            "template")
