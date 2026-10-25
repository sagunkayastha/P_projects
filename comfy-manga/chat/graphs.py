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

# Colour mode (covers, chapter art; 2026-10-26): same graphs, no greyscale finish, colour wording
COLOUR_STYLE = ("Full-colour anime manga illustration, like a manga volume cover: clean ink lineart, vibrant cel "
                "shading, rich harmonious colours.")
ANIMA_COLOUR_PREFIX = "anime coloring, manga cover illustration, vibrant colors, ink lineart, "
_BW_NEG = ", color, colored, spot color, limited palette, orange, blue, red, yellow"


def colourize(wf):
    """Turn a B/W graph into a colour one in place: drop the greyscale nodes (bw_finish ids 40-51; the output
    reads the image they started from) and swap the B/W wording for colour wording."""
    if "40" in wf and wf["40"]["class_type"] == "ImageToMask":
        src = wf["40"]["inputs"]["image"]
        for k in range(40, 52):
            wf.pop(str(k), None)
        for node in wf.values():
            if node["class_type"] in ("PreviewImage", "SaveImage") and node["inputs"].get("images") == ["51", 0]:
                node["inputs"]["images"] = src
    for node in wf.values():
        for k, v in node["inputs"].items():
            if isinstance(v, str):
                v = (v.replace(STYLE, COLOUR_STYLE).replace(ANIMA_PREFIX, ANIMA_COLOUR_PREFIX)
                     .replace(_BW_NEG, "").replace(", monochrome, greyscale", ""))
                if k == "text" and v.startswith(workflows.NEG):  # Anima negative: push away from B/W
                    v += ", monochrome, greyscale, black and white, lineart only, sketch"
                node["inputs"][k] = v
    return wf


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


# Anima-family models the user can pick in the chat (diffusion model files in models/diffusion_models)
UNETS = {"anima": "beretMixAnimaManga_v20.safetensors", "vision": "mangaVisionANIIL_animaV1.safetensors"}


def anima_bw(prompt, w, h, seed, model="anima"):
    """Anima Manga picture from a text prompt, true greyscale."""
    wf = workflows.anima(ANIMA_PREFIX + prompt, w, h, seed, "app", ANIMA_NEG)
    wf["1"]["inputs"]["unet_name"] = UNETS[model]
    return _preview(workflows.bw_finish(wf, ["9", 0], w, h, "app"))


def klein_t2i(prompt, w, h, seed):
    """klein 9B from a text prompt only (no reference picture)."""
    wf = workflows.klein9_refs(prompt, ["none.png"], w, h, seed, "app")
    for k in ("60", "61", "62", "63", "64"):  # the reference chain of the dummy picture
        del wf[k]
    wf["15"]["inputs"]["positive"], wf["15"]["inputs"]["negative"] = ["7", 0], ["8", 0]
    return _preview(workflows.bw_finish(wf, ["17", 0], w, h, "app", save_id="18"))


SCRIBBLE = "scribble_lora_260405_v1.0.2-step00000300.safetensors"  # Anima Scribble Control LoRA (civitai 2846262)


def anima_scribble(prompt, sketch, w, h, seed, model="anima", until=0.4):
    """Anima steered by the user's sketch through the Scribble Control LoRA: the sketch (inverted = white lines on
    black, like PiDiNet) as a Cosmos reference latent + the LoRA for the first 40% of the steps, then plain Anima."""
    wf = workflows.anima(ANIMA_PREFIX + prompt, w, h, seed, "app", ANIMA_NEG)
    wf["1"]["inputs"]["unet_name"] = UNETS[model]
    wf["60"] = {"class_type": "LoadImage", "inputs": {"image": sketch}}
    wf["61"] = {"class_type": "ImageScale", "inputs": {"image": ["60", 0], "upscale_method": "lanczos", "width": w,
                "height": h, "crop": "center"}}
    wf["62"] = {"class_type": "ImageInvert", "inputs": {"image": ["61", 0]}}
    wf["63"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["62", 0], "vae": ["3", 0]}}
    wf["64"] = {"class_type": "ApplyCosmosReferenceLatent", "inputs": {"model": ["1", 0], "ref_latents.ref_latent_1": ["63", 0]}}
    wf["65"] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["64", 0], "lora_name": SCRIBBLE, "strength_model": 1.0}}
    steps, cut = 32, int(32 * until)
    common = {"noise_seed": seed, "steps": steps, "cfg": 4.0, "sampler_name": "er_sde", "scheduler": "beta",
              "positive": ["5", 0], "negative": ["6", 0]}
    wf["66"] = {"class_type": "KSamplerAdvanced", "inputs": {**common, "model": ["65", 0], "add_noise": "enable",
                "latent_image": ["7", 0], "start_at_step": 0, "end_at_step": cut, "return_with_leftover_noise": "enable"}}
    wf["8"] = {"class_type": "KSamplerAdvanced", "inputs": {**common, "model": ["1", 0], "add_noise": "disable",
               "latent_image": ["66", 0], "start_at_step": cut, "end_at_step": 10000, "return_with_leftover_noise": "disable"}}
    return _preview(workflows.bw_finish(wf, ["9", 0], w, h, "app"))


