"""Thin client for the ComfyUI HTTP + websocket API.

Pictures go in through /upload/image and come back through /view, so the app needs no shared folders
with ComfyUI. A job is tracked by its prompt_id + client_id (both stored in the app DB), so after an app
restart the worker re-attaches to a prompt that is still queued or running in ComfyUI.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

COMFY = os.environ.get("COMFY_URL", "http://comfyui:8188")
WS = COMFY.replace("https://", "wss://").replace("http://", "ws://")


class JobCancelled(Exception):
    pass


class PromptLost(Exception):
    """ComfyUI no longer knows the prompt (it was restarted): submit again."""


def _post(path, body, timeout=30):
    req = urllib.request.Request(COMFY + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def _get(path, timeout=30):
    with urllib.request.urlopen(COMFY + path, timeout=timeout) as r:
        return json.load(r)


def alive():
    try:
        _get("/system_stats", timeout=3)
        return True
    except Exception:
        return False


def submit(workflow, client_id):
    try:
        return _post("/prompt", {"prompt": workflow, "client_id": client_id})["prompt_id"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:600]
        raise RuntimeError(f"ComfyUI refused the job: {detail}")


def history(pid):
    return _get(f"/history/{pid}").get(pid)


def in_queue(pid):
    q = _get("/queue", timeout=10)
    for item in q.get("queue_running", []) + q.get("queue_pending", []):
        if len(item) > 1 and item[1] == pid:
            return True
    return False


def interrupt():
    try:
        _post("/interrupt", {})
    except Exception:
        pass


def delete_queued(pid):
    try:
        _post("/queue", {"delete": [pid]})
    except Exception:
        pass


def free():
    """Drop cached models + free RAM/VRAM (when switching model families; klein 9B fills the card)."""
    try:
        _post("/free", {"unload_models": True, "free_memory": True})
    except Exception:
        pass


def upload(data, name, subfolder="studio"):
    """Upload PNG bytes into ComfyUI's input folder; returns the LoadImage name."""
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in (("subfolder", subfolder), ("type", "input"), ("overwrite", "true")):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
                 f'Content-Type: image/png\r\n\r\n'.encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(COMFY + "/upload/image", b"".join(parts),
                                 {"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    return f"{out['subfolder']}/{out['name']}" if out.get("subfolder") else out["name"]


def view(item):
    q = urllib.parse.urlencode({"filename": item["filename"], "subfolder": item.get("subfolder", ""),
                                "type": item.get("type", "output")})
    with urllib.request.urlopen(f"{COMFY}/view?{q}", timeout=60) as r:
        return r.read()


def outputs(entry):
    """Image items and ui text from a history entry."""
    imgs, ui = [], {}
    for node_out in (entry or {}).get("outputs", {}).values():
        for item in node_out.get("images", []):
            imgs.append(item)
        for k, v in node_out.items():
            if k != "images":
                ui[k] = v
    return imgs, ui


def track(pid, client_id, cancel_check=None, on_progress=None):
    """Block until prompt `pid` finishes; returns its history entry.

    Uses the websocket (same client_id as the submit, so progress messages keep coming after a
    re-attach) and also checks /history every few seconds, so a missed message never hangs a job."""
    try:
        import websocket
    except ImportError:
        websocket = None
    ws = None
    last_check = 0.0
    misses = 0
    try:
        while True:
            if cancel_check and cancel_check():
                if in_queue(pid):
                    delete_queued(pid)
                    interrupt()
                raise JobCancelled()
            if ws is None and websocket is not None:
                try:
                    ws = websocket.WebSocket()
                    ws.connect(f"{WS}/ws?clientId={client_id}", timeout=10)
                    ws.settimeout(2.0)
                except Exception:
                    ws = None
            if ws is not None:
                try:
                    msg = json.loads(ws.recv())
                    t, d = msg.get("type"), msg.get("data", {})
                    if d.get("prompt_id") == pid:
                        if t == "progress" and on_progress:
                            on_progress(d.get("value", 0), d.get("max", 1))
                        elif t == "execution_error":
                            raise RuntimeError(d.get("exception_message", "execution error").strip()[:400])
                        elif t == "execution_interrupted":
                            raise JobCancelled()
                except (RuntimeError, JobCancelled):
                    raise
                except websocket.WebSocketTimeoutException:
                    pass
                except Exception:
                    try:
                        ws.close()
                    except Exception:
                        pass
                    ws = None
                    time.sleep(1)
            else:
                time.sleep(1.5)
            if time.time() - last_check > 3:
                last_check = time.time()
                entry = history(pid)
                if entry:
                    st = entry.get("status", {})
                    if st.get("status_str") == "error":
                        msgs = [m[1] for m in st.get("messages", []) if m[0] == "execution_error"]
                        err = (msgs[0].get("exception_message", "") if msgs else "") or "ComfyUI error"
                        raise RuntimeError(err.strip()[:400])
                    if st.get("completed") or entry.get("outputs"):
                        return entry
                else:
                    if in_queue(pid):
                        misses = 0
                    else:
                        misses += 1
                        if misses >= 3:  # neither finished nor queued: ComfyUI lost it
                            raise PromptLost()
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
