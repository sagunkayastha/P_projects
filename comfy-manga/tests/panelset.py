"""Fixed panel test set for 'do panels follow the line' (user priority 2026-10-25): 8 neutral lines with explicit
camera / pose / action / place asks, the test characters Nori (young woman, glasses, scarf) and Bram (old man,
white beard, flat cap). Each line has a yes/no checklist for the VLM judge and the reviewers, and a stick-figure
pose (normalised x, y joints) for the pose-control hypothesis.
"""

# who: test character slugs; shape: picture size key; checks: yes/no questions (yes = followed)
SET = [
    {"name": "lowangle", "who": ["bram"], "shape": "tall",
     "line": "Low angle looking up at Bram standing on the steps of an old stone library",
     "checks": {"angle": "Is the camera low, looking UP at the man (we see him from below, strong upward perspective)?",
                "pose": "Is the old bearded man standing?",
                "place": "Are there stone steps and a large old stone building (a library)?"}},
    {"name": "ots", "who": ["bram", "nori"], "shape": "wide",
     "line": "Over-the-shoulder shot from behind Bram, looking at Nori across a cafe table",
     "checks": {"angle": "Is it an over-the-shoulder shot: the old bearded man's back/shoulder big in the foreground, "
                         "the young woman with glasses facing the camera further away?",
                "pose": "Are the two people sitting across a table from each other?",
                "place": "Is it inside a cafe (table, cups, cafe interior)?"}},
    {"name": "running", "who": ["nori"], "shape": "tall",
     "line": "Nori running toward the camera down a narrow alley, arms swinging",
     "checks": {"angle": "Is the young woman facing the camera and coming toward it (front view)?",
                "pose": "Is she clearly running (one foot off the ground, arms swinging), not walking or standing?",
                "place": "Is it a narrow alley between buildings?"}},
    {"name": "stairs", "who": ["nori"], "shape": "tall",
     "line": "Nori sitting on the stairs of a train station, chin in her hands",
     "checks": {"angle": "Is she shown full or most of her body (not a face close-up)?",
                "pose": "Is the young woman sitting on stairs with her chin resting in her hands?",
                "place": "Is it a train station (platform, trains, station signs or station stairs)?"}},
    {"name": "topdown", "who": ["bram"], "shape": "square",
     "line": "Top-down view of Bram lying on his back in the grass in a park",
     "checks": {"angle": "Is the camera directly above, looking straight DOWN at the man (bird's-eye view)?",
                "pose": "Is the old bearded man lying on his back?",
                "place": "Is he on grass in a park?"}},
    {"name": "back", "who": ["nori"], "shape": "tall",
     "line": "Back view of Nori standing at a harbor railing, looking at the boats",
     "checks": {"angle": "Do we see the young woman from BEHIND (her back to the camera, face not visible)?",
                "pose": "Is she standing at a railing?",
                "place": "Is it a harbor with boats on the water?"}},
    {"name": "hands", "who": ["bram"], "shape": "square",
     "line": "Close-up of Bram's hands holding an old pocket watch on a workbench in a clock shop",
     "checks": {"angle": "Is it a close-up where the HANDS fill most of the picture (face not the main subject)?",
                "pose": "Are the hands holding a pocket watch?",
                "place": "Is there a workbench or clock shop detail (tools, clocks, gears)?"}},
    {"name": "bridge", "who": ["nori", "bram"], "shape": "wide",
     "line": "Wide shot of Nori and Bram walking side by side across a snowy bridge",
     "checks": {"angle": "Is it a wide shot where both people are small and the bridge and surroundings are large?",
                "pose": "Are the two people walking side by side?",
                "place": "Is it a bridge with snow?"}},
]

# who appears, for the count check (judge words)
LOOKS = {"nori": "the young woman with glasses", "bram": "the old bearded man"}

