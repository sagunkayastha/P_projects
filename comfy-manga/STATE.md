# comfy-manga — STATE
Updated: 2026-10-24 23:30 (MDT) · by rem-mangafix (Claude, PC laanta-chy)

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
- Not tested on the real Samsung: no phone on USB/adb. (192.168.0.179:5555 = AT&T TV box, left alone.)

## Next
1. Deploy everything together after the user's discussion of the continuity research (Rem):
   `docker compose -f docker-compose.yml -f docker-compose.private.yml up -d --build app`; decide MANGA_B /
   MANGA_CONT (both default on in code; MANGA_B=0 in docker-compose.yml today).
2. Open points: close-ups come out medium; shoes drift with upper-body sheets (put shoes in Looks); Director model
   choice (qwen36 switch mode recommended; 8B on the 3060 needs a router preset with device=CUDA1 = models.ini change).
3. Phone test on the Samsung (ask Rem first). Private / Continue choice at start (not built).

## Blockers / waiting on
- User's discussion of the research + go for the deploy.

## Decisions
- 2026-10-24: one app at / (chat, gallery, characters, page). Old /studio and /demo routes removed from app.py
  (code in git history; studio.py still used for the angle/outfit plan; store.py, routing.py, style.css,
  studio.html/js/css, demo.html are now unused, left in place).
- 2026-10-24: ComfyUI I/O over HTTP (/upload/image into input/studio = RAM, results via PreviewImage + /view);
  the app keeps the only lasting copy on disk.
- 2026-10-24: Anima chat negative adds swimsuit/bikini/lingerie/underwear/cleavage/text (it drifted to glamour
  shots on a plain prompt).
- Character ranking: drifted = face sim < set median - 0.15; outfits always kept unless drifted (whole-picture
  similarity punishes new clothes). Heuristic; no real "other person" case seen yet in tests.

- 2026-10-24: phase B (angle-matched refs, trait list, source floor + best-of-2 views, review grid before
  save) ships behind MANGA_B (0 in docker-compose.yml) until measured; old behaviour when off.
- 2026-10-24: the app reaches the host only through manga-gpu (host/README.md): fixed verbs, SSH forced command,
  key in ~/.config/manga-gpu (never in git). The llama.cpp router listens on 127.0.0.1 only, so LLM calls are relayed.
- 2026-10-24: Director = chat with the local LLM, system prompt chat/director-skills.md (user copy in APP_DIR
  overrides); LLM up stops comfyui-manga (both need the 5070 Ti), LLM down starts it again.

## Gotchas / do-not
- The user may be working in the PRIVATE session (RAM only): never restart/recreate manga-app or comfyui-manga,
  and never queue test jobs on comfyui-manga, without asking Rem. Test instances share comfyui-manga's queue
  (docker-compose.test.yml): for UI tests without GPU use the isolated setup (mock LLM, COMFY_URL=nowhere, see log).
- One ComfyUI stack on GPU 0 at a time: stop ../comfyui (comfyui + chat) before starting this one (klein fills 16 GB).
- Never delete in ~/Documents/Personal/manga. Never look at the user's own pictures (ram-backup, gallery):
  tests use the test instance with its own data (~/scratch/mangaapp/testdata).
- Rebuilding/restarting the app no longer loses jobs; restarting ComfyUI re-sends the running job.
- Old work/out holds unclothed rejects from the studio era: never show or publish.

## Key paths & commands
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
