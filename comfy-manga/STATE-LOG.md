# comfy-manga — STATE-LOG (newest first)


## 2026-10-24 (eve) — per-panel fix, chat tools, Director tab built; deploy waits on the user ⚠️ (rem-mangafix)
- Phase A (commit 0dc2e42): per-panel Redo/Edit (line + cast), versions kept + pickable, page re-composed;
  no-character sheet; user shot words beat default framing; letterbox trim; panel face check (MangaRefScore)
  with one auto-redo + warning; LLM writer spelling fix. Flow test with ComfyUI 12/15 (3 test bugs, fixed).
- Chat: Copy prompt / Edit / Try again (new or same seed), like the ComfyUI image chat. Cache: no-store for all
  but hashed assets; picture URLs carry a per-store key (fresh private store reuses ids -> phone showed old pictures).
- Phase B code (refs.py, traits, floors 0.85 face / 0.90 whole / 0.80 outfit, best-of-2, review grid) behind
  MANGA_B. B1 bench (6 lines x 2 seeds): Nori face-sim 0.929 -> 0.940 (faces found 6/12 vs 4/12), Bram no faces
  found (whole 0.850 vs 0.850): the anime face cascade misses most panels; better metric needed.
- Director (c63f417): chat + editable shot list + Send to Make page (+ scene bible field); manga-gpu host helper
  installed (symlink, key, authorized_keys line; backup authorized_keys.bak-20261024-mangagpu). Mock-LLM UI test 6/6.
- My test instance used the shared comfyui-manga while the user worked (slowed them); stopped on user order,
  as was the 8B director test on the 3060 (container had already exited). Image backup local/comfymanga:pre-fix-20261024b.

## 2026-10-24 06:10 — new mobile-first app: chat, gallery, characters, pages (rem-mangaapp, overnight)
- Rewrote chat/app.py around an on-disk SQLite job table + worker (re-attach after app restart, re-send after
  ComfyUI restart; both tested mid-job). All output in ~/Documents/Personal/manga/app.
- New UI (static/index.html, app.js, app.css): chat with pending/queued/running/progress, long poll, hashed assets;
  drawer; gallery with thumbs + infinite scroll; viewer (swipe/pinch/double-tap/pan/download/back).
- Make character: 28 klein edits -> face check node (first try: cascade file unreadable (ADD 600 root) -> --chmod;
  cascade found no faces at 896 px -> detect on a 384 px copy: 17/29) -> first ranking dropped all outfits
  (whole-picture similarity) -> outfits kept separately. Test characters Rin, Kai (own prompts).
- Make page: template prompts, 4 shaped panels RTL + bubbles; first test drew Rin twice in a Rin-only panel ->
  panels get only the characters they name. Page ~75 s, character ~230 s.
- Playwright mobile emulation: 40 checks (run 1: 36/40, test bugs; run 2: 39/40, test key reuse; final run see
  STATE). Screens: ~/scratch/mangaapp/shots{1,2,3}. No Samsung reachable (no USB device; .179:5555 = AT&T TV).
- Main ComfyUI stack (../comfyui) stopped for the night, restarted at the end.

## 2026-10-24 03:55 — 12 frames, ink refs, parked (rem-manga)
- Ink references via Civitai LoRAs Mangalike_Anima + Pearly Cross-hatching (user key) -> haze-ink, rem-ink.
- Gemini 12-shot list drawn: klein layouts (two-character wide shots dropped Rem until reworded) -> Anima + LLLite
  + LoRAs (+ IP-Adapter for Haze). 36 candidates + 6 redos; critic by me and Gemini (busty Haze, weak angles).
- New shapes: tall916, hstrip, vstrip; control endpoint takes loras, neg_extra, shape. /demo reworked.
- User: still not manga. Project parked for research.

## 2026-10-24 03:20 — Anima-drawn frames (rem-manga)
- Read + pinned 3 nodes (LLLite, IP-Adapter, Cosmos-Reference) into local/comfyui-manga:cu130; weights ~2 GB.
- Tests (same seed): IP-Adapter fixes Haze (hair/mask) but breaks Rem; control 1.0/end 0.6 keeps layout with Anima linework.
- Line 1 at control end 0.6 drew two nude women kissing (not shown); fixed with control 1.2 to the end + outfit tags
  + nudity/kiss negatives. Final F frames: jobs 247, 235, 256, 245. /demo shows F on top, old variants below.

## 2026-10-24 02:45 — restyle test, video prep, research (rem-manga)
- Frames restyle endpoint (/api/frames/<p>/<line>/restyle) + per-line variants and final; /demo shows final
  frames + comparison row (klein, A-E). E (klein + MangaScreen finish without Levels) won my test; user: "just
  added dots, not manga". Line 1 night street became mud under halftone.
- Voice clips from deadlock.wiki (4 mp3), whisper word timings; renderer written, video on hold.
- Research: Anima has IP-Adapter, ControlNet-RefLatents and ControlNet-LLLite; Illustrious Rem/Haze LoRAs exist.

## 2026-10-24 — phase 1: character studio, edit-model test, demo frames (rem-manga)
- Added Character studio (/studio): grid 16 -> keep -> more like this / inpaint -> save -> variation set -> frames.
  Studio data persistent under ~/Documents/Personal/manga (app runs as uid 1000, TZ America/Denver).
- Anima knows `haze (deadlock)` / `rem (deadlock)` well (on-model full body), but paints them in spot colour:
  fixed with a greyscale finish. Anima ~15-16 s per 896x1152 picture.
- klein 9B variation sets (27 each, 4 runs): identity + B/W 108/108, 4.4 s each; camera-move wording raised
  angles followed from ~11 to ~17 of 24; low angle never works. Qwen-Edit-2511 not downloaded (klein did not drift).
- Frames: Anima tag-only frames lost characters (and drew unclothed figures twice); klein 9B with saved character
  refs on-model in all 4 lines. Demo at /demo (lines 1-4 = klein jobs 153, 182, 168, 183).
- Phone bug: user saw no pictures — phone had cached an old studio.js; static now served no-store + version bump.
- User found the studio confusing (tapped 18 pictures = 18 keeps); notes for a simpler UI written.
