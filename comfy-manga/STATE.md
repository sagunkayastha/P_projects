# comfy-manga — STATE
Updated: 2026-10-25 23:30 (MDT) · by rem-mangafix (Claude, PC laanta-chy)

## Goal
Simple, mobile-first manga maker that runs fully locally (ComfyUI in Docker, GPU 0): chat -> pictures,
"Make character" from any picture, 4-panel pages. Original characters only (no Valve/Deadlock IP from 2026-10-24).

## Status
- Overall: active. New app live on :8289 since 2026-10-24 ~06:15 (branch manga-app, merged to main).
- Works (tested in Playwright mobile emulation, 360x780 touch, 40 checks + desktop 1280):
  - Chat: instant send (pending bubble), queued/running with step progress, Stop, Again, clear "Not sent · retry"
    on network errors (same ckey = no duplicate), sticky composer above the keyboard, no page reloads (long poll
    /api/wait), hashed assets (stale-JS bug fixed: ?v=<hash> immutable, index no-store), dark, 360-390 px first.
  - Everything on disk in ~/Documents/Personal/manga/app (700): app.db (SQLite) + images/ + thumbs/ +
    characters/<slug>/ + pages/page-NNNN/. Jobs survive app restart (re-attach by prompt_id) and ComfyUI restart
    (prompt sent again). Both tested mid-job.
  - Gallery (drawer -> Gallery): all pictures newest first, WebP thumbs (360 px, 1080 px "m"), infinite scroll;
    full-screen viewer: swipe, double-tap + pinch zoom, pan, download, back button closes. ram-backup-2026-10-24
    (417 PNG) is copied into the gallery on app start (read only, idempotent).
  - Make character (button on any picture): klein 9B edit of the picture, 28 views (8 angles x 3 faces + 4
    outfits, one seed), face check (custom ComfyUI node MangaRefScore: anime-face cascade + SigLIP2) drops
    drifted faces, keeps 4 outfits + 16 best angles = 20. ~3.5 min. Characters list with progress/Stop/Retry.
  - Make page: 1-2 characters + 4 lines -> 4 panels (klein 9B, 2 refs per named character; a panel gets only the
    characters its line names) -> page 1500x2250: top strip, right big + left narrow with slanted gutter, bottom
    strip, read right to left, speech bubbles from "quoted" text. Redo one panel re-composes. ~75 s per page.
    Panel prompts: local LLM only if a model is already loaded in the llama.cpp router, else template.
- Samsung tested 2026-10-25 (adb RZCR908FCPN on archbox): per-panel Edit/Redo works with ef7ee07.
- LIVE since 2026-10-25 (private mode): 73b82b3 = quality rounds + "order" panel prompt (line + shot first, short)
  + hands/object close-ups get detail-shot wording. Image sha256:4ca7c9da.
