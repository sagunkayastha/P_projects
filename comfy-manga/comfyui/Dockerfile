# ComfyUI for comfy-manga = the shared local/comfyui:cu130 image + three Anima nodes, each pinned to a commit
# whose code was read before use (2026-10-24). Weights live in ../models (controlnet/, ipadapter/, siglip2/).
FROM local/comfyui:cu130
WORKDIR /app/ComfyUI/custom_nodes
# kohya-ss: ControlNet-LLLite for Anima (Apache-2.0)
RUN git clone -q https://github.com/kohya-ss/ComfyUI-Anima-LLLite && \
    git -C ComfyUI-Anima-LLLite checkout -q b7495bd8eb876e334509976896702484ed19cdbb
# LuciferTC9527: Anima IP-Adapter, SigLIP2 (Apache-2.0 code; keep auto_download off, encoder is in models/siglip2)
RUN git clone -q https://github.com/LuciferTC9527/ComfyUI-Anima_IP-Adapter && \
    git -C ComfyUI-Anima_IP-Adapter checkout -q 6b77cd0c367d76402174ace2be50d3cb6aa77855
# Mirumo0u0: reference latent for Cosmos/Anima (Apache-2.0)
RUN git clone -q https://github.com/Mirumo0u0/ComfyUI-Cosmos-Reference && \
    git -C ComfyUI-Cosmos-Reference checkout -q 6fd6b27e7c72847d69ad74f4c9cb68ce91b319df
WORKDIR /app/ComfyUI
# manga app (2026-10-24): face-similarity check for character sets. OpenCV headless (no deps: numpy is already in
# the image) + nagadomi's anime-face cascade (MIT), pinned commit; node code in nodes/manga_score.
RUN pip install --no-cache-dir --no-deps opencv-python-headless==4.14.0.94
COPY --chmod=755 nodes/manga_score /app/ComfyUI/custom_nodes/manga_score
ADD --chmod=644 https://raw.githubusercontent.com/nagadomi/lbpcascade_animeface/4433ab1ae1166ea75acfe99eb0f18709dac329a0/lbpcascade_animeface.xml /app/ComfyUI/custom_nodes/manga_score/lbpcascade_animeface.xml
# 2026-10-26: Qwen-Image-Edit 2511 as GGUF Q4_K_M (fits 16 GB). city96 ComfyUI-GGUF (Apache-2.0), pinned commit,
# code read before use (no network/subprocess); gguf reader lib pinned, no deps (numpy/pyyaml/tqdm already in the image).
RUN pip install --no-cache-dir --no-deps gguf==0.17.1 && \
    git clone -q https://github.com/city96/ComfyUI-GGUF custom_nodes/ComfyUI-GGUF && \
    git -C custom_nodes/ComfyUI-GGUF checkout -q 6ea2651e7df66d7585f6ffee804b20e92fb38b8a
