# Live view of an opencode --format json run: follows the file and prints thinking, text and tool calls.
import json, sys, time, textwrap
f = open(sys.argv[1]); step = 0; t0 = None
while True:
    line = f.readline()
    if not line:
        time.sleep(0.3); continue
    try: e = json.loads(line)
    except Exception: continue
    p = e.get('part', {}); ts = e.get('timestamp', 0) / 1000
    t0 = t0 or ts; el = f"[{ts - t0:6.1f}s]"
    k = e.get('type')
    if k == 'step_start':
        step += 1; print(f"\n\033[1;36m{el} ── step {step} ──\033[0m", flush=True)
    elif k == 'reasoning':
        print("\033[2m" + textwrap.shorten(p.get('text', ''), 600) + "\033[0m", flush=True)
    elif k == 'text':
        print("\033[1m" + p.get('text', '') + "\033[0m", flush=True)
    elif k == 'tool_use':
        st = p.get('state', {}); code = json.dumps(st.get('input'))[:300]
        print(f"\033[33m{el} TOOL {p.get('tool')} [{st.get('status')}]\033[0m {code}", flush=True)
    elif k == 'step_finish':
        tk = p.get('tokens', {})
        print(f"\033[2m{el} tokens in={tk.get('input')} out={tk.get('output')} think={tk.get('reasoning')} cache_read={tk.get('cache', {}).get('read')}\033[0m", flush=True)
    elif k == 'error':
        print("\033[31mERROR " + json.dumps(e.get('error'))[:400] + "\033[0m", flush=True)
