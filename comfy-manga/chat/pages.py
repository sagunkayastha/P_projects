"""A page's jobs: the scene pictures (place plate, prop sheet) and the 4 panels, and in which order they run.

Continuity mode (refs.CONT, default on):
- a page with a scene bible first draws a place plate (wide, nobody in it) and, when the bible lists props,
  a prop sheet (Anima, ~15 s each); every panel then gets them as two separate reference pictures
  (stacked into one picture, klein drew split panels: test 2026-10-24, tests/exp_refs.py);
- a page without scene pictures draws its panels in order and panel k gets panel k-1 as a reference;
- every panel prompt asks for one single picture (refs made klein draw comic grids / split screens);
- each character is one reference sheet (upper-body crops, sheets.py) so klein does not copy the pose,
  and the prompt says so;
- no default shot per panel slot: the shot comes from the line (or the Director).
Off: the old way (4 panels at once, source + best view per character, full pictures).
"""
import re

import db
import graphs
import layout
import refs
import worker

KEYS = {"location": "location", "place": "location", "time and light": "time_light", "time_light": "time_light",
        "time": "time_light", "light": "time_light", "props": "props", "wardrobe": "wardrobe", "clothes": "wardrobe",
        "mood": "mood"}


class PanelError(Exception):
    """A panel cannot be drawn as asked (e.g. one of its characters is gone)."""


def parse_bible(text):
    """'location: ...; time and light: ...; props: ...' (Director) or free text (= the place)."""
    out = {}
    for part in re.split(r";\s*(?=[a-z_ ]{3,20}:)", text or ""):
        k, sep, v = part.partition(":")
        key = KEYS.get(k.strip().lower())
        if sep and key and v.strip():
            out[key] = (out.get(key, "") + " " + v.strip()).strip()
    if not out and (text or "").strip():
        out["location"] = text.strip()
    return out


def scene_prompts(bible):
    b = parse_bible(bible)
    out = {}
    if b.get("location") or b.get("time_light"):
        out["plate"] = (f"Wide establishing background drawing of {b.get('location', 'the place')}. "
                        f"{b.get('time_light', '')}. {b.get('mood', '')}. Empty scene with no people, nobody, "
                        f"detailed manga background art.").replace(" . ", " ").replace("..", ".")
    if b.get("props"):
        out["props"] = (f"Object reference sheet: {b['props']}. Each object drawn twice, side view and three-quarter "
                        f"view, on a plain white background. No people.")
    return out


def char_refs(chars, text):
    """(reference specs for worker._graph, cast dicts for writer.cast_text)."""
    n = 3 if len(chars) == 1 else 2
    specs, cast = [], []
    for ch in chars:
        ids = refs.pick(ch, text, n if refs.CONT else refs.per_char(len(chars)))
        if refs.CONT:
            specs.append({"sheet": ids})
            cast.append({"name": ch["name"], "n": 1, "sheet": True, "traits": ch.get("traits") or ""})
        else:
            specs += ids
            cast.append({"name": ch["name"], "n": len(ids), "traits": ch.get("traits") or ""})
    return specs, cast


ONE = "One single picture filling the whole frame: not a comic page, no split screen, no grid, no inset panels."


def _extras(place_slot, props_slot, prev_slot, has_chars):
    parts = []
    if place_slot:
        parts.append(f"Image {place_slot} is only a reference for what the place looks like (same buildings, light and "
                     f"time of day); frame this panel as the scene says, do not copy its composition.")
    if props_slot:
        parts.append(f"Image {props_slot} is only a reference for what the objects look like; draw them the same.")
    if prev_slot:
        parts.append(f"Image {prev_slot} is the previous panel of this page: keep the same place, objects, light and "
                     f"time of day, but use a new camera angle and new poses; do not copy its composition.")
    if has_chars:
        parts.append("Draw new poses that fit the action; do not copy the pose or framing of any reference picture.")
    parts.append(ONE)
    return " ".join(parts)


