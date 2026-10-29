#!/usr/bin/env bash
# Start the auto-compact helper for long tasks in the chat window (see docker/chat-helper.mjs, CHAT-MCP.md).
# Start it, then give the task in the chat window. Log: runs/chat-helper.log (also: docker logs -f lbt-chat-helper).
cd "$(dirname "$0")/.."
docker rm -f lbt-chat-helper >/dev/null 2>&1
mkdir -p runs && : > runs/chat-helper.log
docker run -d --name lbt-chat-helper --network host --user 1000:1000 --label local-browser-test=1 \
  -e STALL_S="${STALL_S:-180}" -e MAX_TURN_CONTINUES="${MAX_TURN_CONTINUES:-4}" -e MAX_ROUNDS="${MAX_ROUNDS:-15}" -e MAX_NUDGES="${MAX_NUDGES:-5}" -e MAX_USED="${MAX_USED:-70}" \
  -v "$PWD/docker/chat-helper.mjs:/h.mjs:ro" -v "$PWD/runs:/out" node:22-bookworm-slim node /h.mjs >/dev/null \
  && echo "helper running (log: $PWD/runs/chat-helper.log)"
