#!/usr/bin/env bash
# Usage: bin/run_task.sh <model id, e.g. ornith> <task id from tasks.json>
# One fresh opencode session (private server) with only the chrome-devtools MCP browser (see opencode.json).
set -u
cd "$(dirname "$0")/.."
M=$1; T=$2; OUT=runs/$M; mkdir -p "$OUT" "shots/frames-$M-$T"
P=$(python3 -c "import json,sys; print(json.load(open('tasks.json'))[sys.argv[1]])" "$T")
# reset the visible Chrome: close extra tabs, main tab to about:blank
python3 - <<'PY'
import json, urllib.request as u
tabs=[t for t in json.load(u.urlopen('http://127.0.0.1:9333/json')) if t['type']=='page']
for t in tabs[1:]: u.urlopen('http://127.0.0.1:9333/json/close/'+t['id'])
PY
docker run -d --rm --name lbt-rec --network host -v "$PWD/docker/record.mjs:/r.mjs:ro" -v "$PWD/shots/frames-$M-$T:/out" node:22-bookworm-slim node /r.mjs >/dev/null
S=$(date +%s)
timeout 900 opencode run --standalone -m "pc/$M" --format json "$P" > "$OUT/$T.jsonl" 2> "$OUT/$T.err"; RC=$?
E=$(date +%s)
docker rm -f lbt-rec >/dev/null 2>&1
python3 -I bin/summ.py "$OUT/$T.jsonl" $((E-S)) $RC | tee "$OUT/$T.summary.txt"
