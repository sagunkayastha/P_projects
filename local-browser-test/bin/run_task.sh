#!/usr/bin/env bash
# Usage: bin/run_task.sh <model id, e.g. ornith> <task id from tasks.json>
# One fresh opencode session (private server) with only the chrome-devtools MCP browser (see opencode.json).
set -u
cd "$(dirname "$0")/.."
M=$1; T=$2; OUT=runs/$M${RUNTAG:+-$RUNTAG}; mkdir -p "$OUT"; [ -n "${REC:-}" ] && mkdir -p "shots/frames-$M-$T"
P=$(python3 -c "import json,sys; print(json.load(open('tasks.json'))[sys.argv[1]])" "$T")
# reset the visible Chrome: close extra tabs, main tab to about:blank
python3 - <<'PY'
import json, urllib.request as u
tabs=[t for t in json.load(u.urlopen('http://127.0.0.1:9333/json')) if t['type']=='page']
for t in tabs[1:]: u.urlopen('http://127.0.0.1:9333/json/close/'+t['id'])
PY
[ -n "${REC:-}" ] && docker run -d --rm --name lbt-rec --network host -v "$PWD/docker/record.mjs:/r.mjs:ro" -v "$PWD/shots/frames-$M-$T:/out" node:22-bookworm-slim node /r.mjs >/dev/null
S=$(date +%s); SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
: > "$OUT/$T.jsonl"
# LIVE=1: visible Konsole on the desktop following the run (thinking, tool calls, tokens)
if [ -n "${LIVE:-}" ]; then
  PS=$(pgrep -x plasmashell | head -1)
  env $(tr '\0' '\n' < /proc/$PS/environ | grep -E '^(DISPLAY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|XAUTHORITY)=') \
    kstart -- konsole --hold -p tabtitle="opencode $M $T" -e python3 -I "$PWD/bin/live.py" "$PWD/$OUT/$T.jsonl" >/dev/null 2>&1
fi
timeout 900 opencode run --standalone --thinking -m "pc/$M" --format json "$P" > "$OUT/$T.jsonl" 2> "$OUT/$T.err"; RC=$?
E=$(date +%s)
docker rm -f lbt-rec >/dev/null 2>&1
{ python3 -I bin/summ.py "$OUT/$T.jsonl" $((E-S)) $RC; echo "ROUTER: $(docker logs llm --since "$SINCE" 2>&1 | python3 -I bin/logstats.py)"; } | tee "$OUT/$T.summary.txt"
