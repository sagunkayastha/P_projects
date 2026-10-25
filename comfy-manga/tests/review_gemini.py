"""Gemini review of a bench round (run on archbox, key ~/.config/gemini/aistudio.key, free tier: TEST IMAGES ONLY).
  python3 review_gemini.py <brief.md> <prompts.json> <out.json> <image> [<image> ...] [-m model]"""
import base64, json, os, sys, urllib.error, urllib.request
args = sys.argv[1:]
model = "gemini-3.8-flash"
if "-m" in args:
    i = args.index("-m"); model = args[i + 1]; del args[i:i + 2]
brief, prompts, out, imgs = args[0], args[1], args[2], args[3:]
key = open(os.path.expanduser("~/.config/gemini/aistudio.key")).read().strip()
parts = [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(p, "rb").read()).decode()}} for p in imgs]
parts.append({"text": open(brief).read() + "\n\nPROMPTS:\n" + open(prompts).read()})
body = {"contents": [{"parts": parts}], "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"}}
import time
d = None
for m in [model, "gemini-3.7-flash", "gemini-2.5-flash"]:  # busy (503/429): wait, retry, then an older Flash
    for wait in (0, 20, 60):
        time.sleep(wait)
        try:
            r = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent",
                                       json.dumps(body).encode(), {"x-goog-api-key": key, "Content-Type": "application/json"})
            d = json.load(urllib.request.urlopen(r, timeout=600))
            break
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 503):
                raise
    if d:
        print(f"model: {m}", file=sys.stderr)
        break
if not d:
    sys.exit("gemini busy")
text = d["candidates"][0]["content"]["parts"][0]["text"]
open(out, "w").write(text)
print(text)
