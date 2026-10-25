"""Panel prompts for a page: 4 plain lines -> 4 image prompts.

Uses the local LLM (llama.cpp router on the host, :11434) only when a model is already loaded there
(never starts or loads one: it would take the GPU from ComfyUI). Otherwise a fixed template. No cloud."""
import json
import os
import re

import gpu
import graphs
import layout
import refs

FRAMING = ["Wide establishing shot that shows the place", "Medium shot", "Close-up on the face and hands",
           "Medium-wide shot"]


def cast_text(chars):
    """chars: list of {"name", "n" (reference pictures, in order), "traits"}."""
    parts, k = [], 1
    for c in chars:
        n = c.get("n", 2)
        imgs = [f"image {i}" for i in range(k, k + n)]
        k += n
        say = ", ".join(imgs[:-1]) + f" and {imgs[-1]}" if n > 1 else imgs[0]
        t = f"{c['name']} is the person shown in {say}"
        if c.get("sheet"):
            t += " (a reference sheet for the face, hair and clothes only)"
        if c.get("traits"):
            t += f" ({c['name']}: {c['traits'].strip().rstrip('.')})"
        parts.append(t)
    return "; ".join(parts) + "." if parts else ""


def template(scene, chars, framing, bible=""):
    keep = (("Keep each character's face, hair and clothes exactly as in the reference pictures. " if refs.CONT else
             "Keep each character's face, hair, body and outfit exactly as in the reference pictures. ") if chars else "")
    shot = f"{framing}. " if framing else ""
    n = refs.per_char(len(chars))
    chars = [{**c, "n": c.get("n", n), "sheet": c.get("sheet", refs.CONT)} for c in chars]
    scene = scene.strip().rstrip(".") + "."
    same = f"Same in every panel of this page: {bible.strip().rstrip('.')}. " if bible else ""
    return (f"Manga panel. {shot}{cast_text(chars)} Scene: {scene} {same}{keep}{graphs.STYLE} "
            "The drawing fills the whole picture edge to edge. No text, no letters, no speech bubbles, no panel borders, "
            "no white bars.").replace("  ", " ")


def _loaded_model():
    data = gpu.models()
    for m in (data or {}).get("data", []):
        st = m.get("status")
        if (st.get("value") if isinstance(st, dict) else st) == "loaded":
            return m.get("id")
    return None


def _llm(model, lines, chars):
    names = ", ".join(c["name"] for c in chars) or "no named characters"
    ask = ("You write image prompts for 4 panels of one black-and-white manga page. Characters: " + names + ".\n"
           "For each panel line below, write ONE sentence describing only what the camera sees: shot type "
           "(vary them: wide, medium, close-up, over-the-shoulder), who is where, pose, action, facial expression, "
           "setting. Use the character names. No dialogue, no text, no style words. If a line already says the shot "
           "(close-up, zoom, focus on, from behind...), keep that shot.\n"
           "Also return each line with only its spelling mistakes fixed (same words otherwise, keep \"quotes\").\n"
           + "\n".join(f"{i + 1}. {s}" for i, s in enumerate(lines)) +
           '\nAnswer with JSON only: {"panels": ["...", "...", "...", "..."], "fixed": ["...", "...", "...", "..."]}')
    body = {"model": model, "messages": [{"role": "user", "content": ask}], "temperature": 0.4, "max_tokens": 1200,
            "chat_template_kwargs": {"enable_thinking": False}}
    text = gpu.chat(body)["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.S)
    d = json.loads(m.group(0))
    panels = d["panels"]
    if len(panels) != 4 or not all(isinstance(p, str) and p.strip() for p in panels):
        raise ValueError("bad LLM answer")
    fixed = d.get("fixed") if isinstance(d.get("fixed"), list) and len(d.get("fixed")) == 4 else [None] * 4
    fixed = [f.strip() if isinstance(f, str) and f.strip() and f.strip() != ln.strip() else None
             for f, ln in zip(fixed, lines)]
    return [p.strip() for p in panels], fixed


def who(scene, chars):
    """Indexes of the characters a panel line names (all of them when it names none)."""
    named = [i for i, c in enumerate(chars) if re.search(r"\b" + re.escape(c["name"].lower()) + r"\b", scene.lower())]
    return named or list(range(len(chars)))


SHOT_WORDS = re.compile(r"\b(close[- ]?up|wide|establishing|medium|full[- ]body|over[- ]the[- ]shoulder|from (below|above)|"
                        r"low[- ]angle|high[- ]angle|bird'?s[- ]eye|worm'?s[- ]eye|profile|side view|from behind(?! (?:the|a|an|his|her|their) )|focus(?:es|ed)? on|"
                        r"zoom(?:s|ed)?(?: in| out| into)?|pan(?:s)? (?:to|across|over)|drifts?|overhead|extreme|"
                        r"shot|view of|seen from|camera)\b", re.I)


def framing(scene, idx):
    """The default shot for a panel, unless the line already says one ("close-up: ..."). Continuity mode: none
    at all; the shot comes from the story line, not from the panel's place on the page."""
    if refs.CONT:
        return None
    return None if SHOT_WORDS.search(scene) else FRAMING[idx % len(FRAMING)]


def panel(line, chars, idx, cast=None, bible=""):
    """One panel again (after the user edits its line or its characters): (prompt, quotes, cast).
    cast: indexes into chars chosen by the user; None = the characters the line names."""
    scene, quotes = layout.split_line(line)
    if cast is None:
        cast = who(scene, chars)
    return template(scene, [chars[i] for i in cast], framing(scene, idx), bible), quotes, cast


def write(lines, chars, bible=""):
    """Returns (prompts, quotes, cast per panel (indexes into chars), writer-name, spelling-fixed lines or None).
    Each panel gets only the characters its line names, so klein does not draw someone twice."""
    split = [layout.split_line(ln) for ln in lines]
    scenes = [s for s, _ in split]
    quotes = [q for _, q in split]
    casts = [who(s, chars) for s in scenes]
    model = _loaded_model()
    if model:
        try:
            shots, fixed = _llm(model, lines, chars)
            for k, f in enumerate(fixed):  # a fixed line (typos) also fixes its speech bubbles and names
                if f:
                    sc, quotes[k] = layout.split_line(f)
                    casts[k] = who(sc, chars)
            return ([template(s, [chars[i] for i in casts[k]], None, bible) for k, s in enumerate(shots)], quotes, casts,
                    f"local LLM ({model})", fixed)
        except Exception:
            pass
    return ([template(s, [chars[i] for i in casts[k]], framing(s, k), bible) for k, s in enumerate(scenes)], quotes, casts,
            "template", [None] * 4)