def anima_guided(prompt, w, h, seed, control=None, ref=None, model="anima", strength=1.0, end=0.6, ip=0.7):
    """Anima steered by a sketch (ControlNet-LLLite lineart control) and/or a character picture (IP-Adapter)."""
    wf = workflows.anima_control(ANIMA_PREFIX + prompt, control, w, h, seed, "app", strength, end, ref=ref, ip_strength=ip,
                                 neg_extra=ANIMA_NEG[len(workflows.NEG_BW) + 2:])
    wf["1"]["inputs"]["unet_name"] = UNETS[model]
    return _preview(wf)


# Qwen-Image-Edit 2511 (GGUF Q4_K_M, city96 loader) + Lightning 4-step LoRA; optional Multiple-Angles LoRA (fal)
QWEN = {"unet": "qwen-image-edit-2511-Q4_K_M.gguf", "clip": "qwen_2.5_vl_7b_nvfp4.safetensors",
        "vae": "qwen_image_vae.safetensors", "fast": "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors",
        "angles": "qwen-image-edit-2511-multiple-angles-lora.safetensors"}


def qwen_edit(prompt, images, w, h, seed, angles=False):
    """Qwen-Image-Edit 2511 with 1-3 pictures (Picture 1 = the one to edit), 4 steps, cfg 1, true greyscale."""
    wf = {"1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": QWEN["unet"]}},
          "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": QWEN["clip"], "type": "qwen_image", "device": "default"}},
          "3": {"class_type": "VAELoader", "inputs": {"vae_name": QWEN["vae"]}}}
    model = workflows.with_loras(wf, [(QWEN["fast"], 1.0)] + ([(QWEN["angles"], 1.0)] if angles else []))
    wf["120"] = {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": model, "shift": 3.1}}
    wf["121"] = {"class_type": "CFGNorm", "inputs": {"model": ["120", 0], "strength": 1.0}}
    pics = {}
    for i, img in enumerate(images[:3]):
        n = 130 + i * 2
        wf[str(n)] = {"class_type": "LoadImage", "inputs": {"image": img}}
        wf[str(n + 1)] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": [str(n), 0],
                          "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 1}}
        pics[f"image{i + 1}"] = [str(n + 1), 0]
    wf["140"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["2", 0], "prompt": prompt, "vae": ["3", 0], **pics}}
    wf["141"] = {"class_type": "TextEncodeQwenImageEditPlus", "inputs": {"clip": ["2", 0], "prompt": "", "vae": ["3", 0], **pics}}
    wf["142"] = {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": ["140", 0],
                "reference_latents_method": "index_timestep_zero"}}
    wf["143"] = {"class_type": "FluxKontextMultiReferenceLatentMethod", "inputs": {"conditioning": ["141", 0],
                "reference_latents_method": "index_timestep_zero"}}
    wf["144"] = {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}}
    wf["145"] = {"class_type": "KSampler", "inputs": {"model": ["121", 0], "positive": ["142", 0], "negative": ["143", 0],
                "latent_image": ["144", 0], "seed": seed, "steps": 4, "cfg": 1.0, "sampler_name": "euler",
                "scheduler": "simple", "denoise": 1.0}}
    wf["146"] = {"class_type": "VAEDecode", "inputs": {"samples": ["145", 0], "vae": ["3", 0]}}
    return _preview(workflows.bw_finish(wf, ["146", 0], w, h, "app", save_id="18"))


# Qwen-Image 2.1 (int8) + Alibaba PAI Fun ControlNet Union (int8), ComfyUI core nodes (PR #16519)
Q21 = {"unet": "qwen_image_2.1_int8_convrot.safetensors", "clip": "qwen3vl_8b_w4a8.safetensors",
       "vae": "qwen_image_2.1_vae_bf16.safetensors", "union": "qwen_image_2.1_fun_controlnet_union_int8_convrot.safetensors"}


