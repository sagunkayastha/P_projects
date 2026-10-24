"""Manga workflow: beretMix Anima Manga v2.0 on ComfyUI core nodes.

Prompt prefix and sampler settings are the ones measured on this PC (32 steps, cfg 4, er_sde/beta).
"""

NEG = ("worst quality, low quality, artist name, blurry, jpeg artifacts, chromatic aberration")
# Studio (B/W manga characters): Anima still paints well-known outfits in their colours (spot colour) unless told not to.
NEG_BW = NEG + ", nsfw, nude, naked, topless, bottomless, kiss, yuri, color, colored, spot color, limited palette, orange, blue, red, yellow"


def _save(prefix, ref):
    return {"class_type": "SaveImage", "inputs": {"images": ref, "filename_prefix": prefix}}


def anima(prompt, w, h, seed, prefix, neg=NEG):
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "beretMixAnimaManga_v20.safetensors",
              "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_06b_base.safetensors",
              "type": "stable_diffusion"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "qwen_image_vae.safetensors"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "masterpiece, best quality, " + prompt,
              "clip": ["2", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": neg, "clip": ["2", 0]}},
        "7": {"class_type": "EmptyLatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "8": {"class_type": "KSampler", "inputs": {"model": ["1", 0], "seed": seed, "steps": 32, "cfg": 4.0,
              "sampler_name": "er_sde", "scheduler": "beta", "positive": ["5", 0], "negative": ["6", 0],
              "latent_image": ["7", 0], "denoise": 1.0}},
        "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": _save(prefix, ["9", 0]),
    }


# ---- Character studio (2026-10-24) ----

def anima_i2i(prompt, image, w, h, seed, prefix, denoise, mask=None, neg=NEG_BW):
    """Anima img2img from `image` (input-folder name). With `mask` (white = repaint) only that area changes:
    noise mask on the latent, then the result is pasted back over the source so the rest stays pixel-exact."""
    wf = anima(prompt, w, h, seed, prefix, neg)
    wf["20"] = {"class_type": "LoadImage", "inputs": {"image": image}}
    wf["21"] = {"class_type": "ImageScale", "inputs": {"image": ["20", 0], "upscale_method": "lanczos",
                "width": w, "height": h, "crop": "center"}}
    wf["22"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["21", 0], "vae": ["3", 0]}}
    wf["8"]["inputs"]["latent_image"] = ["22", 0]
    wf["8"]["inputs"]["denoise"] = max(0.05, min(1.0, denoise))
    if mask:
        wf["23"] = {"class_type": "LoadImageMask", "inputs": {"image": mask, "channel": "red"}}
        wf["24"] = {"class_type": "GrowMask", "inputs": {"mask": ["23", 0], "expand": 6, "tapered_corners": True}}
        wf["25"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["22", 0], "mask": ["24", 0]}}
        wf["8"]["inputs"]["latent_image"] = ["25", 0]
        wf["26"] = {"class_type": "ImageCompositeMasked", "inputs": {"destination": ["21", 0], "source": ["9", 0],
                    "x": 0, "y": 0, "resize_source": False, "mask": ["24", 0]}}
        wf["10"] = _save(prefix, ["26", 0])
    return wf


def klein9_edit(prompt, image, w, h, seed, prefix):
    """FLUX.2 klein 9B NVFP4 edit with one reference picture (same graph as the main comfyui stack's klein9-ref:
    4 steps, cfg 1, Qwen3-8B fp4-mixed encoder). Fills the 16 GB card: free ComfyUI before the first job."""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {"unet_name": "flux-2-klein-9b-nvfp4.safetensors",
              "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_8b_fp4mixed.safetensors", "type": "flux2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "flux2-vae.safetensors"}},
        "4": {"class_type": "LoadImage", "inputs": {"image": image}},
        "5": {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": ["4", 0], "upscale_method": "lanczos",
              "megapixels": 1.0, "resolution_steps": 1}},
        "6": {"class_type": "VAEEncode", "inputs": {"pixels": ["5", 0], "vae": ["3", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["2", 0]}},
        "8": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["7", 0]}},
        "9": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["7", 0], "latent": ["6", 0]}},
        "10": {"class_type": "ReferenceLatent", "inputs": {"conditioning": ["8", 0], "latent": ["6", 0]}},
        "11": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": w, "height": h, "batch_size": 1}},
        "12": {"class_type": "Flux2Scheduler", "inputs": {"steps": 4, "width": w, "height": h}},
        "13": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "14": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "15": {"class_type": "CFGGuider", "inputs": {"model": ["1", 0], "positive": ["9", 0], "negative": ["10", 0],
               "cfg": 1.0}},
        "16": {"class_type": "SamplerCustomAdvanced", "inputs": {"noise": ["13", 0], "guider": ["15", 0],
               "sampler": ["14", 0], "sigmas": ["12", 0], "latent_image": ["11", 0]}},
        "17": {"class_type": "VAEDecode", "inputs": {"samples": ["16", 0], "vae": ["3", 0]}},
        "18": _save(prefix, ["17", 0]),
    }


