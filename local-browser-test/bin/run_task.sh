#!/usr/bin/env bash
# Usage: bin/run_task.sh <model id, e.g. ornith> <task id from tasks.json>
# One fresh opencode session (private server) with only the chrome-devtools MCP browser (see opencode.json).
# Env: RUNTAG=x (results in runs/<model>-x), LIVE=1 (visible Konsole), REC=1 (frame recorder),
#      LIMIT=900 (hard limit, s), STALL=180 (no router request / no tool event for this long = stall), RETRY=1.
set -u
cd "$(dirname "$0")/.."
M=$1; T=$2; OUT=runs/$M${RUNTAG:+-$RUNTAG}; mkdir -p "$OUT"; [ -n "${REC:-}" ] && mkdir -p "shots/frames-$M-$T"
LIMIT=${LIMIT:-900}; STALL=${STALL:-180}; RETRY=${RETRY:-1}
P=$(python3 -c "import json,sys; print(json.load(open('tasks.json'))[sys.argv[1]])" "$T")
STATUS="$OUT/$T.status"

attempt() {  # $1 = attempt number. Sets RC and CAUSE.
  # reset the visible Chrome: close extra tabs
  python3 - <<'PY'
import json, urllib.request as u
tabs=[t for t in json.load(u.urlopen('http://127.0.0.1:9333/json')) if t['type']=='page']
for t in tabs[1:]: u.urlopen('http://127.0.0.1:9333/json/close/'+t['id'])
PY
  : > "$OUT/$T.jsonl"; : > "$STATUS"
  if [ -n "${LIVE:-}" ]; then
    pkill -f "konsole --hold -p tabtitle=opencode " 2>/dev/null   # close old live windows
    PS=$(pgrep -x plasmashell | head -1)
    env $(tr '\0' '\n' < /proc/$PS/environ | grep -E '^(DISPLAY|WAYLAND_DISPLAY|XDG_RUNTIME_DIR|DBUS_SESSION_BUS_ADDRESS|XAUTHORITY)=') \
      kstart -- konsole --hold -p tabtitle="opencode $M $T" -e python3 -I "$PWD/bin/live.py" "$PWD/$OUT/$T.jsonl" "$PWD/$STATUS" >/dev/null 2>&1
  fi
  [ -n "${REC:-}" ] && docker run -d --rm --name lbt-rec --network host -v "$PWD/docker/record.mjs:/r.mjs:ro" -v "$PWD/shots/frames-$M-$T:/out" node:22-bookworm-slim node /r.mjs >/dev/null
  S=$(date +%s); SINCE=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  # stdin MUST be closed: opencode run reads piped stdin when it is not a terminal and waits forever on an open one
  # (cause of the 'hang before the first request'). FORCE_STALL=1 reproduces that hang to test the watchdog.
  if [ -n "${FORCE_STALL:-}" ]; then   # stdin = a pipe whose writer never closes (the real hang)
    FIFO="$OUT/$T.fifo"; rm -f "$FIFO"; mkfifo "$FIFO"; (exec 3>"$FIFO"; sleep $((LIMIT+60))) >/dev/null 2>&1 &
    setsid opencode run --standalone --thinking -m "pc/$M" --format json "$P" < "$FIFO" > "$OUT/$T.jsonl" 2> "$OUT/$T.err" &
  else
    setsid opencode run --standalone --thinking -m "pc/$M" --format json "$P" < /dev/null > "$OUT/$T.jsonl" 2> "$OUT/$T.err" &
  fi
  PID=$!; CAUSE=""; last_req=$S; last_ev=$S; nlines=0
  while kill -0 $PID 2>/dev/null; do
    sleep 10; now=$(date +%s)
    n=$(wc -l < "$OUT/$T.jsonl"); [ "$n" != "$nlines" ] && { nlines=$n; last_ev=$now; }
    [ "$(docker logs llm --since 15s 2>&1 | grep -c 'proxying request')" -gt 0 ] && last_req=$now
    steps=$(grep -c '"step_start"' "$OUT/$T.jsonl")
    echo "watchdog: attempt $1, $((now-S))s/${LIMIT}s, step $steps, last router request $((now-last_req))s ago, last event $((now-last_ev))s ago" >> "$STATUS"
    if   [ $((now-S)) -ge $LIMIT ];            then CAUSE="hard limit ${LIMIT}s"
    elif [ $((now-last_req)) -ge $STALL ];     then CAUSE="no router request for ${STALL}s (step $steps)"
    elif [ $((now-last_ev)) -ge $STALL ];      then CAUSE="no opencode event for ${STALL}s (step $steps)"
    fi
    if [ -n "$CAUSE" ]; then
      echo "watchdog: STOP ($CAUSE)" >> "$STATUS"
      kill -TERM -- -$PID 2>/dev/null; sleep 3; kill -KILL -- -$PID 2>/dev/null
      docker ps -q --filter label=lbt-run=1 | xargs -r docker rm -f >/dev/null   # its MCP container
      break
    fi
  done
  wait $PID 2>/dev/null; RC=$?; rm -f "$OUT/$T.fifo"; [ -n "$CAUSE" ] && RC=124
  E=$(date +%s)
  docker rm -f lbt-rec >/dev/null 2>&1
  { python3 -I bin/summ.py "$OUT/$T.jsonl" $((E-S)) $RC; echo "ROUTER: $(docker logs llm --since "$SINCE" 2>&1 | python3 -I bin/logstats.py)"
    echo "WATCHDOG: attempt $1: ${CAUSE:-ok}"; } > "$OUT/$T.summary.txt"
}

for a in $(seq 1 $((RETRY+1))); do
  attempt $a
  cat "$OUT/$T.summary.txt"
  [ -z "$CAUSE" ] && break
  cp "$OUT/$T.jsonl" "$OUT/$T.attempt$a.jsonl"; cp "$OUT/$T.summary.txt" "$OUT/$T.attempt$a.summary.txt"
  [ $a -le $RETRY ] && echo "watchdog: retrying ($CAUSE)" | tee -a "$STATUS"
done
[ -n "$CAUSE" ] && echo "RESULT: FAILED after $a attempt(s): $CAUSE" | tee -a "$OUT/$T.summary.txt"
true