def qwen21_control(prompt, sketch, w, h, seed, strength=1.0, steps=30, cfg=4.0, neg="", end=1.0, invert=True):
    """Qwen-Image 2.1 drawing from words, the sketch (inverted: white lines on black) as Fun ControlNet scribble."""
    wf = {"1": {"class_type": "UNETLoader", "inputs": {"unet_name": Q21["unet"], "weight_dtype": "default"}},
          "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": Q21["clip"], "type": "qwen_image", "device": "default"}},
          "3": {"class_type": "VAELoader", "inputs": {"vae_name": Q21["vae"]}},
          "4": {"class_type": "ModelPatchLoader", "inputs": {"name": Q21["union"]}},
          "130": {"class_type": "LoadImage", "inputs": {"image": sketch}},
          "131": {"class_type": "ImageScale", "inputs": {"image": ["130", 0], "upscale_method": "lanczos", "width": w,
                  "height": h, "crop": "center"}},
          "132": {"class_type": "ImageInvert", "inputs": {"image": ["131", 0]}},
          "133": {"class_type": "ZImageFunControlnet", "inputs": {"model": ["1", 0], "model_patch": ["4", 0], "vae": ["3", 0],
                  "strength": strength, "image": ["132" if invert else "131", 0], "start_percent": 0.0, "end_percent": end}},
          "140": {"class_type": "TextEncodeQwenImage21", "inputs": {"clip": ["2", 0], "prompt": prompt, "negative_prompt": neg,
                  "resolution": 1024}},
          "144": {"class_type": "EmptySD3LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
          "145": {"class_type": "KSampler", "inputs": {"model": ["133", 0], "positive": ["140", 0], "negative": ["140", 1],
                  "latent_image": ["144", 0], "seed": seed, "steps": steps, "cfg": cfg, "sampler_name": "euler",
                  "scheduler": "simple", "denoise": 1.0}},
          "146": {"class_type": "VAEDecode", "inputs": {"samples": ["145", 0], "vae": ["3", 0]}}}
    return _preview(workflows.bw_finish(wf, ["146", 0], w, h, "app", save_id="18"))


def klein_edit(prompt, image, w, h, seed):
    """klein 9B edit of one reference picture (character sets)."""
    wf = workflows.klein9_edit(prompt, image, w, h, seed, "app")
    return _preview(workflows.bw_finish(wf, ["17", 0], w, h, "app", save_id="18"))


def klein_refs(prompt, images, w, h, seed, loras=None):
    """klein 9B with several reference pictures (image 1, image 2, ...); loras = [(file, strength), ...]."""
    wf = workflows.klein9_refs(prompt, images, w, h, seed, "app")
    if loras:
        wf["15"]["inputs"]["model"] = workflows.with_loras(wf, loras)
    return _preview(workflows.bw_finish(wf, ["17", 0], w, h, "app", save_id="18"))


def score(reference, candidates):
    """Face similarity of each candidate to the reference (custom node in comfyui/nodes/manga_score)."""
    return {"1": {"class_type": "MangaRefScore", "inputs": {"reference": reference,
                                                            "candidates": "\n".join(candidates)}}}


# ---- "Anima look" two-stage pipeline (2026-10-26, user's choice: one visible model) ----
# B/W: a helper (klein / Qwen-Edit: layout, edits, pose, references) draws first, Anima redraws it in its manga
# style through LLLite (the helper picture as layout control, 1.0 for the first 60% of the steps; tuned on the r1
# cases) + the IP-Adapter on the character's picture. Colour: then Qwen-Edit colours Anima's drawing.
IN = "__IN__"
COLOUR_EDIT = ("Colour Picture 1, a black-and-white manga drawing: keep every line, the faces, the poses, the "
               "composition and the drawing style exactly; only add full colour with clean cel shading. ")


def chain(a, b, prefix):
    """Feed graph a's output picture into graph b (its LoadImage named IN); b's node ids get `prefix`."""
    out = [k for k, n in a.items() if n["class_type"] in ("PreviewImage", "SaveImage")][0]
    ref = a.pop(out)["inputs"]["images"]
    loads = {k for k, n in b.items() if n["class_type"] == "LoadImage" and n["inputs"].get("image") == IN}
    for k, n in b.items():
        if k in loads:
            continue
        ins = {}
        for name, v in n["inputs"].items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and v[0] in b:
                v = ref if v[0] in loads else [prefix + v[0], v[1]]
            ins[name] = v
        a[prefix + k] = {**n, "inputs": ins}
    return a


def pipeline(helper, pipe, ipref=None):
    """helper graph -> Anima redraw (B/W) -> optional Qwen-Edit colouring."""
    w, h, seed = pipe["w"], pipe["h"], pipe["seed"]
    wf = chain(helper, anima_guided(pipe["prompt"], w, h, seed, IN, ipref, "anima", 1.0, 0.6), "a")
    if pipe.get("colour"):
        wf = chain(wf, colourize(qwen_edit(COLOUR_EDIT + COLOUR_STYLE, [IN], w, h, seed)), "c")
    return wf
