"""SQLite message history for the chat app (stdlib only)."""
import json
import sqlite3
import threading
import time

DB = "/data/chat.db"
_lock = threading.Lock()
_conn = None

FIELDS = ["status", "progress", "total", "model", "kind", "filename", "error", "elapsed"]


def init():
    global _conn
    _conn = sqlite3.connect(DB, check_same_thread=False)
    _conn.row_factory = sqlite3.Row
    with _conn:
        _conn.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, prompt TEXT, mode TEXT, quality TEXT, image TEXT,
            model TEXT, kind TEXT, seed INTEGER, params TEXT,
            status TEXT, progress INTEGER, total INTEGER,
            filename TEXT, error TEXT, elapsed REAL)""")


def add(prompt, mode, quality, image, params):
    with _lock, _conn:
        cur = _conn.execute(
            "INSERT INTO messages (ts,prompt,mode,quality,image,model,kind,seed,params,"
            "status,progress,total) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (time.time(), prompt, mode, quality, image, params["model"], params["kind"],
             params["seed"], json.dumps(params), "queued", 0, 0))
        return cur.lastrowid


def update(mid, **fields):
    cols = [f for f in fields if f in FIELDS]
    if not cols:
        return
    sets = ", ".join(f"{c}=?" for c in cols)
    with _lock, _conn:
        _conn.execute(f"UPDATE messages SET {sets} WHERE id=?", [fields[c] for c in cols] + [mid])


def get(mid):
    row = _conn.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    return dict(row) if row else None


def feed(limit=50):
    rows = _conn.execute("SELECT * FROM messages ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in reversed(rows)]


def unfinished_ids():
    rows = _conn.execute("SELECT id FROM messages WHERE status IN ('queued','running')").fetchall()
    return [r["id"] for r in rows]
