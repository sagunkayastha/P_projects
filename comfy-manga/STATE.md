# comfy-manga — STATE
Updated: 2026-10-24 02:45 (MDT) · by rem-manga (Claude, PC laanta-chy)

## Goal
Manga pipeline in one small app (ComfyUI + Anima Manga + klein 9B, Docker, GPU 0). Phase 1 = character studio
+ choosing the edit model for LoRA datasets. Later phases: LoRA training, frame studio, page editor.

## Status
- Overall: active — phase 1 done; demo frames made, but user says they do not look like manga (klein render +
  screentone dots). Video (motion comic) ON HOLD until Rem/user pick a new frame method.
- Pictures page `/` (unchanged), Character studio `/studio`, demo view `/demo`.
- Studio: grid of 16 (Anima, random seeds, B/W finish) -> tap = keep -> More like this (img2img, 0.30-0.55)
  / Inpaint (paint mask) -> Save as character (image + seed + prompt + settings + traits) -> variation set
  (27 = 8 angles x 3 expressions + 3 outfits, klein 9B, ~4.4 s each) -> Frames (one line per card, 4 candidates, pick).
- Saved characters: `haze`, `rem` (picked by Claude for the user), `haze-test`, `rem-test` (test copies).
- Edit model verdict: klein 9B (style + identity held in 108/108; low angle ignored). Qwen-Edit-2511 NOT downloaded.
- Studio jobs, results, kept pictures, characters and frames are on disk (not RAM) under ~/Documents/Personal/manga.
- Phone (390 px) + desktop checked by screenshot (Playwright in Docker).

## Next
0. Waiting on Rem/user: frame method. Proposal sent: Anima Manga draws the frame, identity/layout from
   Anima IP-Adapter + ControlNet-LLLite (outline/pose/tile) using the klein frame + saved characters.
   Video renderer ready (no GPU): ~/scratch/manga/video/render.py (voice clips + whisper word times in place).
1. User: look at /demo; say whether to fetch Qwen-Edit-2511 (~27.5 GB) for better camera angles.
2. Simpler studio UI (user found it confusing): one step per screen, tap = view, "This one" button
   — plan in ~/Documents/Personal/manga/notes/studio-ui-notes.md.
3. Phase 2: LoRA training on Anima (kohya sd-scripts `anima_train_network.py`, see research notes).

## Blockers / waiting on
- None.

## Decisions
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
- Some Anima frame candidates in work/out are unclothed figures (tag-only frames); never show/publish work/out.
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
- Models (hardlinks from ../comfyui/models): beretMixAnimaManga_v20, qwen_3_06b_base, qwen_image_vae,
  flux-2-klein-9b-nvfp4, qwen_3_8b_fp4mixed, flux2-vae.
