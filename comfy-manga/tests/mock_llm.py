"""Mock llama.cpp router for UI tests without a GPU: /models says a model is loaded, chat completions stream
a fixed shot list (edit turns answer a short text + the same list with panel 2 changed)."""
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SL = {"title": "Rainy cafe", "bible": {"location": "small wooden cafe, counter on the left, shelf of glass jars",
      "time_light": "rainy evening, warm lamp over the counter", "props": "Nori's black folding umbrella",
      "wardrobe": "Nori: striped scarf, cardigan; Bram: flat cap, dark vest", "mood": "cosy"},
      "panels": [{"shot": "wide", "angle": "eye level", "characters": ["Nori"], "action": "Nori runs in out of the rain",
                  "expression": "out of breath", "setting": "cafe door", "light": "cold window light", "effects": "speed lines",
                  "dialogue": ""},
                 {"shot": "medium", "angle": "eye level", "characters": ["Bram"], "action": "Bram looks up from the counter",
                  "expression": "dry smile", "setting": "counter, jars", "light": "lamp glow", "effects": "",
                  "dialogue": "BRAM: \"You forgot your umbrella again.\""},
                 {"shot": "medium close-up", "angle": "three-quarter", "characters": ["Nori"],
                  "action": "Nori shakes water off her scarf", "expression": "embarrassed", "setting": "door mat",
                  "light": "lamp glow", "effects": "sweat drop", "dialogue": ""},
                 {"shot": "close-up", "angle": "eye level", "characters": ["Bram", "Nori"],
                  "action": "Bram slides a hot cup to Nori", "expression": "kind eyes", "setting": "counter",
                  "light": "lamp glow", "effects": "steam", "dialogue": "BRAM: \"On the house.\""}],
      "review": ["umbrella stays black"]}


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"data": [{"id": "qwen36", "status": {"value": "loaded"}}]}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        turns = sum(1 for m in req["messages"] if m["role"] == "user")
        sl = json.loads(json.dumps(SL))
        if turns > 1:
            sl["panels"][1]["angle"] = "low angle"
        text = ("Here is the shot list." if turns == 1 else "Panel 2 is now a low angle.") + "\n```json\n" + json.dumps(sl, indent=1) + "\n```"
        self.send_response(200); self.send_header("Content-Type", "text/event-stream"); self.end_headers()
        for i in range(0, len(text), 40):
            self.wfile.write(b"data: " + json.dumps({"choices": [{"delta": {"content": text[i:i + 40]}}]}).encode() + b"\n\n")
            self.wfile.flush(); time.sleep(0.03)
        self.wfile.write(b"data: [DONE]\n\n")

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("0.0.0.0", 8080), H).serve_forever()
