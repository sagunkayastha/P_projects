#!/usr/bin/env bash
# Stop the chat-page browser tool: bridge container + both throw-away Chrome windows (only ones using our profiles).
cd "$(dirname "$0")/.."
docker rm -f lbt-chat-mcp >/dev/null 2>&1 && echo "bridge stopped"
pkill -f -- "--user-data-dir=$PWD/chrome-profile" && echo "test Chrome closed"
pkill -f -- "--user-data-dir=$PWD/chat-ui-profile" && echo "chat window closed"
true
