"""Which reference pictures of a character klein gets for one picture.

The source picture is always image 1 of a character (it is the truth). The other slots go to the saved
views (labels like "profile-left_smile", "low_angry", "outfit-coat") that best match the panel: camera
angle first, then outfit, then expression; ties go to the view most like the source (face check score).
"""
import os
import re

# Phase B switch (angle-matched refs, trait list, best-of-2 + source floor, review before save). Off = old behaviour.
ON = os.environ.get("MANGA_B", "1") != "0"


def per_char(n_chars):
    """Reference pictures per character in one picture (klein gets at most 4)."""
    return 3 if ON and n_chars == 1 else 2

# camera words in a panel line/prompt -> wanted view family (the view labels' angle part)
ANGLE_WORDS = [
    ("profile", r"profile|side view|from the side|side-on|sideways"),
    ("back", r"from behind(?! (?:the|a|an|his|her|their) )|back view|seen from the back|walks away|over (?:her|his|their|the) shoulder|back to the camera"),
    ("low", r"from below|low[- ]angle|worm'?s[- ]eye|looking up at (?:her|him|them)|towering"),
    ("high", r"from above|high[- ]angle|bird'?s[- ]eye|top[- ]down|looking down at (?:her|him|them)"),
    ("34", r"three[- ]quarter|turns? (?:her|his|their) head|glances"),
    ("front", r"close[- ]?up|faces the camera|front view|looks at the camera|portrait"),
]
FAMILY = {"front": "front", "34left": "34", "34right": "34", "profile-left": "profile", "profile-right": "profile",
          "back34": "back", "low": "low", "high": "high"}
NEAR = {"front": {"34"}, "34": {"front", "profile"}, "profile": {"34"}, "back": {"34", "profile"},
        "low": {"front", "34"}, "high": {"front", "34"}}
EXPR_WORDS = [("smile", r"smil|laugh|grin|happy|cheer|joy"),
              ("angry", r"angr|shout|yell|frown|furious|glare|scream|mad\b")]
OUTFIT_WORDS = [("coat", r"\bcoat\b|winter|snow|scarf"), ("sleep", r"pajama|pyjama|in bed|sleep|wakes up"),
                ("casual", r"hoodie|casual"), ("sport", r"tracksuit|sport|gym|jogging|running")]


def wanted(text):
    """(view family, expression, outfit or None) a panel asks for."""
    t = text.lower()
    fam = next((f for f, rx in ANGLE_WORDS if re.search(rx, t)), "34")
    expr = next((e for e, rx in EXPR_WORDS if re.search(rx, t)), "neutral")
    outfit = next((o for o, rx in OUTFIT_WORDS if re.search(rx, t)), None)
    side = "left" if re.search(r"fac\w* left|to the left", t) else "right" if re.search(r"fac\w* right|to the right", t) else None
    return fam, expr, outfit, side


def _match(label, want):
    fam, expr, outfit, side = want
    if label.startswith("outfit-"):
        # outfit views are three-quarter, calm: only worth a slot when the panel asks for that outfit
        return (6 if outfit and label == f"outfit-{outfit}" else -10) + (1 if fam in ("34", "front") else 0)
    ang, _, ex = label.partition("_")
    f = FAMILY.get(ang)
    s = 4 if f == fam else 2 if f in NEAR.get(fam, ()) else 0
    if side and ang.endswith(side):
        s += 1
    s += 1 if ex == expr else 0
    return s - (3 if outfit else 0)  # wrong clothes when a panel asks for another outfit


def pick(ch, text, n):
    """Source + the n-1 saved views that fit `text` best (image ids). ch: character row with refs/scores."""
    out = [ch["source_image"]]
    if not ON:  # old rule: the source + the best-scored view
        best = [r for r in (ch.get("refs") or []) if r != ch["source_image"]]
        return out + [best[0] if best else ch["source_image"]]
    scores = ch.get("scores") or {}
    want = wanted(text)
    cands = []
    for iid in ch.get("refs") or []:
        if iid == ch["source_image"]:
            continue
        sc = scores.get(str(iid), {})
        fs = sc.get("face_sim")
        q = fs if fs is not None else sc.get("whole_sim", 0) - 0.3
        cands.append((_match(sc.get("label", ""), want), q, iid))
    cands.sort(key=lambda c: (-c[0], -c[1]))
    fams = set()
    for m, q, iid in cands:
        if len(out) >= n:
            break
        fam = FAMILY.get(scores.get(str(iid), {}).get("label", "").partition("_")[0])
        if len(out) > 1 and fam in fams and len(cands) > n:
            continue  # second view: prefer another angle family over a near duplicate
        fams.add(fam)
        out.append(iid)
    for m, q, iid in cands:  # fill if the family rule left a slot open
        if len(out) >= n:
            break
        if iid not in out:
            out.append(iid)
    while len(out) < n:
        out.append(ch["source_image"])
    return out
