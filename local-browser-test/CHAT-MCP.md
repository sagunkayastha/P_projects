# Browser tool in the llama.cpp chat page

The router's own chat page (http://127.0.0.1:11434) can drive a visible throw-away Chrome through
chrome-devtools-mcp. Set up 2026-10-28.

## On / off

```bash
llm-up                                                  # router (if it is off)
~/Others/P_projects/local-browser-test/bin/chat-mcp-up.sh     # 2 windows + browser tool
~/Others/P_projects/local-browser-test/bin/chat-mcp-down.sh   # closes both windows, stops the tool
llm-down                                                # when done with the model
```

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