def bw_finish(wf, image_ref, w, h, prefix, save_id="10"):
    """True greyscale (Rec.601 luma) from core mask nodes; Anima keeps famous outfits in spot colour otherwise."""
    for ch, k, n in (("red", 0.299, "40"), ("green", 0.587, "42"), ("blue", 0.114, "44")):
        wf[n] = {"class_type": "ImageToMask", "inputs": {"image": image_ref, "channel": ch}}
        wf[str(int(n) + 1)] = {"class_type": "SolidMask", "inputs": {"value": k, "width": w, "height": h}}
    wf["46"] = {"class_type": "MaskComposite", "inputs": {"destination": ["40", 0], "source": ["41", 0], "x": 0, "y": 0,
                "operation": "multiply"}}
    wf["47"] = {"class_type": "MaskComposite", "inputs": {"destination": ["42", 0], "source": ["43", 0], "x": 0, "y": 0,
                "operation": "multiply"}}
    wf["48"] = {"class_type": "MaskComposite", "inputs": {"destination": ["44", 0], "source": ["45", 0], "x": 0, "y": 0,
                "operation": "multiply"}}
    wf["49"] = {"class_type": "MaskComposite", "inputs": {"destination": ["46", 0], "source": ["47", 0], "x": 0, "y": 0,
                "operation": "add"}}
    wf["50"] = {"class_type": "MaskComposite", "inputs": {"destination": ["49", 0], "source": ["48", 0], "x": 0, "y": 0,
                "operation": "add"}}
    wf["51"] = {"class_type": "MaskToImage", "inputs": {"mask": ["50", 0]}}
    wf[save_id] = _save(prefix, ["51", 0])
    return wf


def klein9_refs(prompt, images, w, h, seed, prefix):
    """klein 9B with several reference pictures (image 1, image 2, ...) chained through ReferenceLatent."""
    wf = klein9_edit(prompt, images[0], w, h, seed, prefix)
    pos, neg = ["7", 0], ["8", 0]
    for i, img in enumerate(images):
        n = 60 + i * 5
        wf[str(n)] = {"class_type": "LoadImage", "inputs": {"image": img}}
        wf[str(n + 1)] = {"class_type": "ImageScaleToTotalPixels", "inputs": {"image": [str(n), 0],
                          "upscale_method": "lanczos", "megapixels": 1.0, "resolution_steps": 1}}
        wf[str(n + 2)] = {"class_type": "VAEEncode", "inputs": {"pixels": [str(n + 1), 0], "vae": ["3", 0]}}
        wf[str(n + 3)] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": pos, "latent": [str(n + 2), 0]}}
        wf[str(n + 4)] = {"class_type": "ReferenceLatent", "inputs": {"conditioning": neg, "latent": [str(n + 2), 0]}}
        pos, neg = [str(n + 3), 0], [str(n + 4), 0]
    for k in ("4", "5", "6", "9", "10"):
        del wf[k]
    wf["15"]["inputs"]["positive"] = pos
    wf["15"]["inputs"]["negative"] = neg
    return wf


def with_loras(wf, loras, base=("1", 0)):
    """Chain LoraLoaderModelOnly after the UNet; returns the model output ref. loras = [(file, strength), ...]."""
    ref = list(base)
    for i, (name, st) in enumerate(loras or []):
        n = str(80 + i)
        wf[n] = {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ref, "lora_name": name, "strength_model": st}}
        ref = [n, 0]
    return ref


def anima_control(prompt, control, w, h, seed, prefix, ctrl_strength=1.0, ctrl_end=0.6, ref=None, ip_strength=0.7,
                  loras=None, neg_extra=""):
    """Anima draws the frame itself (real manga linework); a finished picture (e.g. a klein frame) steers the
    layout through kohya's ControlNet-LLLite 'any-test like v2' (greyscale/lineart control), and a saved
    character picture steers identity through the Anima IP-Adapter (SigLIP2). Nodes pinned in comfyui/Dockerfile."""
    wf = anima(prompt, w, h, seed, prefix, NEG_BW + (", " + neg_extra if neg_extra else ""))
    model = with_loras(wf, loras)
    if control and ctrl_strength > 0:
        wf["30"] = {"class_type": "LoadImage", "inputs": {"image": control}}
        wf["31"] = {"class_type": "ImageScale", "inputs": {"image": ["30", 0], "upscale_method": "lanczos",
                    "width": w, "height": h, "crop": "center"}}
        wf["32"] = {"class_type": "AnimaLLLiteApply_sdscripts", "inputs": {
            "model": model, "lllite_name": "anima-lllite-any-test-like-v2.safetensors", "image": ["31", 0],
            "strength": ctrl_strength, "start_percent": 0.0, "end_percent": ctrl_end, "preserve_wrapper": True}}
        model = ["32", 0]
    if ref and ip_strength > 0:
        wf["33"] = {"class_type": "LoadImage", "inputs": {"image": ref}}
        wf["34"] = {"class_type": "AnimaIPAdapterLoader", "inputs": {
            "ip_adapter_name": "ip_adapter-Character_Reference-10.safetensors", "auto_download": False}}
        wf["35"] = {"class_type": "AnimaIPAdapterApply", "inputs": {
            "model": model, "ip_adapter": ["34", 0], "ref_image": ["33", 0], "strength": ip_strength,
            "ref_image_size": 512, "siglip_layer": -1, "ip_cfg_scale": 4.0, "ip_cfg_separate": False,
            "gray_null": False, "use_lora": True}}
        model = ["35", 0]
    wf["8"]["inputs"]["model"] = model
    return bw_finish(wf, ["9", 0], w, h, prefix)
