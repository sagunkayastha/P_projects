import json, sys
f, secs, rc = sys.argv[1], sys.argv[2], sys.argv[3]
steps = tools = errs = 0; calls = []; text = ''
for l in open(f):
    try: e = json.loads(l)
    except Exception: continue
    p = e.get('part', {})
    if e['type'] == 'step_start': steps += 1
    if e['type'] == 'tool_use':
        tools += 1; st = p.get('state', {})
        if st.get('status') == 'error': errs += 1
        calls.append(f"{p.get('tool')}[{st.get('status')}]: " + json.dumps(st.get('input'))[:160])
    if e['type'] == 'text': text = p.get('text', '')
print(f"time_s={secs} rc={rc} steps={steps} tool_calls={tools} tool_errors={errs}")
for c in calls: print('  ', c)
print('FINAL ANSWER:\n' + text)
