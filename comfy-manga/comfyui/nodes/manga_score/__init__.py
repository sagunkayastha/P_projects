"""MangaRefScore: how close each candidate picture is to a reference character picture.

Anime-face detector (nagadomi lbpcascade_animeface, OpenCV) crops the face; SigLIP2 (models/siglip2,
already used by the Anima IP-Adapter) embeds face crop + whole picture; score = cosine similarity
of face crops (when both have a detectable face) and of whole pictures; the app ranks them.
Output: ui {"scores": [json string]} so the app reads it from /history. Model is unloaded after each run.
"""
import json
import os

import numpy as np
import torch
from PIL import Image

import folder_paths

HERE = os.path.dirname(os.path.abspath(__file__))
SIGLIP = os.path.join(folder_paths.models_dir, "siglip2", "siglip2-base-patch16-512")


def _face(img, cascade):
    import cv2
    if cascade is None or cascade.empty():
        return None
    # the cascade is trained on small faces: detect on a 384 px wide copy, then scale the box back
    k = 384 / img.width
    small = img.convert("RGB").resize((384, max(1, round(img.height * k))), Image.LANCZOS)
    g = cv2.equalizeHist(cv2.cvtColor(np.array(small), cv2.COLOR_RGB2GRAY))
    faces = cascade.detectMultiScale(g, scaleFactor=1.05, minNeighbors=4, minSize=(24, 24))
    if len(faces) == 0:
        return None
    faces = [[v / k for v in f] for f in faces]
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    cx, cy, s = x + w / 2, y + h / 2, max(w, h) * 1.5
    box = (int(max(0, cx - s / 2)), int(max(0, cy - s / 2)), int(min(img.width, cx + s / 2)),
           int(min(img.height, cy + s / 2)))
    return img.crop(box)


def _pix(imgs):
    arr = [np.asarray(i.convert("RGB").resize((512, 512), Image.BICUBIC), dtype=np.float32) / 255.0 for i in imgs]
    t = torch.from_numpy(np.stack(arr)).permute(0, 3, 1, 2)
    return (t - 0.5) / 0.5


class MangaRefScore:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"reference": ("STRING", {"default": ""}),
                             "candidates": ("STRING", {"default": "", "multiline": True})}}

    RETURN_TYPES = ()
    FUNCTION = "run"
    OUTPUT_NODE = True
    CATEGORY = "manga"

    def run(self, reference, candidates):
        import cv2
        from transformers import SiglipVisionModel
        cascade = cv2.CascadeClassifier(os.path.join(HERE, "lbpcascade_animeface.xml"))
        names = [c.strip() for c in candidates.splitlines() if c.strip()]
        load = lambda n: Image.open(folder_paths.get_annotated_filepath(n)).convert("RGB")
        ref = load(reference)
        cands = [load(n) for n in names]
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        model = SiglipVisionModel.from_pretrained(SIGLIP, torch_dtype=torch.float16).to(dev).eval()
        try:
            @torch.no_grad()
            def emb(imgs):
                out = []
                for i in range(0, len(imgs), 8):
                    v = model(pixel_values=_pix(imgs[i:i + 8]).to(dev, torch.float16)).pooler_output.float()
                    out.append(torch.nn.functional.normalize(v, dim=-1).cpu())
                return torch.cat(out)
            rf = _face(ref, cascade)
            whole = emb([ref] + cands)
            faces = [_face(c, cascade) for c in cands]
            face_idx = [i for i, f in enumerate(faces) if f is not None]
            fe = emb([rf] + [faces[i] for i in face_idx]) if rf is not None and face_idx else None
            res = []
            for i, n in enumerate(names):
                w_sim = float(whole[0] @ whole[i + 1])
                if fe is not None and i in face_idx:
                    f_sim, has = round(float(fe[0] @ fe[face_idx.index(i) + 1]), 4), True
                else:
                    f_sim, has = None, False
                res.append({"name": n, "face": has, "face_sim": f_sim, "whole_sim": round(w_sim, 4)})
        finally:
            del model
            torch.cuda.empty_cache()
        return {"ui": {"scores": [json.dumps({"ref_face": rf is not None, "items": res})]}}


NODE_CLASS_MAPPINGS = {"MangaRefScore": MangaRefScore}
