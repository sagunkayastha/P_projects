"""Reference sheets for klein: several pictures of one character packed into one image (one reference slot),
each cut to head + upper body so klein takes the face, hair and clothes from it but not the full-body pose
(it copied the source picture's standing pose into panels)."""
import io

from PIL import Image

UPPER = 0.62  # share of the figure's height kept from the top (head to about the hips)


def content_box(im):
    """Box of the drawn figure: everything clearly darker than the white background."""
    g = im.convert("L")
    mask = g.point(lambda v: 255 if v < 235 else 0)
    box = mask.getbbox()
    return box or (0, 0, im.width, im.height)


def upper(im, frac=UPPER):
    x0, y0, x1, y1 = content_box(im)
    h = y1 - y0
    if h < 0.5 * im.height:  # not a standing figure on white (a scene, a close-up): keep it whole
        return im
    pad = int(0.03 * im.height)
    return im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y0 + int(h * frac))))


def sheet(pngs, tile_h=640, gap=24, crop=True):
    """PNG bytes of the pictures side by side (each cut to the upper body when crop) on white."""
    tiles = []
    for data in pngs:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        if crop:
            im = upper(im)
        k = tile_h / im.height
        tiles.append(im.resize((max(1, round(im.width * k)), tile_h), Image.LANCZOS))
    w = sum(t.width for t in tiles) + gap * (len(tiles) + 1)
    out = Image.new("RGB", (w, tile_h + 2 * gap), "white")
    x = gap
    for t in tiles:
        out.paste(t, (x, gap))
        x += t.width + gap
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