def panel_job(pid, idx, seed=None, prm_extra=None):
    """Queue panel idx of page pid with its references; returns the job id (the caller stores it)."""
    page = db.get("pages", pid)
    pn = page["panels"][idx]
    chars = [db.one("SELECT * FROM characters WHERE slug=?", (s,)) for s in page["chars"]]
    missing = [page["chars"][i] for i, c in enumerate(chars) if not c or c["status"] != "ready"]
    if missing:  # never draw a panel without a character it should show
        raise PanelError(f"character not ready or gone: {', '.join(missing)}")
    chars = [chars[i] for i in pn.get("cast", range(len(chars))) if i < len(chars)]
    w, h = graphs.fit_size(layout.aspects()[idx], 1.0)
    params = {"w": w, "h": h, "seed": seed or worker.seed(), "page": pid, "idx": idx, "line": pn["line"],
              "quotes": pn.get("quotes", [])}
    specs = []
    prompt = pn["prompt"]
    if chars:
        specs, _ = char_refs(chars, pn["line"] + " " + pn["prompt"])
        empty = [c["name"] for c, s in zip(chars, specs) if refs.CONT and not s.get("sheet")]
        if empty:  # never draw a character without its pictures (klein would invent a person)
            raise PanelError(f"no reference pictures for {', '.join(empty)}")
        params["check_ref"], params["check_name"] = chars[0]["source_image"], chars[0]["name"]
    if refs.CONT:
        scene = page.get("scene") or {}
        slots = {}
        for k in ("plate", "props"):
            iid = (scene.get(k) or {}).get("image_id")
            if iid and len(specs) < 4:
                specs.append(iid)
                slots[k] = len(specs)
        prev = page["panels"][idx - 1].get("image_id") if idx > 0 and not scene else None
        if prev and len(specs) < 4:
            specs.append(prev)
            slots["prev"] = len(specs)
        extra = _extras(slots.get("plate"), slots.get("props"), slots.get("prev"), bool(chars))
        if extra:
            prompt = prompt.replace(graphs.STYLE, extra + " " + graphs.STYLE, 1)
    params["prompt"] = prompt
    # what this panel was given, shown on the page card so a wrong picture explains itself
    used = [f"{c['name']} sheet" if refs.CONT else c["name"] for c in chars]
    if refs.CONT:
        used += [{"plate": "place", "props": "objects", "prev": "previous panel"}[k] for k in slots]
    params["used"] = " + ".join(used) if used else "no reference"
    if specs:
        params["refs"] = specs
    params.update(prm_extra or {})
    return worker.add_job("panel", params, f"page:{pid}:{idx}")


def start(pid):
    """A new page: scene pictures first (continuity mode with a bible), then the panels (advance)."""
    page = db.get("pages", pid)
    if refs.CONT and page.get("bible"):
        scene = {}
        for kind, prompt in scene_prompts(page["bible"]).items():
            scene[kind] = {"prompt": prompt, "job_id": scene_job(pid, kind, prompt, page.get("seed"))}
        db.update("pages", pid, scene=scene)
    if not refs.CONT:
        page = db.get("pages", pid)
        panels = page["panels"]
        for i in range(4):
            panels[i]["job_id"] = panel_job(pid, i, _seed(page, i))
        db.update("pages", pid, panels=panels)
    advance(pid)


def scene_job(pid, kind, prompt, seed=None):
    w, h = graphs.SHAPES["wide"]
    return worker.add_job("scene", {"prompt": prompt, "w": w, "h": h, "seed": seed or worker.seed(), "page": pid,
                                    "kind": kind}, f"page:{pid}:scene:{kind}")


def _seed(page, i):
    return page["seed"] + i if page.get("seed") else None


def _busy(jid):
    return bool(jid) and db.get("jobs", jid)["status"] in ("queued", "running")


def busy(page):
    scene = page.get("scene") or {}
    return (any(_busy(v.get("job_id")) for v in scene.values())
            or any(_busy(p.get("job_id")) or _busy(p.get("check_id")) for p in page["panels"]))


def advance(pid):
    """Next step of a page: wait while something runs; then start the next panel not started yet (in order,
    continuity mode); when all are drawn, put the page together."""
    page = db.get("pages", pid)
    if not page or busy(page):
        return
    panels = page["panels"]
    todo = [i for i, p in enumerate(panels) if not p.get("job_id")]
    if todo:
        # in order with the previous panel as a reference; all at once when the scene pictures carry the place
        try:
            for i in (todo if page.get("scene") else todo[:1]):
                panels[i]["job_id"] = panel_job(pid, i, _seed(page, i))
                db.update("pages", pid, panels=panels)
        except PanelError as e:
            db.update("pages", pid, status="failed", error=str(e))
        return
    if page["status"] == "working":
        worker.compose_page(pid)


def scene_done(pid, kind, job):
    page = db.get("pages", pid)
    if not page:
        return
    scene = page.get("scene") or {}
    item = scene.get(kind) or {}
    if item.get("job_id") != job["id"]:
        return
    if job["status"] == "done":
        item["image_id"] = job["image_id"]
    item["error"] = job.get("error") if job["status"] == "failed" else None
    scene[kind] = item
    db.update("pages", pid, scene=scene)
    advance(pid)

