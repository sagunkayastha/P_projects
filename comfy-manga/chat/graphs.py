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


def anima_guided(prompt, w, h, seed, control=None, ref=None, model="anima"):
    """Anima steered by a sketch (ControlNet-LLLite lineart control) and/or a character picture (IP-Adapter)."""
    wf = workflows.anima_control(ANIMA_PREFIX + prompt, control, w, h, seed, "app", 1.0, 0.6, ref=ref,
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