- Built + committed, test image only, NOT deployed (2418b93..4f14ceb):
  - Chat sketch upload (✎ Sketch chip): klein keeps the sketch layout, character sheets as extra refs.
  - Model chip in chat: klein (default) / Anima / Manga Vision (Anima-family, Civitai 3188880, SHA-256 checked).
    Prompt-only chat now uses klein t2i (was Anima).
  - Character set-up list before Make character (angles / faces / outfits, add own items, live count).
  - Panel Edit works while the page still draws (waiting panel takes the new line) — 72ab6a5.
  - UI checked in Playwright without GPU. 2026-10-26: test image rebuilt from 227999e, test app :8290 + comfyui-manga
    up; prompt-only drew fine with klein (~11 s), Anima (~20 s), Manga Vision (~19 s). Tests with the user running.
  - ✎ Modify on every chat picture (user ask via Rem): picture becomes the source (klein edit) + its prompt in the box.
    Checked at 360 px: prompt + source loaded, chip row fits (2 lines, nothing cut), edit 'give her glasses' kept layout.
  - 2026-10-26 Modify v2 (user yes to 3 fixes): own edit prompt (app.py EDIT/_edit_job, messages.edit column),
    modes Small change (default) / New picture, empty box with hint. Re-run of the user's cases
    (~/scratch/mangafix/modify/rerun.png): cyberpunk clothing OK, cyberpunk theme OK (background), long bob OK but
    hair turns light grey, front view fails in Small change but works in New picture (hint says so).
    New picture still copies the pose when the words name none (cafe test kept the sitting pose: new_cafe.png).
  - 2026-10-26 Modify model switch (klein / Qwen-Edit) in the Modify row; Qwen-Image-Edit 2511 GGUF Q4_K_M +
    Lightning 4-step (+ Multiple-Angles LoRA file, unused) + Qwen2.5-VL nvfp4 in models/; ComfyUI-GGUF in the
    comfyui image (old image tag local/comfyui-manga:cu130-pre-qwen-20261026). Result: klein stays default
    (~/scratch/mangafix/modify/MODELS-REPORT.md); Qwen 20-26 s vs klein 6-8 s. klein Character Consistency LoRA
    downloaded (models/loras), no gain, not used.
  - 2026-10-26 sketch test (~/scratch/mangafix/sketchtest/SKETCH-REPORT.md, sketch_models.png): klein stays default;
    Qwen-Edit equal but slower; Anima Scribble LoRA (grainy) and Qwen-Image 2.1 int8 + Fun ControlNet Union (copies
    or ignores the sketch) not added. Test-only paths in the app API: model "qwen" / "scribble" / "q21" with a sketch
    (no UI). Qwen 2.1 files (~18 GB) + scribble LoRA kept in models/ until the user decides.
  - 2026-10-26 A/B round r1 (~/scratch/mangafix/ab/r1/REPORT.md, TABLE.md): 96 Modify + 48 Sketch pictures, 3 judges.
    Sketch: klein best (all judges). Modify: near tie (Codex klein, Gemini Qwen); Qwen better for New-picture scene/
    action. Blind A/B page for the user: https://claude.ai/artifact/Msh9dySQ34EWfpAcGKz5Jv (picks in its db
    collection "picks"; key in r1/<round>/key.json: modify A=qwen B=klein, sketch A=qwen B=anima C=klein).
  - 2026-10-26 user picks -> defaults in the test build: sketch = Anima ("Manga look"; klein = "Exact layout"),
    Modify Small = klein, Modify New = Qwen-Edit (switch still there). Checked at 360 px.
  - 2026-10-26 colour mode in the test build: chat 'Look' chip B/W (default) / Colour / Cover (tall, title room at
    the top) / Chapter art (wide, title room at one side); messages.style; graphs.colourize drops the greyscale
    finish + swaps the style words (pages stay B/W). Qwen-Edit also in the main Model chip (text + character refs).
    Colour round c1 (6 cases x 2 seeds x klein/Qwen/Anima, ~/scratch/mangafix/ab/c1, key.json A=qwen B=klein
    C=anima); blind page https://claude.ai/artifact/4fJpZWJ7DaMUw22yCggUX1. Anima (both manga fine-tunes) stays B/W
    in colour mode, even with 'monochrome' in its negative.

