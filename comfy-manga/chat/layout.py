"""One manga page from 4 panel pictures: panels of different sizes/shapes, white gutters,
read right-to-left (1 top, 2 right, 3 left, 4 bottom), optional speech bubbles."""
import io
import re
import textwrap

from PIL import Image, ImageDraw, ImageFont

W, H = 1500, 2250
M, G = 60, 28
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _panels():
    x0, x1 = M, W - M
    avail = H - 2 * M - 2 * G
    h1, h2 = int(avail * 0.28), int(avail * 0.42)
    y1 = M + h1
    y2a, y2b = y1 + G, y1 + G + h2
    y3 = y2b + G
    top_split = x0 + int((x1 - x0) * 0.42)   # slanted gutter between panels 2 and 3
    bot_split = x0 + int((x1 - x0) * 0.35)
    g = G // 2
    return [
        [(x0, M), (x1, M), (x1, y1), (x0, y1)],                                              # 1 top, full width
        [(top_split + g, y2a), (x1, y2a), (x1, y2b), (bot_split + g, y2b)],                  # 2 right (big)
        [(x0, y2a), (top_split - g, y2a), (bot_split - g, y2b), (x0, y2b)],                  # 3 left (narrow)
        [(x0, y3), (x1, y3), (x1, H - M), (x0, H - M)],                                      # 4 bottom
    ]


PANELS = _panels()


def bbox(poly):
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


def aspects():
    out = []
    for poly in PANELS:
        a, b, c, d = bbox(poly)
        out.append((c - a) / (d - b))
    return out


QUOTE = re.compile(r'["“”«»]([^"“”«»]+)["“”«»]')


def split_line(line):
    """'Mia runs. "Wait!"' -> ('Mia runs.', ['Wait!'])"""
    quotes = [q.strip() for q in QUOTE.findall(line) if q.strip()]
    scene = QUOTE.sub("", line).strip(" ,;:-")
    return scene or line.strip(), quotes[:2]


def _band(lines):
    """How many blank lines (near-white and flat) a list of pixel lines starts with."""
    n = 0
    for px in lines:
        mean = sum(px) / len(px)
        if mean < 245 or max(px) - min(px) > 40:
            break
        n += 1
    return n


def trim_letterbox(im):
    """klein sometimes draws a wide picture with white bars above and below (or a tall one with bars left
    and right) inside the panel's frame. Cut such bars (blank on both sides, each >= 4%) so the panel is filled."""
    k = 256 / max(im.size)
    sm = im.convert("L").resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.BILINEAR)
    w, h = sm.size
    px = list(sm.getdata())
    rows = [px[y * w:(y + 1) * w] for y in range(h)]
    cols = [px[x::w] for x in range(w)]
    top, bot, lef, rig = _band(rows), _band(rows[::-1]), _band(cols), _band(cols[::-1])
    box = [0, 0, w, h]
    if top >= 0.04 * h and bot >= 0.04 * h and top + bot < 0.8 * h:
        box[1], box[3] = top, h - bot
    if lef >= 0.04 * w and rig >= 0.04 * w and lef + rig < 0.8 * w:
        box[0], box[2] = lef, w - rig
    if box == [0, 0, w, h]:
        return im
    x0, y0 = round(box[0] / k), round(box[1] / k)
    x1, y1 = min(im.width, round(box[2] / k)), min(im.height, round(box[3] / k))
    return im.crop((x0, y0, x1, y1))


def _cover(im, w, h):
    s = max(w / im.width, h / im.height)
    im = im.resize((max(w, round(im.width * s)), max(h, round(im.height * s))), Image.LANCZOS)
    left, top = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((left, top, left + w, top + h))


def _bubble(draw, box, text, right):
    a, b, c, d = box
    pw = c - a
    font = ImageFont.truetype(FONT, 34 if pw > 700 else 28)
    chars = max(8, int(pw * 0.38 / (font.size * 0.6)))
    lines = textwrap.wrap(text, chars)[:5]
    lh = int(font.size * 1.25)
    tw = max(draw.textlength(ln, font=font) for ln in lines)
    th = lh * len(lines)
    bw, bh = int(tw * 1.35 + 40), int(th * 1.45 + 30)
    x = c - bw - 24 if right else a + 24
    y = b + 22
    tail_x = x + bw * (0.3 if right else 0.7)
    draw.polygon([(tail_x - 18, y + bh - 12), (tail_x + 18, y + bh - 12), (tail_x + (-30 if right else 30), y + bh + 46)],
                 fill="white", outline="black")
    draw.ellipse((x, y, x + bw, y + bh), fill="white", outline="black", width=4)
    draw.polygon([(tail_x - 15, y + bh - 16), (tail_x + 15, y + bh - 16), (tail_x + (-26 if right else 26), y + bh + 38)],
                 fill="white")
    ty = y + (bh - th) // 2
    for ln in lines:
        lw = draw.textlength(ln, font=font)
        draw.text((x + (bw - lw) / 2, ty), ln, font=font, fill="black")
        ty += lh


def compose(panel_pngs, quotes):
    """panel_pngs: 4 PNG byte strings (or None for a missing panel); quotes: 4 lists of speech strings."""
    page = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(page)
    for i, poly in enumerate(PANELS):
        a, b, c, d = bbox(poly)
        if panel_pngs[i]:
            im = _cover(trim_letterbox(Image.open(io.BytesIO(panel_pngs[i])).convert("RGB")), c - a, d - b)
            mask = Image.new("L", (c - a, d - b), 0)
            ImageDraw.Draw(mask).polygon([(x - a, y - b) for x, y in poly], fill=255)
            page.paste(im, (a, b), mask)
        else:
            draw.polygon(poly, fill=(235, 235, 235))
        draw.polygon(poly, outline="black", width=6)
    for i, poly in enumerate(PANELS):
        for k, q in enumerate(quotes[i] if i < len(quotes) else []):
            _bubble(draw, bbox(poly), q, right=(k == 0))
    buf = io.BytesIO()
    page.save(buf, "PNG", optimize=True)
    return buf.getvalue()
