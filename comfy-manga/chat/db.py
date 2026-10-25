"""On-disk SQLite store for the manga app (chats, messages, jobs, images, characters, pages).

Lives in APP_DIR (default /data/manga/app = ~/Documents/Personal/manga/app, mode 700), so nothing
is lost when the app or ComfyUI restarts. Every write bumps `rev`; clients long-poll /api/wait on it.
"""
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

APP_DIR = Path(os.environ.get("APP_DIR", "/data/manga/app"))

_lock = threading.RLock()
_conn = None
_cond = threading.Condition()
_rev = 0
STORE = ""

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, title TEXT);
CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, ts REAL,
    text TEXT, shape TEXT, chars TEXT, job_id INTEGER, ckey TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, kind TEXT, status TEXT,
    params TEXT, prompt_id TEXT, progress INTEGER DEFAULT 0, total INTEGER DEFAULT 0, error TEXT,
    image_id INTEGER, owner TEXT, started REAL, finished REAL, attempts INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS images (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, path TEXT, w INTEGER,
    h INTEGER, source TEXT, prompt TEXT, job_id INTEGER, meta TEXT, origin TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS characters (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, slug TEXT UNIQUE,
    name TEXT, source_image INTEGER, status TEXT, refs TEXT, scores TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS pages (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, chars TEXT, lines TEXT,
    panels TEXT, image_id INTEGER, status TEXT, error TEXT, writer TEXT);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS msg_chat ON messages(chat_id);
"""

JSON_COLS = {"params", "chars", "meta", "refs", "scores", "lines", "panels", "scene"}


def init():
    global _conn
    APP_DIR.mkdir(parents=True, exist_ok=True)
    for sub in ("", "images", "thumbs", "characters", "pages"):
        d = APP_DIR / sub
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
    _conn = sqlite3.connect(str(APP_DIR / "app.db"), check_same_thread=False, isolation_level=None)
    _conn.row_factory = sqlite3.Row
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.executescript(SCHEMA)
    # a random id per store: picture URLs carry it, so a phone never shows a cached picture of another store
    # (picture ids start at 1 again in a fresh private store)
    _conn.execute("INSERT OR IGNORE INTO meta (k, v) VALUES ('store', lower(hex(randomblob(6))))")
    global STORE
    STORE = _conn.execute("SELECT v FROM meta WHERE k='store'").fetchone()[0]
    cols = {r[1] for r in _conn.execute("PRAGMA table_info(characters)")}
    if "traits" not in cols:  # added 2026-10-24: the character's looks in words
        _conn.execute("ALTER TABLE characters ADD COLUMN traits TEXT")
    pcols = {r[1] for r in _conn.execute("PRAGMA table_info(pages)")}
    for col, typ in (("bible", "TEXT"), ("scene", "TEXT"), ("seed", "INTEGER")):  # added 2026-10-24
        if col not in pcols:
            _conn.execute(f"ALTER TABLE pages ADD COLUMN {col} {typ}")


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k in JSON_COLS & d.keys():
        if d[k]:
            d[k] = json.loads(d[k])
    return d


def _enc(v):
    return json.dumps(v) if isinstance(v, (dict, list)) else v


def bump():
    global _rev
    with _cond:
        _rev += 1
        _cond.notify_all()


def rev():
    return _rev


def wait(since, timeout=25.0):
    """Block until rev != since (or timeout). Returns the current rev."""
    end = time.time() + timeout
    with _cond:
        while _rev == since:
            left = end - time.time()
            if left <= 0:
                break
            _cond.wait(left)
        return _rev


def insert(table, **f):
    f.setdefault("ts", time.time())
    cols = list(f)
    with _lock:
        cur = _conn.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                            [_enc(f[c]) for c in cols])
        rid = cur.lastrowid
    bump()
    return rid


def update(table, rid, **f):
    if not f:
        return
    with _lock:
        _conn.execute(f"UPDATE {table} SET {', '.join(c + '=?' for c in f)} WHERE id=?",
                      [_enc(v) for v in f.values()] + [rid])
    bump()


def get(table, rid):
    with _lock:
        return _row(_conn.execute(f"SELECT * FROM {table} WHERE id=?", (rid,)).fetchone())


def query(sql, args=()):
    with _lock:
        return [_row(r) for r in _conn.execute(sql, args).fetchall()]


def one(sql, args=()):
    rows = query(sql, args)
    return rows[0] if rows else None
