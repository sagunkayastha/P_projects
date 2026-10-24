"""Client for the host helper manga-gpu (comfy-manga/host/manga-gpu), reached over SSH with a key that can only
run that helper. It switches the 5070 Ti between drawing (comfyui-manga) and the local LLM, and relays LLM
calls (the llama.cpp router listens on the host's localhost only). Without the key: LLM calls go straight to
LLM_URL and the mode buttons are hidden.
"""
import json
import os
import subprocess
import urllib.request

KEY = os.environ.get("GPU_KEY", "/keys/id_ed25519")
KNOWN = os.environ.get("GPU_KNOWN_HOSTS", "/keys/known_hosts")
HOST = os.environ.get("GPU_HOST", "sgkayast@host.docker.internal")
LLM = os.environ.get("LLM_URL", "http://host.docker.internal:11434")


def available():
    return os.path.exists(KEY)


def _ssh(verb):
    return ["ssh", "-i", KEY, "-o", f"UserKnownHostsFile={KNOWN}", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
            "-o", "LogLevel=ERROR", HOST, verb]


def call(verb, data=None, timeout=30):
    """Run a helper verb; returns (exit code, stdout bytes, stderr text)."""
    r = subprocess.run(_ssh(verb), input=data, capture_output=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr.decode("utf-8", "ignore").strip()


def status():
    if not available():
        return None
    try:
        rc, out, err = call("status", timeout=20)
        return json.loads(out) if rc == 0 else {"error": err or f"helper exit {rc}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"[:200]}


def mode(verb):
    rc, out, err = call(verb, timeout=30)
    if rc != 0:
        raise RuntimeError(err or f"helper exit {rc}")
    return out.decode().strip()


def models():
    """The router's /models JSON, or None when it is not running."""
    try:
        if available():
            rc, out, _ = call("models", timeout=15)
            return json.loads(out) if rc == 0 else None
        with urllib.request.urlopen(LLM + "/models", timeout=3) as r:
            return json.load(r)
    except Exception:
        return None


def chat_stream(body):
    """POST a chat completion; yields raw response lines (bytes). body: dict (stream may be on or off)."""
    data = json.dumps(body).encode()
    if available():
        p = subprocess.Popen(_ssh("chat"), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.stdin.write(data)
        p.stdin.close()
        try:
            yield from p.stdout
        finally:
            rc = p.wait(timeout=30)
            if rc != 0:
                raise RuntimeError(p.stderr.read().decode("utf-8", "ignore").strip() or f"helper exit {rc}")
        return
    req = urllib.request.Request(LLM + "/v1/chat/completions", data, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as r:
        yield from r


def chat(body):
    """Non-streaming chat completion -> response JSON."""
    return json.loads(b"".join(chat_stream({**body, "stream": False})))
