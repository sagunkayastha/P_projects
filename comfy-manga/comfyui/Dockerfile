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
