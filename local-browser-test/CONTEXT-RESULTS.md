# Context tuning: results (2026-10-28)

Changes from CONTEXT-RESEARCH.md applied to ornith (and qwen36), measured on the eBay task
("5 cheapest refurbished Sony WH-1000XM6", read-only), plus tasks 1-2 as a quick check.
One run per cell, so expect noise of about ±30%. Correct answer checked against the live eBay page:
cheapest = $233.99 (Good), $239.99 x2 (Very Good), $251.00, $254.99 (Excellent).

## Result in short

- Re-processing was **not** the bottleneck: at most 1 full re-process per run, prompt reading 46-92 s per run.
  The cost is generated tokens (thinking + text): 18k-66k per run at ~85-96 tok/s.
- The **chat page** solves the eBay task well both before and after (3.5-4 min, correct). opencode is much
  slower and less reliable on it (10-15 min): its code-mode wrapper makes the model fight result formats.
- Change (d) (opencode context 65k, keep 8k) **hurt**: it triggered a compaction at step 48 whose summary lost
  the task, and the model wandered off (closed the test Chrome, read our docs). Reverted.
- Tasks 1-2 still pass and got faster (29 s and 34 s, were 50 s and 62 s).

## eBay task

| Harness / run | Result | Time | Steps (model calls) | Generated tokens | Prompt tokens read (time) | Full re-process | Peak context |
|---|---|---|---|---|---|---|---|
| opencode, earlier today (before any tuning) | PASS | 590 s | 44 | 38.8k | n/a | n/a | 93k |
| opencode BEFORE (baseline) | FAIL: 15-min timeout, no answer | 900 s | 65 | 62.7k | 108.6k (92 s) | 1 | 111k |
| opencode AFTER, run 1 | WRONG: filtered Certified only, said all 4 grades, cheapest $269.99 | 573 s | 47 | 50.0k | 64.5k (53 s) | 1 | 48k |
| opencode AFTER, run 2 | FAIL: compaction at step 48 lost the task, wandered | 792 s | 102 | 66.1k | 91.9k (78 s) | 1 | 49k |
| opencode AFTER, run 3 (d reverted) | opencode hang (no requests sent; known opencode issue) | - | 0 | 0 | - | - | - |
| chat page BEFORE | PASS (all 5 right) | 211 s | 17 | 18.1k | 59.9k (46 s) | 0 | - |
| chat page AFTER | PASS (all 5 right) | 246 s | 32 | 21.1k | 75.5k (60 s) | 0 | - |

Quick check, opencode AFTER: task 1 BBC headlines PASS 29 s / 8 steps; task 2 Wikipedia PASS 34 s / 9 steps.

## What changed (and what stays)

| # | Change | Where | Status |
|---|---|---|---|
| a | Tool output cap 300 lines / 8 KB | test `opencode.json` (`tool_output`) | kept (test config only) |
| a | chrome-devtools tool list 32 -> 24 (performance, network, emulation, memory off; debugging must stay: it holds take_snapshot / evaluate_script) | test `opencode.json`, `bin/chat-mcp-up.sh` | kept |
| a | 16k-character cut on tool results for the chat page | `docker/trim.mjs` | kept (unchanged) |
| b | `checkpoint-min-step = 1024` (was 8192). ctx-checkpoints 32 and cache-ram 8192 are already the defaults | `models.ini` `[*]` | kept |
| c | `reasoning-budget = 2048` + `reasoning-budget-message = Enough thinking; act now.` | `models.ini` `[ornith]`, `[qwen36]` | kept. Fired only 3 times in 30 min; no clear gain |
| c | preserve thinking | nothing to do: ornith's template supports it and this build turns it on by default (log: "preserve_reasoning kwarg: true") | - |
| d | opencode `limit.context 65536`, `compaction.keep.tokens 8000` | test `opencode.json` | **reverted** (caused the derail) |
| e | stable prompt start | checked: cache hits step to step; the date only changes at midnight. No change | - |
| f | `swa-full = true` | `models.ini` `[gpt-oss-20b]` | kept (load checked in the llama.cpp update) |
| - | test config: file read/glob/grep/list denied (browser only) | test `opencode.json` | kept |

The user's main `~/.config/opencode/opencode.jsonc` and `lean-local.mjs` are **unchanged** (backed up anyway).

## Roll back

```bash
cd ~/Others/Gemma/llamacpp
cp models.ini.bak-20261028-1651 models.ini && docker compose restart llm      # router settings
cd ~/Others/P_projects/local-browser-test
cp opencode.json.bak-20261028-1651 opencode.json                              # test opencode config
git checkout 2c20070 -- bin/chat-mcp-up.sh                                    # bridge tool list
```
Backups of the untouched files: `compose.yaml.bak-20261028-1651`, `~/.config/opencode/opencode.jsonc.bak-20261028-1651`,
`~/.config/opencode/plugins-own/lean-local.mjs.bak-20261028-1651`.

## How it was measured

`RUNTAG=<tag> LIVE=1 bin/run_task.sh ornith t5-ebay` (Konsole live view `bin/live.py`; `bin/summ.py` reads opencode's
token counts; `bin/logstats.py` counts router log events: prompt tokens read, generated tokens, "forcing full prompt
re-processing", checkpoint restores). Chat page: the same prompt typed into the visible chat window (`docker/cdp.mjs`),
router log for the same time slice. Raw: `runs/ornith-base/`, `runs/ornith-after/` (run1/run2 files), `runs/chat-*-ebay.txt`.