# stick figures for the pose-control test: joints in 0..1 of the picture, None = hidden
J = ("head", "neck", "hip", "lsh", "lel", "lha", "rsh", "rel", "rha", "lkn", "lft", "rkn", "rft")
POSES = {
    # low angle: big feet near the bottom, small head high up (perspective from below)
    "lowangle": [{"head": (.5, .10), "neck": (.5, .17), "hip": (.5, .52), "lsh": (.40, .19), "lel": (.36, .35),
                  "lha": (.36, .50), "rsh": (.60, .19), "rel": (.64, .35), "rha": (.64, .50), "lkn": (.42, .74),
                  "lft": (.36, .97), "rkn": (.58, .74), "rft": (.64, .97)}],
    # over the shoulder: big back figure left (head + shoulders), small facing figure right
    "ots": [{"head": (.22, .45), "neck": (.22, .62), "hip": None, "lsh": (.05, .70), "lel": None, "lha": None,
             "rsh": (.40, .70), "rel": None, "rha": None, "lkn": None, "lft": None, "rkn": None, "rft": None},
            {"head": (.68, .30), "neck": (.68, .38), "hip": (.68, .62), "lsh": (.62, .40), "lel": (.60, .52),
             "lha": (.64, .60), "rsh": (.74, .40), "rel": (.76, .52), "rha": (.72, .60), "lkn": None, "lft": None,
             "rkn": None, "rft": None}],
    "running": [{"head": (.5, .14), "neck": (.5, .22), "hip": (.5, .52), "lsh": (.40, .24), "lel": (.32, .36),
                 "lha": (.38, .46), "rsh": (.60, .24), "rel": (.68, .32), "rha": (.64, .20), "lkn": (.42, .68),
                 "lft": (.44, .90), "rkn": (.60, .64), "rft": (.66, .74)}],
    "stairs": [{"head": (.5, .30), "neck": (.5, .38), "hip": (.5, .62), "lsh": (.42, .40), "lel": (.40, .56),
                "lha": (.47, .36), "rsh": (.58, .40), "rel": (.60, .56), "rha": (.53, .36), "lkn": (.40, .60),
                "lft": (.40, .84), "rkn": (.60, .60), "rft": (.60, .84)}],
    # lying on the back seen from above: figure along the diagonal, arms out
    "topdown": [{"head": (.25, .22), "neck": (.30, .28), "hip": (.55, .55), "lsh": (.24, .34), "lel": (.14, .44),
                 "lha": (.08, .56), "rsh": (.37, .25), "rel": (.48, .16), "rha": (.58, .10), "lkn": (.60, .70),
                 "lft": (.66, .88), "rkn": (.70, .60), "rft": (.88, .66)}],
    "back": [{"head": (.5, .20), "neck": (.5, .28), "hip": (.5, .58), "lsh": (.40, .30), "lel": (.36, .44),
              "lha": (.38, .54), "rsh": (.60, .30), "rel": (.64, .44), "rha": (.62, .54), "lkn": (.45, .76),
              "lft": (.45, .95), "rkn": (.55, .76), "rft": (.55, .95)}],
    "hands": [],  # hands close-up: no figure (pose control skipped)
    "bridge": [{"head": (.40, .48), "neck": (.40, .52), "hip": (.40, .64), "lsh": (.38, .53), "lel": (.37, .58),
                "lha": (.37, .62), "rsh": (.42, .53), "rel": (.43, .58), "rha": (.43, .62), "lkn": (.39, .70),
                "lft": (.38, .76), "rkn": (.41, .70), "rft": (.42, .76)},
               {"head": (.48, .46), "neck": (.48, .51), "hip": (.48, .64), "lsh": (.46, .52), "lel": (.45, .58),
                "lha": (.45, .62), "rsh": (.50, .52), "rel": (.51, .58), "rha": (.51, .62), "lkn": (.47, .70),
                "lft": (.46, .76), "rkn": (.49, .70), "rft": (.50, .76)}],
}
BONES = [("head", "neck"), ("neck", "hip"), ("neck", "lsh"), ("lsh", "lel"), ("lel", "lha"), ("neck", "rsh"),
         ("rsh", "rel"), ("rel", "rha"), ("hip", "lkn"), ("lkn", "lft"), ("hip", "rkn"), ("rkn", "rft")]


