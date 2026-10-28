#!/usr/bin/env bash
# Browser tool for the llama.cpp chat page: visible throw-away Chrome (debug port 9333) +
# chrome-devtools-mcp behind supergateway at http://127.0.0.1:8940/mcp (CORS only for the chat page).
set -eu
cd "$(dirname "$0")/.."
PS=$(pgrep -x plasmashell | head -1)
eval "$(tr '\0' '\n' < /proc/$PS/environ | grep -E '^(DISPLAY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|XAUTHORITY)=' | sed 's/^/export /')"
if ! curl -s -m 2 127.0.0.1:9333/json/version >/dev/null; then
  kstart -- google-chrome-stable --user-data-dir="$PWD/chrome-profile" --remote-debugging-port=9333 \
    --remote-debugging-address=127.0.0.1 --no-first-run --no-default-browser-check --disable-sync \
    --window-size=1280,900 about:blank >/dev/null 2>&1
  for i in $(seq 20); do curl -s -m 1 127.0.0.1:9333/json/version >/dev/null && break; sleep 1; done
fi
# chat page window: its own throw-away profile (settings already saved there: MCP server + system prompt)
if ! curl -s -m 2 127.0.0.1:9334/json/version >/dev/null; then
  kstart -- google-chrome-stable --user-data-dir="$PWD/chat-ui-profile" --remote-debugging-port=9334 \
    --remote-debugging-address=127.0.0.1 --no-first-run --no-default-browser-check --disable-sync \
    --window-size=1100,950 http://127.0.0.1:11434/ >/dev/null 2>&1
fi
# keep a running bridge (restarting it drops the chat page's MCP session)
if [ "$(docker inspect -f '{{.State.Running}}' lbt-chat-mcp 2>/dev/null)" != true ]; then
docker rm -f lbt-chat-mcp >/dev/null 2>&1 || true
docker run -d --name lbt-chat-mcp --network host --user 1000:1000 --label local-browser-test=1 \
  -v "$PWD/docker/trim.mjs:/trim.mjs:ro" --entrypoint supergateway local-browser-test/cdt-mcp:1.11.0 \
  --stdio "node /trim.mjs chrome-devtools-mcp --browserUrl http://127.0.0.1:9333 --usageStatistics=false --categoryPerformance=false --categoryNetwork=false --categoryEmulation=false --categoryMemory=false" \
  --outputTransport streamableHttp --stateful --host 127.0.0.1 --port 8940 \
  --cors "http://127.0.0.1:11434" "http://localhost:11434" --logLevel info >/dev/null
fi
sleep 2; docker ps --filter name=lbt-chat-mcp --format '{{.Names}} {{.Status}}'
echo "MCP URL: http://127.0.0.1:8940/mcp   (chat page: http://127.0.0.1:11434)"
