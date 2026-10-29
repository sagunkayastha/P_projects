# Browser tool in the llama.cpp chat page

The router's own chat page (http://127.0.0.1:11434) can drive a visible throw-away Chrome through
chrome-devtools-mcp. Set up 2026-10-28.

## On / off

Part of `llm-up` / `llm-down` since 2026-10-28:

```bash
llm-up      # router + browser tool (2 windows), prints the CHAT and BROWSER addresses
llm-down    # stops the browser tool (closes both windows) and the router
LLM_NO_BROWSER=1 llm-up                                    # router only, no windows
~/Others/P_projects/local-browser-test/bin/chat-mcp-up.sh  # browser tool alone (router already up)
~/Others/P_projects/local-browser-test/bin/chat-mcp-down.sh
```

If the browser tool fails to start, `llm-up` still brings the model up and prints one `WARN` line.
Both addresses are bound to 127.0.0.1: they work on the PC only. Running `llm-up` again keeps a running
bridge (restarting it would drop the chat page's connection).

`chat-mcp-up.sh` opens two Chrome windows, each with its own throw-away profile in this folder
(never your own Chrome or logins):

1. **Chat window** (`chat-ui-profile/`, opens on http://127.0.0.1:11434): already set up with the
   browser tool and the browsing system prompt. Pick **ornith** in the model menu, ask a web question.
2. **Test Chrome** (`chrome-profile/`, blank page): the window the model drives. Watch this one.

If you close the test Chrome while the chat window is open, the next tool call fails with
"fetch failed ... 127.0.0.1:9333". Run `chat-mcp-up.sh` again, then reload the chat page.

## Use it from your own browser instead

Settings live in each browser's local storage, so in another browser set them once:
1. Open http://127.0.0.1:11434, click the **MCP** icon in the left bar, **Add New Server**:
   URL `http://127.0.0.1:8940/mcp`, leave any proxy option off, enable it. It should say "32 tools available".
2. **Settings** (gear) > System message: paste `chat-system-prompt.txt` (this folder).
Only the tab at http://127.0.0.1:11434 or http://localhost:11434 can connect (CORS).

## How it works

```
chat page (browser) --HTTP--> 127.0.0.1:8940/mcp  supergateway 4.2.0 (Docker lbt-chat-mcp, host network)
                                  --stdio--> trim.mjs --> chrome-devtools-mcp 1.11.0 --CDP--> test Chrome :9333
```

- Bridge listens on 127.0.0.1 only; CORS allows only the chat page origins.
- `docker/trim.mjs` cuts any tool result over 16,000 characters. Without it, one full-page snapshot
  (Wikipedia) pushed the chat to 160k tokens, over ornith's 131k context, and the chat stopped with
  "request exceeds the available context size". The chat page has no setting for this.
- The page connects to the bridge directly, so the router's `--webui-mcp-proxy` flag is **not** used and
  `~/Others/Gemma/llamacpp/compose.yaml` is **unchanged**. That proxy runs inside the `llm` container, which
  cannot reach the host's 127.0.0.1, so it would need extra network changes for no gain.
- Image: `local-browser-test/cdt-mcp:1.11.0` (Dockerfile in `docker/`).

## Smoke test (2026-10-28)

Prompt: "Open https://en.wikipedia.org, search for 'Kathmandu' with the site's search box, and tell me the
population figure shown in the article's infobox, with the URL." ornith: used the search box, opened the
article, answered 856,767 (2021 census) + metro "Approximately 4 million", URL
https://en.wikipedia.org/wiki/Kathmandu. Correct (checked against the article source). 69 s.

Recording is off. For a video, use the frame recorder in `bin/run_task.sh` (`docker/record.mjs`).

## Long tasks (2026-10-28, llama.cpp b11960)

The chat page can now compact a conversation ("Compact conversation" in the context gauge popup, only while the
model is idle and once there are more steps than "preserved steps"). For long jobs (10+ items, 60-150 steps):

```bash
~/Others/P_projects/local-browser-test/bin/chat-helper-up.sh     # start BEFORE giving the task
~/Others/P_projects/local-browser-test/bin/chat-helper-down.sh   # stop (it also stops by itself at the end)
tail -f ~/Others/P_projects/local-browser-test/runs/chat-helper.log
```

What the helper does (`docker/chat-helper.mjs`, Node in Docker, drives the chat window over CDP port 9334):
- The system prompt makes the model work item by item and stop every 3 items with a **PROGRESS REPORT**.
- When the model stops after a PROGRESS REPORT: hover the context gauge, click **Compact conversation**, wait,
  then send `continue`.
- "Agentic turn limit reached. Continue?" -> clicks Continue, at most `MAX_TURN_CONTINUES` (4) times = ~300 turns.
- Context guard: while the model runs, if the gauge shows >= `MAX_USED` (70%) it presses Stop, compacts and sends
  `continue` (the model often uses up the context before its 3-item checkpoint).
- Model stopped mid-task (no PROGRESS REPORT, no final table): sends a `continue` nudge, at most `MAX_NUDGES` (5).
- Ends on the final answer (model idle, last message has a table), on an error dialog, at `MAX_ROUNDS` (15), or after two
  stalls (page unchanged for `STALL_S`=180 s while running: presses Stop, sends `continue` once).
- Env overrides: `STALL_S=… MAX_TURN_CONTINUES=… MAX_ROUNDS=… bin/chat-helper-up.sh`.

Settings (router defaults from `~/Others/Gemma/llamacpp/ui-config.json` via `--ui-config-file`, made by
`bin/mkuicfg.py`): system prompt (item list, NOTE lines, PROGRESS REPORT every 3 items, read-only rules),
agenticMaxTurns 60, excludeReasoningFromContext on, browser MCP server preset (http://127.0.0.1:8940/mcp).
A browser takes them on its first visit or Settings > Reset to default. **compactionPrompt and
compactionPreservedSteps (2) are not taken from the server by this build**: set them once by hand in Settings
(text in `ui-config.json`); the chat window profile already has them.
Bridge: tool output cut at 5,000 characters (`TRIM_CHARS` in `chat-mcp-up.sh`), 24 tools.

### Test 2026-10-28: "find 10 independent headphone review sites and each site's top pick" (ornith, chat page)

PASS: 10/10 sites with page URL and top pick; spot-check 3/3 right (The Verge: Sony WH-1000XM5 best overall,
CNET: Sony WH-1000XM6, Tom's Guide: Bose QC Ultra Gen 2). One item first pointed at a made-up domain
("vergenguide.com"), failed in the browser, and was replaced. Small slip: its summary says "5 sites" for 6.
- Time 35.8 min; 224 model calls; 107k generated tokens; prompt reading 272 s; 3 full re-processes.
- Helper: 5 compactions (3 at PROGRESS REPORTs, 2 forced by the context guard at 95% / 83%), 2 turn-limit Continues,
  2 nudges, 1 stall (Stop + continue). The helper was restarted twice during the run to add the context guard and
  the nudge fix, which are now in place. Without the guard the context reached 95% before the 3rd checkpoint.
- Log: runs/long-task-run2.helper.log, page text runs/long-task-run2.txt.
