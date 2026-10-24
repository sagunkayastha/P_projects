# comfy-manga — STATE
Updated: 2026-10-24 03:20 (MDT) · by rem-manga (Claude, PC laanta-chy)

## Goal
Manga pipeline in one small app (ComfyUI + Anima Manga + klein 9B, Docker, GPU 0). Phase 1 = character studio
+ choosing the edit model for LoRA datasets. Later phases: LoRA training, frame studio, page editor.

## Status
- Overall: active — phase 1 done; demo frames remade as F (Anima draws, klein layout via LLLite, Haze via IP-Adapter),
  waiting for the user's OK. Video (motion comic) ON HOLD until then.
- Pictures page `/` (unchanged), Character studio `/studio`, demo view `/demo`.
- Studio: grid of 16 (Anima, random seeds, B/W finish) -> tap = keep -> More like this (img2img, 0.30-0.55)
  / Inpaint (paint mask) -> Save as character (image + seed + prompt + settings + traits) -> variation set
  (27 = 8 angles x 3 expressions + 3 outfits, klein 9B, ~4.4 s each) -> Frames (one line per card, 4 candidates, pick).
- Saved characters: `haze`, `rem` (picked by Claude for the user), `haze-test`, `rem-test` (test copies).
- Edit model verdict: klein 9B (style + identity held in 108/108; low angle ignored). Qwen-Edit-2511 NOT downloaded.
- Studio jobs, results, kept pictures, characters and frames are on disk (not RAM) under ~/Documents/Personal/manga.
- Phone (390 px) + desktop checked by screenshot (Playwright in Docker).

## Next
0. Waiting on user OK of the F frames on /demo; then render the video from the final frames
   (~/scratch/manga/video/render.py reads line-0N-e.png names: point it at the "final" refs first).
1. User: look at /demo; say whether to fetch Qwen-Edit-2511 (~27.5 GB) for better camera angles.
2. Simpler studio UI (user found it confusing): one step per screen, tap = view, "This one" button
   — plan in ~/Documents/Personal/manga/notes/studio-ui-notes.md.
3. Phase 2: LoRA training on Anima (kohya sd-scripts `anima_train_network.py`, see research notes).

## Blockers / waiting on
- None.

## Decisions
- 2026-10-24: frames = method "control": Anima Manga + kohya ControlNet-LLLite any-test-like-v2 (klein frame as
  greyscale control, strength 1.0, end 0.6; two-shots 1.2/1.0) + Anima IP-Adapter Character_Reference at 0.7
  for Haze only (off for Rem: it turns him into a cat with pupils). Endpoint /api/frames/<p>/<line>/control.
- 2026-10-24: restyle test on /demo (A Anima redraw, B A+MangaScreen, C strong klein prompt, D Manga-Lite,
  E klein+MangaScreen finish): E picked by Claude, user rejected all as "just added dots". Filters do not fix it.
- 2026-10-24: klein 9B for variation sets and for frames with characters (refs = saved character pictures);
  Anima tags alone lose characters in close-ups.
- 2026-10-24: every studio Anima picture gets a true-greyscale finish (core mask nodes); Anima otherwise keeps
  famous outfits in spot colour even with "monochrome" + colour words in the negative.
- 2026-10-24: variation prompts use camera-move wording ("Rotate the camera 45 degrees…"): angles followed 12->18/24.

## Gotchas / do-not
- One ComfyUI stack on GPU 0 at a time (this one or ../comfyui). klein 9B fills the 16 GB card; the app frees
  VRAM when it switches model family.
- Never delete in ~/Documents/Personal/manga; "Remove from kept" only hides (hidden=true in the .json).
- Some Anima frame candidates in work/out are unclothed figures (tag-only frames, and a weak-control two-shot);
  never show/publish work/out. Two-shots need strong control to the end.
- Deadlock characters are Valve IP: private test only.
- Rebuild the app after editing chat/: `docker compose up -d --build app` (stops running studio jobs).

## Key paths & commands
- App: http://127.0.0.1:8289 · phone http://192.168.0.235:8289/studio · /demo · ComfyUI :8288 (localhost).
- `docker compose up -d` / `docker compose stop` in this folder.
- Code: chat/app.py (routes, worker), chat/studio.py (studio store, variation plan, frames), chat/workflows.py,
  chat/static/studio.{html,js,css}, demo.html.
- Data (mode 700): ~/Documents/Personal/manga/{characters,frames,work,notes,scripts}; work/studio.db = job list.
- Notes: ~/Documents/Personal/manga/notes/variation-test.md, studio-ui-notes.md.
- Voice clips (Valve, private): ~/Documents/Personal/manga/audio/*.mp3 (deadlock.wiki); word times
  ~/scratch/manga/video/words.json (faster-whisper small.en in Docker image fwhisper).
- MangaScreen (MIT, commit d0eb8dc) runs standalone: ~/scratch/manga/mangascreen/finish.py in image mscreen.
- ComfyUI image local/comfyui-manga:cu130 = local/comfyui:cu130 + pinned nodes (comfyui/Dockerfile):
  kohya-ss/ComfyUI-Anima-LLLite b7495bd, LuciferTC9527/ComfyUI-Anima_IP-Adapter 6b77cd0, Mirumo0u0/ComfyUI-Cosmos-Reference 6fd6b27.
  Weights: models/controlnet/anima-lllite-any-test-like-v2, models/ipadapter/ip_adapter-Character_Reference-10,
  models/siglip2/siglip2-base-patch16-512 (google). Keep the IP loader's auto_download OFF.
- Models (hardlinks from ../comfyui/models): beretMixAnimaManga_v20, qwen_3_06b_base, qwen_image_vae,
  flux-2-klein-9b-nvfp4, qwen_3_8b_fp4mixed, flux2-vae.