## Next
0. 2026-10-26: PC rebooting into Windows. To resume the tests: `docker compose up -d comfyui` then
   `TEST_DATA=~/scratch/mangaapp/testdata docker compose -f docker-compose.test.yml up -d` (image local/comfymanga:test = 4c3c933).
   Live :8289 still down (not restarted; needs Rem's word).
1. GPU tests WITH the user (Rem: tomorrow, 2026-10-26), on the test app :8290 after rebuild: sketch -> picture
   with each model; prompt-only per model; Make character with an edited list (pictures match the list); Edit of
   a waiting panel. Then deploy only on the user's yes.
2. Finish round p2 scoring (needs judge-3060 + freed ComfyUI): `python3 tests/judge_views.py
   http://127.0.0.1:11500 $B/p2/views`, `python3 tests/judge_panels.py http://127.0.0.1:11500 $B/p2`; final table.
3. Backgrounds: plan the room layout once, draw views from it (both reviewers' advice after p2 views).
4. Ideas reported, not built: save the user's edited set-up list as their default; user-added outfits are not
   auto-picked as panel refs.
5. Older open points: over-the-shoulder still weakest; stray bubbles/sign text; shoes drift; Private / Continue
   choice at start.

## Blockers / waiting on
- GPU drawing tests wait for the user (2026-10-26). Deploy of 2418b93..4f14ceb waits for the user's yes.
- klein base 9B: HF account must accept the FLUX non-commercial licence (user's click; never fill forms for them).

## Decisions
- 2026-10-24: one app at / (chat, gallery, characters, page). Old /studio and /demo routes removed from app.py
  (code in git history; studio.py still used for the angle/outfit plan; store.py, routing.py, style.css,
  studio.html/js/css, demo.html are now unused, left in place).
- 2026-10-24: ComfyUI I/O over HTTP (/upload/image into input/studio = RAM, results via PreviewImage + /view);
  the app keeps the only lasting copy on disk.
- 2026-10-24: Anima chat negative adds swimsuit/bikini/lingerie/underwear/cleavage/text (it drifted to glamour
  shots on a plain prompt).
- 2026-10-25: model licences / training data are not a concern for these personal tests (user via Rem); UI keeps
  only practical notes per model.
- 2026-10-25: chat models = klein (edits, sketches, characters), Anima, Manga Vision (no character sets: they can't
  edit pictures). Anima + sketch = LLLite control; Anima + character = IP-Adapter.
- Character ranking: drifted = face sim < set median - 0.15; outfits always kept unless drifted (whole-picture
  similarity punishes new clothes). Heuristic; no real "other person" case seen yet in tests.

- 2026-10-24: phase B (angle-matched refs, trait list, source floor + best-of-2 views, review grid before
  save) ships behind MANGA_B (0 in docker-compose.yml) until measured; old behaviour when off.
- 2026-10-24: the app reaches the host only through manga-gpu (host/README.md): fixed verbs, SSH forced command,
  key in ~/.config/manga-gpu (never in git). The llama.cpp router listens on 127.0.0.1 only, so LLM calls are relayed.
- 2026-10-24: Director = chat with the local LLM, system prompt chat/director-skills.md (user copy in APP_DIR
  overrides); LLM up stops comfyui-manga (both need the 5070 Ti), LLM down starts it again.

## Gotchas / do-not
- RAM: ComfyUI with klein 9B ~12.7 GB; free it (POST :8288/free) before running a llama.cpp judge; stop at <4 GB.
- The user may be working in the PRIVATE session (RAM only): never restart/recreate manga-app or comfyui-manga,
  and never queue test jobs on comfyui-manga, without asking Rem. Test instances share comfyui-manga's queue
  (docker-compose.test.yml): for UI tests without GPU use the isolated setup (mock LLM, COMFY_URL=nowhere, see log).
- One ComfyUI stack on GPU 0 at a time: stop ../comfyui (comfyui + chat) before starting this one (klein fills 16 GB).
- Never delete in ~/Documents/Personal/manga. Never look at the user's own pictures (ram-backup, gallery):
  tests use the test instance with its own data (~/scratch/mangaapp/testdata).
- Rebuilding/restarting the app no longer loses jobs; restarting ComfyUI re-sends the running job.
- Live app runs with logging driver "none" (private): no server logs to debug from; reproduce on the test app.
- `pkill -f <pattern>` can match your own shell and kill it; use exact PIDs.
- Old work/out holds unclothed rejects from the studio era: never show or publish.

## Key paths & commands
- Rollback of the 2026-10-25 deploy: `docker tag local/comfymanga:pre-deploy-20261025b local/comfymanga:latest &&
  docker compose -f docker-compose.yml -f docker-compose.private.yml up -d --no-build --force-recreate app`.
- Deploy (private mode only, user's yes first): `docker compose -f docker-compose.yml -f docker-compose.private.yml
  up -d --build app`.
- Benches p2: tests/{panelset,viewset,bench_panels,bench_views,judge_panels,judge_views}.py; results
  ~/scratch/mangafix/testdata/bench/panels/{p2,p2hard,p2/views}/ (contact*.png, judge.json, codex/gemini json).
  VLM judge: container judge-3060 on 127.0.0.1:11500 (qwen3-vl-8b); run judges as plain `python3 tests/judge_*.py`.
- UI checks without GPU: ~/scratch/mangafix/pw/{sketch_ui,edit_ui}.py in local/pw-test:1.52; shots ~/scratch/mangafix/p2/ui/.
- Civitai key ~/.config/civitai/token (600); HF token ../comfyui/.hf_token. Never print either.
- Live: http://127.0.0.1:8289 (phone http://192.168.0.235:8289); ComfyUI :8288. `docker compose up -d` here.
- Test instance (:8290, own data): `docker build -t local/comfymanga:test chat && TEST_DATA=~/scratch/mangaapp/testdata
  docker compose -f docker-compose.test.yml up -d`; flows: `docker run --rm --network host --ipc=host -u 1000
  -v $PWD/tests:/t:ro -v <out>:/out local/pw-test:1.52 python /t/mobile_flows.py http://127.0.0.1:8290 /out`
  (local/pw-test:1.52 = playwright/python:v1.52.0-noble + pip playwright; Dockerfile in ~/scratch/mangaapp/pw).
- Rollback to the old app (images kept as tags):
  `docker compose stop app && docker tag local/comfymanga:pre-app-20261024 local/comfymanga:latest &&
  docker tag local/comfyui-manga:cu130-pre-app-20261024 local/comfyui-manga:cu130 &&
  git show 0300075:comfy-manga/docker-compose.yml > docker-compose.yml && docker compose up -d --no-build --force-recreate`
- manga-gpu: `manga-gpu status` on the host; log ~/.cache/manga-gpu/actions.log.
- Flows for this work: tests/fix_flows.py (page | review | director), tests/mock_llm.py, bench_consistency.py,
  bench_director.py. Shots: ~/scratch/mangafix/shots{A,D2,C}.
- Code (chat/): app.py (API), worker.py (job loop, characters, pages), db.py (SQLite + revision/long poll),
  comfy.py (ComfyUI client), graphs.py (graphs on workflows.py), layout.py (page + bubbles), writer.py (panel
  prompts), media.py (files, thumbs, import), static/{index.html,app.js,app.css}. ComfyUI node:
  comfyui/nodes/manga_score. Tests: tests/mobile_flows.py.
- Images: app local/comfymanga:latest; ComfyUI local/comfyui-manga:cu130 (+ opencv-headless 4.14.0.94, cascade
  nagadomi/lbpcascade_animeface@4433ab1). Models as before (models/, siglip2 used by the face check).
