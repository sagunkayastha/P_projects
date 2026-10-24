# comfy-manga

Small, self-contained studio for manga illustrations: ComfyUI plus a one-page app, using the
**Anima Manga** model only.

## What is in here

```
models/            Anima Manga + its text encoder + VAE (hardlinked from ../comfyui, no extra disk)
chat/              the one-page app (FastAPI + static JS)
output/            nothing persistent: results are written into a RAM volume (output/manga)
prompts.txt        a few starting prompts, one per line
docker-compose.yml
```

Model files in use:

- `models/diffusion_models/beretMixAnimaManga_v20.safetensors`
- `models/text_encoders/qwen_3_06b_base.safetensors`
- `models/vae/qwen_image_vae.safetensors`
- studio edit model (FLUX.2 klein 9B): `flux-2-klein-9b-nvfp4`, `qwen_3_8b_fp4mixed`, `flux2-vae` (hardlinks)

Graph: 32 steps, cfg 4.0, `er_sde` / `beta`, prompt prefix `masterpiece, best quality, `.
Warm time on this PC: roughly 16 s per image at the sizes offered.

## Start / stop

```bash
cd ~/Others/P_projects/comfy-manga
docker compose up -d          # ComfyUI + app
docker compose down           # or: docker compose stop
```

- App: <http://127.0.0.1:8289> — home Wi-Fi (phone): <http://192.168.0.235:8289>
- ComfyUI: <http://127.0.0.1:8288> (localhost only, no auth)

Pages: `/` pictures, `/studio` character studio, `/demo` the picked frames of a script
(`/demo?p=<project>`).

The app has shape presets (wide 1344x768, square 1024x1024, tall 832x1216), a progress bar,
regenerate with a new or the same seed, download, and tap-to-enlarge.

## Notes

- The app image is `local/comfymanga:latest`, built from `chat/`:
  `docker compose build app` after editing the app.
- Pictures page: results and prompt history live in RAM; they are gone when the containers stop.
- Character studio: everything (job list, results, kept pictures, characters, variation sets, frames) is on
  disk in `~/Documents/Personal/manga` (mode 700), mounted into the app. See STATE.md.
- Both stacks use GPU 0. Run this one or the main `comfyui` stack at a time on the 16 GB card.
- Ports 8288/8289 were chosen so this stack can sit next to the main one (8188/8189).