def stick_png(name, w, h):
    """PNG bytes: black stick figure(s) on white (head = circle), or None when the line has no figure pose."""
    import io

    from PIL import Image, ImageDraw
    figs = POSES.get(name) or []
    if not figs:
        return None
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    lw = max(4, w // 90)
    for f in figs:
        pts = {k: (v[0] * w, v[1] * h) for k, v in f.items() if v}
        for a, b in BONES:
            if a in pts and b in pts:
                d.line([pts[a], pts[b]], fill="black", width=lw)
        if "head" in pts and "neck" in pts:
            r = 0.6 * (abs(pts["neck"][1] - pts["head"][1]) or h * 0.05)
            x, y = pts["head"]
            d.ellipse([x - r, y - r, x + r, y + r], outline="black", width=lw)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


# round p2 (C): the shots no variant drew in p1, plus one more of each kind
HARD = [SET[1], SET[6], SET[4],
        {"name": "otsnori", "who": ["nori", "bram"], "shape": "wide",
         "line": "Over-the-shoulder shot from behind Nori, looking at Bram behind the counter of his clock shop",
         "checks": {"angle": "Is it an over-the-shoulder shot: the young woman's back/shoulder (short black hair) big "
                             "in the foreground, the old bearded man facing the camera further away?",
                    "pose": "Is the old bearded man standing behind a counter, facing the young woman?",
                    "place": "Is it inside a clock shop (clocks on the walls, a counter)?"}},
        {"name": "handsbook", "who": ["nori"], "shape": "square",
         "line": "Close-up of Nori's hands opening an old book on a library table",
         "checks": {"angle": "Is it a close-up where the HANDS and the book fill most of the picture (face not the main "
                             "subject)?",
                    "pose": "Are the hands opening or holding an open book?",
                    "place": "Is the book on a table (library or desk detail)?"}},
        {"name": "topcafe", "who": ["nori"], "shape": "square",
         "line": "Top-down view of Nori sitting at a small round cafe table with a cup of tea",
         "checks": {"angle": "Is the camera directly above, looking straight DOWN (bird's-eye view: we see the top of "
                             "her head and the table top)?",
                    "pose": "Is the young woman sitting at a round table with a cup?",
                    "place": "Is it a cafe table with a cup of tea?"}}]

# filled grey blockouts (near = dark, far = light, props = pale): shapes as fractions of the picture
NEAR, FAR, PROP = 60, 150, 205
SIL = {
    "ots": [("rect", PROP, (.30, .62, 1.0, .72)), ("ell", FAR, (.62, .20, .74, .38)), ("rect", FAR, (.58, .37, .78, .64)),
            ("ell", NEAR, (.02, .22, .40, .78)), ("poly", NEAR, [(0, 1), (0, .62), (.18, .58), (.36, .62), (.52, 1)])],
    "otsnori": [("rect", PROP, (0, .60, .70, .72)), ("ell", FAR, (.26, .18, .38, .36)), ("rect", FAR, (.22, .35, .42, .62)),
             ("ell", NEAR, (.60, .20, .98, .78)), ("poly", NEAR, [(1, 1), (1, .62), (.82, .58), (.64, .62), (.48, 1)])],
    "hands": [("rect", PROP, (0, .78, 1, 1)), ("poly", NEAR, [(0, .55), (.30, .48), (.46, .56), (.44, .72), (.0, .80)]),
              ("poly", NEAR, [(1, .52), (.68, .46), (.54, .56), (.56, .72), (1, .82)]),
              ("ell", 245, (.38, .40, .62, .66)), ("ring", 30, (.38, .40, .62, .66))],
    "handsbook": [("rect", PROP, (0, .70, 1, 1)), ("poly", 235, [(.12, .40), (.50, .48), (.88, .40), (.88, .78),
                                                                 (.50, .86), (.12, .78)]),
                  ("poly", NEAR, [(0, .62), (.14, .46), (.24, .52), (.20, .74), (0, .86)]),
                  ("poly", NEAR, [(1, .60), (.86, .44), (.76, .50), (.80, .72), (1, .84)])],
    "topdown": [("rect", 225, (0, 0, 1, 1)), ("ell", NEAR, (.18, .14, .34, .30)), ("poly", NEAR, [(.24, .30), (.40, .24),
                (.62, .52), (.50, .62)]), ("line", NEAR, [(.26, .33), (.10, .52)]), ("line", NEAR, [(.38, .26), (.56, .10)]),
                ("line", NEAR, [(.56, .58), (.66, .90)]), ("line", NEAR, [(.58, .55), (.90, .66)])],
    "topcafe": [("ell", PROP, (.30, .30, .80, .80)), ("ell", 245, (.50, .44, .60, .54)), ("ring", 30, (.50, .44, .60, .54)),
                ("ell", NEAR, (.08, .30, .38, .68)), ("ell", 25, (.14, .38, .30, .58))],
}


def sil_png(name, w, h):
    """PNG bytes: the line's grey blockout on white, or None."""
    import io

    from PIL import Image, ImageDraw
    if name not in SIL:
        return None
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    for kind, g, pts in SIL[name]:
        c = (g, g, g)
        if kind in ("rect", "ell", "ring"):
            box = [pts[0] * w, pts[1] * h, pts[2] * w, pts[3] * h]
            if kind == "rect":
                d.rectangle(box, fill=c)
            elif kind == "ell":
                d.ellipse(box, fill=c)
            else:
                d.ellipse(box, outline=c, width=max(4, w // 120))
        else:
            xy = [(x * w, y * h) for x, y in pts]
            if kind == "poly":
                d.polygon(xy, fill=c)
            else:
                d.line(xy, fill=c, width=max(10, w // 18))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
