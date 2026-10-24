"""Thin client for the ComfyUI HTTP + websocket API."""
import json
import os
import time
import uuid
import urllib.request
import urllib.error

COMFY = os.environ.get("COMFY_URL", "http://comfyui:8188")
WS = COMFY.replace("https://", "wss://").replace("http://", "ws://")


class JobCancelled(Exception):
    pass


def _post(path, body):
    req = urllib.request.Request(COMFY + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=30))


def _get(path, timeout=30):
    return json.load(urllib.request.urlopen(COMFY + path, timeout=timeout))


def wait_ready(timeout=180):
    """Block until ComfyUI answers (used at startup)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(COMFY + "/system_stats", timeout=5)
            return True
        except Exception:
            time.sleep(2)
    return False


def submit(workflow, client_id):
    return _post("/prompt", {"prompt": workflow, "client_id": client_id})["prompt_id"]


def history(pid):
    return _get(f"/history/{pid}")


def interrupt():
    try:
        _post("/interrupt", {})
    except Exception:
        pass


def free():
    """Drop cached models + free RAM/VRAM after heavy jobs."""
    try:
        _post("/free", {"unload_models": True, "free_memory": True})
    except Exception:
        pass


def run_job(workflow, cancel_check=None, on_progress=None):
    """Submit a workflow and block until it finishes.

    Returns the ComfyUI history entry for the prompt.
    Raises JobCancelled if cancel_check() becomes true.
    """
    client_id = str(uuid.uuid4())
    pid = submit(workflow, client_id)
    try:
        import websocket
    except ImportError:
        websocket = None

    if websocket is not None:
        try:
            _track_ws(websocket, pid, client_id, cancel_check, on_progress)
        except (JobCancelled, RuntimeError):
            raise
        except Exception:
            # any websocket trouble: fall back to polling history
            _track_poll(pid, cancel_check)
    else:
        _track_poll(pid, cancel_check)
    return _await_history(pid).get(pid, {})


def _await_history(pid, timeout=60):
    """ComfyUI writes the history entry slightly after the websocket 'done' message."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        h = history(pid)
        entry = h.get(pid)
        if entry and (entry.get("outputs") or entry.get("status", {}).get("status_str") != "success"):
            return h
        time.sleep(0.5)
    return history(pid)


def _track_ws(websocket, pid, client_id, cancel_check, on_progress):
    ws = websocket.WebSocket()
    ws.connect(f"{WS}/ws?clientId={client_id}", timeout=10)
    ws.settimeout(5.0)
    try:
        while True:
            if cancel_check and cancel_check():
                interrupt()
                raise JobCancelled()
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            msg = json.loads(raw)
            t = msg.get("type")
            d = msg.get("data", {})
            if t == "progress" and d.get("prompt_id") == pid and on_progress:
                on_progress(d.get("value", 0), d.get("max", 1))
            elif t == "executing" and d.get("prompt_id") == pid and d.get("node") is None:
                return
            elif t == "execution_error" and d.get("prompt_id") == pid:
                raise RuntimeError(d.get("exception_message", "execution error"))
            elif t == "execution_interrupted" and d.get("prompt_id") == pid:
                raise JobCancelled()
            # keepalive / status / other clients' messages are ignored
    finally:
        try:
            ws.close()
        except Exception:
            pass


def _track_poll(pid, cancel_check):
    while True:
        if cancel_check and cancel_check():
            interrupt()
            raise JobCancelled()
        if pid in history(pid):
            return
        time.sleep(2)


def result_files(entry):
    """List output files from a history entry as (subfolder, filename)."""
    out = []
    for node_out in entry.get("outputs", {}).values():
        for key in ("images", "gifs", "videos"):
            for item in node_out.get(key, []):
                out.append((item.get("subfolder", ""), item["filename"]))
    return out
