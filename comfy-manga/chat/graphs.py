"""ComfyUI graphs for the manga app. Built on workflows.py (the graphs measured in the studio work);
results are PreviewImage (ComfyUI temp folder) because the app downloads them through /view and keeps
its own copy on disk."""
import math

import workflows

STYLE = ("Black and white manga drawing: monochrome, greyscale, clean ink lineart, screentone shading, "
         "spot blacks.")
ANIMA_PREFIX = "monochrome, greyscale, manga, ink lineart, screentone, "
# Anima drifts to glamour shots on plain prompts (a "lighthouse" test came back as a bikini figure)
ANIMA_NEG = workflows.NEG_BW + ", swimsuit, bikini, lingerie, underwear, cleavage, text, speech bubble, watermark"

SHAPES = {"tall": (832, 1216), "square": (1024, 1024), "wide": (1344, 768)}


def fit_size(aspect, mp=1.0):
    """Width/height near `mp` megapixels with the given aspect (w/h), multiples of 16."""
    h = math.sqrt(mp * 1_000_000 / aspect)
    w = h * aspect
    return max(256, int(round(w / 16)) * 16), max(256, int(round(h / 16)) * 16)


def _preview(wf):
    for n, node in wf.items():
        if node["class_type"] == "SaveImage":
            wf[n] = {"class_type": "PreviewImage", "inputs": {"images": node["inputs"]["images"]}}
    return wf


def anima_bw(prompt, w, h, seed):
    """Anima Manga picture from a text prompt, true greyscale."""
    wf = workflows.anima(ANIMA_PREFIX + prompt, w, h, seed, "app", ANIMA_NEG)
    return _preview(workflows.bw_finish(wf, ["9", 0], w, h, "app"))


def klein_edit(prompt, image, w, h, seed):
    """klein 9B edit of one reference picture (character sets)."""
    wf = workflows.klein9_edit(prompt, image, w, h, seed, "app")
    return _preview(workflows.bw_finish(wf, ["17", 0], w, h, "app", save_id="18"))


def klein_refs(prompt, images, w, h, seed):
    """klein 9B with several reference pictures (image 1, image 2, ...)."""
    wf = workflows.klein9_refs(prompt, images, w, h, seed, "app")
    return _preview(workflows.bw_finish(wf, ["17", 0], w, h, "app", save_id="18"))


def score(reference, candidates):
    """Face similarity of each candidate to the reference (custom node in comfyui/nodes/manga_score)."""
    return {"1": {"class_type": "MangaRefScore", "inputs": {"reference": reference,
                                                            "candidates": "\n".join(candidates)}}}
