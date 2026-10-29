# Load each model id from models.ini once and ask one short question; print answer, load+answer time, gen tok/s.
import json, re, sys, time, urllib.request as u
ids = re.findall(r'^\[([^\]*][^\]]*)\]', open(sys.argv[1]).read(), re.M)
for m in ids:
    body = json.dumps({"model": m, "messages": [{"role": "user", "content": "What is 7 times 6? Answer with just the number."}], "max_tokens": 1500}).encode()
    t0 = time.time()
    try:
        d = json.load(u.urlopen(u.Request("http://127.0.0.1:11434/v1/chat/completions", body, {"Content-Type": "application/json"}), timeout=300))
        c = d["choices"][0]["message"]; t = d.get("timings", {})
        print(f"{m:20s} OK   {time.time()-t0:5.1f}s  answer={(c.get('content') or '').strip()[:20]!r}  gen={t.get('predicted_per_second', 0):.0f} tok/s", flush=True)
    except Exception as e:
        msg = e.read().decode()[:160] if hasattr(e, 'read') else str(e)[:160]
        print(f"{m:20s} FAIL {time.time()-t0:5.1f}s  {msg}", flush=True)
r = json.load(u.urlopen(u.Request("http://127.0.0.1:8082/v1/embeddings", json.dumps({"input": "pollen", "model": "nomic-embed-text"}).encode(), {"Content-Type": "application/json"}), timeout=60))
print("embeddings           OK   dim =", len(r["data"][0]["embedding"]))
