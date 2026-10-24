# comfy-manga — STATE
Updated: 2026-10-24 03:55 (MDT) · by rem-manga (Claude, PC laanta-chy)

## Goal
Manga pipeline in one small app (ComfyUI + Anima Manga, Docker, GPU 0): consistent characters -> frames ->
pages -> motion comic. Test story: Deadlock's Haze + Rem, "Not Your Mom" (Valve IP, private test, never publish).

## Status
- Overall: PARKED until next week (user 2026-10-24): frames still do not read as manga. Next step is proper
  research, not more generation. App left running (ComfyUI :8288, app :8289). No GPU work in progress.
- Works: Character studio (/studio, phone + desktop), saved characters on disk, variation sets, frames per script
  line with methods klein9 / anima / restyle / control, /demo view (12 frames, old vs new refs, earlier 4 + tests).
- Not done: motion-comic video (on hold; voice clips + word timings + renderer ready, never rendered).

## What was tried (results)
1. Anima Manga (beretMix v2.0) by tag: knows `haze (deadlock)` / `rem (deadlock)`, on-model full-body sheets, but
   paints spot colour (fixed with a true-greyscale finish). In close-ups/two-shots it loses the characters and twice
   drew unclothed figures.
2. FLUX.2 klein 9B edit with saved character pictures as refs: identity + B/W kept 108/108 in variation sets
   (4.4 s/pic), good compositions; camera low-angle never works. Frames look like a clean render, not manga.
3. Restyles of klein frames (/demo "earlier 4"): A Anima img2img 0.38 (keeps render lighting; 0.48 drifts),
   B A+MangaScreen, C strong ink prompt (whitens Haze's skin), D Manga-Lite (Levels whitens skin), E MangaScreen
   finish -> user: "just added dots". Filters on a render do not make manga.
4. F = Anima draws, klein frame only as layout (kohya ControlNet-LLLite any-test-v2, 1.0 to 60%; two-shots 1.2 to
   100%), Haze identity via Anima IP-Adapter (0.7; it breaks Rem, so off for him). Real Anima linework, faces OK.
   User: references themselves look smooth anime-cel, which carries into frames.
5. Ink references (haze-ink, rem-ink): Anima + Civitai LoRAs Mangalike_Anima (3319816) 1.0 + Pearly Cross-hatching
   (3407601) 1.0, sketch/ink/paper tags, flat-grey/cel negatives: more pen-like, still grey fills.
6. Gemini (agy-box) 12-frame shot list -> klein layouts from ink refs -> F method with both LoRAs: 12 frames on /demo.
   My critic: 3 redone (1 mirrored for screen direction, 2 wrong action, 6 strip came out full-body). Gemini critic:
   frames 1, 3, 5, 8 (Haze drawn very busty, off-model), 9, 10 fail. User: still not manga.
- Why it fails (my read): every frame starts from a model's idea of "anime illustration" (smooth shading, grey fills,
  glamour proportions); manga look needs real page grammar (spot blacks, screentone by meaning, hatching, panel
  composition) that neither prompts, LoRAs nor post filters gave. Anima also sexualises Haze unless pushed hard.

## Next
1. User/Rem: research first (what real AI-manga pipelines use: manga-trained checkpoints/LoRAs from real scans,
   lineart-first + tone pass, artist-style LoRAs, Qwen-Image-Edit "redraw as manga" (MangaScreen's QWEN-Manga path)).
2. Then: simpler studio UI (notes/studio-ui-notes.md), then the video.

## Blockers / waiting on
- User's research decision next week.

## Decisions
- 2026-10-24: Qwen-Image-Edit-2511 not downloaded (klein did not drift on variations); Qwen-Image 2.1 edit (MangaScreen
  QWEN-Manga) not tried.
- 2026-10-24: Haze is drawn per the wiki (mask band, messy bun, no hood) even where the shot list says hood/cloak.
- Studio Anima pictures get a greyscale finish; nudity/kiss terms are in the global B/W negative.

## Gotchas / do-not
- One ComfyUI stack on GPU 0 at a time (this or ../comfyui). klein 9B fills the 16 GB card.
- Never delete in ~/Documents/Personal/manga; "Remove from kept" only hides. work/out holds some unclothed rejects:
  never show or publish work/out. Two-shots need strong layout control to the end.
- IP-Adapter loader: keep auto_download OFF (encoder is local). Civitai key = ../comfyui/.civitai_token (never print).
- Rebuilding the app stops running studio jobs (queued ones are marked failed).
- Deadlock characters, voice clips and frames: Valve IP, private only.

## Key paths & commands
- App http://127.0.0.1:8289 (phone http://192.168.0.235:8289/studio, /demo, /demo?p=<project>); ComfyUI :8288.
- `docker compose up -d` / `docker compose stop` here; `docker compose up -d --build app` after chat/ edits.
- Images: app local/comfymanga:latest (chat/); ComfyUI local/comfyui-manga:cu130 (comfyui/Dockerfile = shared
  cu130 + pinned kohya-ss/ComfyUI-Anima-LLLite b7495bd, LuciferTC9527/ComfyUI-Anima_IP-Adapter 6b77cd0,
  Mirumo0u0/ComfyUI-Cosmos-Reference 6fd6b27).
- Models (models/, hardlinks from ../comfyui where shared): beretMixAnimaManga_v20, qwen_3_06b_base, qwen_image_vae,
  flux-2-klein-9b-nvfp4, qwen_3_8b_fp4mixed, flux2-vae; controlnet/anima-lllite-any-test-like-v2; ipadapter/
  ip_adapter-Character_Reference-10; siglip2/siglip2-base-patch16-512; loras/Mangalike_Anima, pearly_cross_hatching.
- Code: chat/app.py (routes, worker), studio.py (store, variation plan, frames), workflows.py (graphs), static/.
- Data (700): ~/Documents/Personal/manga/{characters,frames,work,notes,scripts,audio}; frames projects:
  deadlock-demo (4), deadlock-12 (12), refs; work/studio.db = job list.
- Notes: notes/variation-test.md, notes/studio-ui-notes.md; shot list scripts/shotlist-gemini-v1.md.
- Scratch (PC): ~/scratch/manga/{video (render.py, words.json), shot12 (klein/anima prompt scripts),
  mangascreen (finish.py), nodes (read copies)}.
