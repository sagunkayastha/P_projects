# comfy-manga — STATE-LOG (newest first)

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
