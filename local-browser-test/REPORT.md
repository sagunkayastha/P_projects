# Local model + browser test (2026-10-28)

Model `ornith` (Ornith-1.5-35B-A3B Q4_K_M) on the PC's llama.cpp router, driven by **opencode 2.1.4**,
using the **chrome-devtools-mcp 1.11.0** browser tools. Browser = a visible Google Chrome window on the PC
desktop with a throw-away profile (`chrome-profile/` in this folder), so the user could watch live.

## Result: ornith 4/4 tasks correct

| Task | Result | Time | Steps (model turns) | Tool calls (errors) | What went wrong |
|---|---|---|---|---|---|
| 1. BBC News top 3 headlines | PASS (exact, checked against the page) | 50 s | 6 | 6 (0) | Nothing. Tried once to save a snapshot to a path outside the allowed folder, then just read it inline. |
| 2. Wikipedia search "Pollen", first paragraph | PASS (verbatim match) | 62 s | 12 | 11 (0) | 4 calls wasted finding the tool list (`search()` without `await`). Used the search box + Enter as asked. |
| 3. Fill httpbin pizza form, do NOT submit | PASS (all 7 fields right, never submitted: page stayed on `/forms/post`, no POST) | 129 s | 22 | 21 (2) | Time field: `fill` with "7" first, then set `19:30` by JavaScript (works). 2 errors = it tried to Read its screenshot, which was root-owned (my setup, fixed after). Wrong excuse in its answer about the screenshot path (harmless). |
| 4. Raspberry Pi 5 8GB price, Adafruit vs PiShop | PASS with caveat: both prices right ($200.00 vs $175.00, PiShop $25 cheaper), both URLs right | 160 s | 23 | 22 (0) | Adafruit: used site search, then product page. PiShop: guessed 2 wrong search URLs, found the search box but never used it, then **typed the product URL from a guess** (it happened to be right). Read-only: no cart, no login. |

Totals: 401 s for the 4 tasks, 63 model turns, 0 hard failures. Facts were checked by me against the live pages
(curl / Wikipedia API) right after each run.

Compared with the earlier test (2026-10-09, Playwright MCP, HN task): `gpt-oss-20b` failed (never looked at the
page, guessed selectors, ran out of context). ornith does the opposite: it looks first (`take_snapshot`) and
then reads with small JavaScript snippets, and it recovers from dead ends.

Other notes:
- opencode 2.x does not call MCP tools directly: the model writes small JS in opencode's `execute` tool
  (`await tools.cdt.navigate_page(...)`). ornith handled that well; the only stumbles were forgetting `await`.
- One run (task 4, first try) hung for 10 min before the first model request: the MCP server was up and had
  answered, opencode never sent the prompt. Killed it; the retry worked at once. Cause not found
  (`opencode run --standalone`; maybe a one-off). Watch for it.
- Speed: the time is mostly the model thinking between steps (~5-7 s per turn); page loads are quick.

## Extra task (user request): eBay, refurbished Sony WH-1000XM6 (ornith)

PASS, slow. 590 s, 44 steps, 43 tool calls, 0 errors. Watched live by the user in the test Chrome.
- Used eBay's search box, then ticked all 4 refurbished conditions (Certified / Excellent / Very Good / Good).
- Answer: 5 cheapest XM6 headphones, refurbished: $233.99 (Good, Midnight Blue), $239.99 (Very Good, Black),
  $239.99 (Very Good, Midnight Blue), $254.99 (Excellent, Platinum Silver), $259.99 (Very Good, Sandstone), all free
  delivery. Checked against the live results page afterwards: all 5 listings, ids, prices and conditions match,
  and they are the only XM6 headphones on that page. It correctly left out XM5/XM4 and the WF-1000XM6 earbuds.
- What was slow: ~20 of the 43 calls were it fighting the format of `evaluate_script` results (wrote an `unwrap()`
  helper and rewrote it ~15 times), plus one reload because the first eBay load was not ready.
- Read-only: no login, cart, watchlist or bid.
- Video: `shots/t5-ebay-ornith.mp4` (98 s, sped up ~6x). Transcript `runs/ornith/t5-ebay.jsonl`.

## ornith-q6 (extra, 2 tasks)

Not tested: `ornith-q6` **failed to load** both times (`cudaMalloc failed: out of memory` on CUDA0,
~860 MB short; router log). Its layout in `models.ini` is fixed and leaves no slack, and the desktop plus the
visible test Chrome held extra VRAM. Each attempt burned ~10 min because opencode retried the 500 error 11 times
before giving up (runs `runs/ornith-q6/`). To try it: close GPU-heavy apps first, or loosen its layout in
`models.ini` (not done here: out of scope).

## Evidence

- Video of task 3 (form fill, ornith, 32 s, 2 frames/s played at 8 fps): `shots/t3-form-ornith.mp4`
- Screenshot the model took itself after filling the form: `shots/t3-filled-ornith.png`
- Raw frames per run: `shots/frames-<model>-<task>/` (JPEG every 0.5 s from the test Chrome)
- Full transcripts (opencode JSON events): `runs/<model>/<task>.jsonl`; short summaries `runs/<model>/<task>.summary.txt`

## How to repeat

```bash
cd ~/Others/P_projects/local-browser-test
llm-up                                                     # llama.cpp router on 127.0.0.1:11434
docker build -t local-browser-test/cdt-mcp:1.11.0 docker/  # chrome-devtools-mcp + Node 22 (once)

# visible throw-away Chrome on the desktop (from a terminal in the KDE session; env from plasmashell otherwise)
kstart -- google-chrome-stable --user-data-dir=$PWD/chrome-profile --remote-debugging-port=9333 \
  --remote-debugging-address=127.0.0.1 --no-first-run --no-default-browser-check --disable-sync \
  --window-size=1280,900 about:blank

bin/run_task.sh ornith t1-news       # task ids in tasks.json: t1-news t2-wiki t3-form t4-price
bin/run_task.sh ornith-q6 t3-form    # any pc/<id> model from models.ini
# make a video from a run's frames:
ffmpeg -framerate 8 -pattern_type glob -i 'shots/frames-ornith-t3-form/*.jpg' -vf "scale=1280:-2,format=yuv420p" shots/out.mp4
```

How it is wired:
- `opencode.json` here is a **project-local** config (the user's main `~/.config/opencode/opencode.jsonc` is
  untouched; its `pc` provider and lean-local plugin are still used). It adds one MCP server `cdt`:
  `docker run -i --rm --network host local-browser-test/cdt-mcp:1.11.0 --browserUrl http://127.0.0.1:9333`,
  and denies bash/edit/webfetch/websearch so the model can only use the browser.
- `bin/run_task.sh` closes extra tabs, starts a frame recorder container (`docker/record.mjs`, CDP screenshots),
  runs `opencode run --standalone -m pc/<model> --format json "<task>"`, then prints time/steps/tool calls
  (`bin/summ.py`).
- For a headless run with no window instead: drop `--browserUrl` and use the image's default entrypoint
  (`--headless --isolated`, Chromium inside the container).

Cleanup when done with it: `chrome-profile/` (throw-away Chrome profile) and `shots/frames-*` can be deleted;
image `local-browser-test/cdt-mcp:1.11.0` (1.4 GB) can be removed with `docker rmi`.
