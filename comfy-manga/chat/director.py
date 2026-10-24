"""Director: a chat with the local LLM (llama.cpp router on the host) that turns simple panel lines into a
shot list (scene bible + per-panel shot design). System prompt = director-skills.md (repo default, or the
user's edited copy in APP_DIR). Multi-turn: the whole conversation is sent each time, so "make panel 2 a low
angle" works. Answers stream into the DB (the phone sees them grow through the normal long poll).
"""
import json
import os
import re
import threading
import time
import urllib.request
from pathlib import Path

import db

LLM = os.environ.get("LLM_URL", "http://host.docker.internal:11434")
MODEL = os.environ.get("DIRECTOR_MODEL", "qwen36")
DEFAULT_SKILLS = Path(__file__).resolve().parent / "director-skills.md"
SCHEMA = """
CREATE TABLE IF NOT EXISTS dchats (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, title TEXT, chars TEXT);
CREATE TABLE IF NOT EXISTS dmsgs (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, ts REAL, role TEXT,
    content TEXT, shotlist TEXT, status TEXT, error TEXT);
CREATE INDEX IF NOT EXISTS dmsgs_chat ON dmsgs(chat_id);
"""
_busy = set()


def init():
    with db._lock:
        db._conn.executescript(SCHEMA)
    db.JSON_COLS.add("shotlist")
    # answers cut off by an app restart
    with db._lock:
        db._conn.execute("UPDATE dmsgs SET status='failed', error='stopped by an app restart' WHERE status='working'")


def skills_path():
    return db.APP_DIR / "director-skills.md"


def skills():
    p = skills_path()
    return p.read_text() if p.exists() else DEFAULT_SKILLS.read_text()


def set_skills(text):
    p = skills_path()
    if text is None:
        p.unlink(missing_ok=True)  # back to the repo default
    else:
        p.write_text(text)


def llm_state():
    """off (router not running) | idle (running, no model loaded) | loading | ready (model loaded)."""
    try:
        with urllib.request.urlopen(LLM + "/models", timeout=3) as r:
            data = json.load(r)
    except Exception:
        return {"state": "off", "model": None}
    for m in data.get("data", []):
        st = m.get("status")
        st = st.get("value") if isinstance(st, dict) else st
        if st in ("loaded", "loading"):
            return {"state": "ready" if st == "loaded" else "loading", "model": m.get("id")}
    return {"state": "idle", "model": None}


def unload():
    try:
        req = urllib.request.Request(LLM + "/models/unload", json.dumps({"model": MODEL}).encode(),
                                     {"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
        return True
    except Exception:
        return False


def _system(chars):
    s = skills()
    if chars:
        s += "\n\n## Saved characters (use these exact names)\n" + "\n".join(
            f"- {c['name']}" + (f": {c['traits']}" if c.get("traits") else "") for c in chars)
    return s


def parse_shotlist(text):
    """The JSON shot list in an answer (```json block or the outermost {...}), or None."""
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    raw = m.group(1) if m else None
    if raw is None:
        a, b = text.find("{"), text.rfind("}")
        raw = text[a:b + 1] if a >= 0 and b > a else None
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(d, dict) or not isinstance(d.get("panels"), list) or not d["panels"]:
        return None
    return d


def send(chat_id, text, chars):
    """Add the user's message and start the answer in the background. Returns the answer row id."""
    db.insert("dmsgs", chat_id=chat_id, role="user", content=text, status="done")
    aid = db.insert("dmsgs", chat_id=chat_id, role="assistant", content="", status="working")
    threading.Thread(target=_answer, args=(chat_id, aid, chars), daemon=True).start()
    return aid


def _answer(chat_id, aid, chars):
    _busy.add(aid)
    try:
        hist = db.query("SELECT role, content, shotlist FROM dmsgs WHERE chat_id=? AND id<? AND status='done' "
                        "ORDER BY id", (chat_id, aid))
        msgs = [{"role": "system", "content": _system(chars)}]
        for h in hist:
            msgs.append({"role": h["role"], "content": h["content"]})
        body = {"model": MODEL, "messages": msgs, "stream": True, "temperature": 0.6, "max_tokens": 6000,
                "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request(LLM + "/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        out, last = [], 0.0
        with urllib.request.urlopen(req, timeout=600) as r:
            for raw in r:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0].get("delta", {}).get("content") or ""
                except (ValueError, KeyError, IndexError):
                    continue
                out.append(delta)
                if time.time() - last > 0.7:
                    last = time.time()
                    db.update("dmsgs", aid, content="".join(out))
        text = re.sub(r"<think>.*?</think>", "", "".join(out), flags=re.S).strip()
        sl = parse_shotlist(text)
        db.update("dmsgs", aid, content=text, shotlist=sl, status="done",
                  error=None if sl else "no shot list in this answer (ask again or say 'give the full JSON')")
    except Exception as e:  # noqa: BLE001
        db.update("dmsgs", aid, status="failed", error=f"{type(e).__name__}: {e}"[:300])
    finally:
        _busy.discard(aid)


def page_lines(sl):
    """Shot list -> (4-or-more page lines, bible text) for Make page."""
    lines = []
    for p in sl.get("panels", []):
        parts = [", ".join(x for x in (p.get("shot"), p.get("angle")) if x)]
        for k in ("action", "expression"):
            if p.get(k):
                parts.append(str(p[k]).strip().rstrip("."))
        for k, lab in (("setting", "Setting"), ("light", "Light"), ("effects", "Effects")):
            if p.get(k):
                parts.append(f"{lab}: {str(p[k]).strip().rstrip('.')}")
        line = ". ".join(x for x in parts if x) + "."
        d = (p.get("dialogue") or "").strip()
        if d and '"' not in d and "“" not in d:
            d = f'"{d.split(":", 1)[-1].strip()}"'
        if d:
            line += " " + d
        lines.append(line)
    b = sl.get("bible") or {}
    bible = "; ".join(f"{k.replace('_', ' and ')}: {v}" for k, v in b.items() if v) if isinstance(b, dict) else str(b)
    return lines, bible
