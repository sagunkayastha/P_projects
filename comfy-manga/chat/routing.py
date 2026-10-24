"""One model: Anima Manga (anime/manga illustrations)."""

MODEL = "anima-beret"
LABEL = "Anima Manga"
EST = 16  # warm seconds at these sizes on the 5070 Ti

SHAPES = {
    "wide": (1344, 768),
    "square": (1024, 1024),
    "tall": (832, 1216),
}


def plan(shape="tall", seed=42):
    key = shape if shape in SHAPES else "tall"
    w, h = SHAPES[key]
    return {
        "model": MODEL,
        "kind": "picture",
        "width": w,
        "height": h,
        "shape": key,
        "seed": seed,
        "est_seconds": EST,
        "style": "anime",
    }


def describe(p):
    mins, secs = divmod(p["est_seconds"], 60)
    eta = f"{mins} min" if mins else f"{secs} s"
    return f'{p["width"]}x{p["height"]} · ~{eta}'
