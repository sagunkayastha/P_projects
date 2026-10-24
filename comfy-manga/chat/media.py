"""Image files on disk: originals in APP_DIR/images/<day>/, small WebP thumbnails in APP_DIR/thumbs/."""
import hashlib
import io
import os
import shutil
import time
from pathlib import Path

from PIL import Image

import db

SIZES = {"s": 360, "m": 1080}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def save(data, source, prompt="", job_id=None, meta=None, origin=None):
    """Store PNG bytes as a new gallery image; returns its id."""
    im = Image.open(io.BytesIO(data))
    w, h = im.size
    day = time.strftime("%Y%m%d")
    rel = f"images/{day}/{int(time.time() * 1000)}-{hashlib.sha1(data).hexdigest()[:8]}.png"
    _write(db.APP_DIR / rel, data)
    iid = db.insert("images", path=rel, w=w, h=h, source=source, prompt=prompt, job_id=job_id, meta=meta or {},
                    origin=origin)
    try:
        thumb(iid)
    except Exception:
        pass  # made again on first request
    return iid


def path(iid):
    row = db.get("images", iid)
    if not row:
        raise FileNotFoundError(iid)
    return db.APP_DIR / row["path"], row


def thumb(iid, size="s"):
    px = SIZES.get(size, SIZES["s"])
    p = db.APP_DIR / "thumbs" / (f"{iid}.webp" if size == "s" else f"{iid}-{size}.webp")
    if not p.is_file():
        src, _ = path(iid)
        im = Image.open(src)
        im.thumbnail((px, px * 2))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "WEBP", quality=78)
        _write(p, buf.getvalue())
    return p


def read(iid):
    return path(iid)[0].read_bytes()


def import_folder(folder):
    """Copy every PNG/JPG/WebP under `folder` into the gallery (the folder itself is only read).
    Idempotent: a file already imported (same relative path + size) is skipped. Returns the count added."""
    folder = Path(folder)
    added = 0
    files = sorted(p for p in folder.rglob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp"))
    for f in files:
        origin = f"import:{f.relative_to(folder)}:{f.stat().st_size}"
        if db.one("SELECT id FROM images WHERE origin=?", (origin,)):
            continue
        try:
            im = Image.open(f)
            w, h = im.size
        except Exception:
            continue
        rel = f"images/import/{folder.name}/{f.relative_to(folder)}"
        dst = db.APP_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        for d in [dst.parent] + list(dst.parent.parents):
            if d == db.APP_DIR:
                break
            os.chmod(d, 0o700)
        shutil.copy2(f, dst)
        # keep the file's own time so imported pictures sort by when they were made
        db.insert("images", ts=f.stat().st_mtime, path=rel, w=w, h=h, source="import", prompt="", meta={},
                  origin=origin)
        added += 1
    return added
