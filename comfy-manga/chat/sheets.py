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


def plain(im):
    """True when the picture is a figure on a plain light background (its border is near-white and flat).
    A source picture with a scene behind the character is not: cutting its 'upper part' can cut the
    character out."""
    g = im.convert("L").resize((128, max(1, round(128 * im.height / im.width))))
    w, h = g.size
    px = list(g.getdata())
    border = px[:w] + px[-w:] + [px[y * w] for y in range(h)] + [px[y * w + w - 1] for y in range(h)]
    mean = sum(border) / len(border)
    return mean > 230 and sum(1 for v in border if v < 200) < 0.05 * len(border)


def upper(im, frac=UPPER):
    x0, y0, x1, y1 = content_box(im)
    h = y1 - y0
    if h < 0.5 * im.height:  # not a standing figure on white (a scene, a close-up): keep it whole
        return im
    pad = int(0.03 * im.height)
    return im.crop((max(0, x0 - pad), max(0, y0 - pad), min(im.width, x1 + pad), min(im.height, y0 + int(h * frac))))


def sheet(pngs, tile_h=640, gap=24, crop=True):
    """PNG bytes of the pictures side by side (each cut to the upper body when crop) on white. Pictures with a
    scene background are left out when there are plain ones (the views of a saved character are plain)."""
    ims = [Image.open(io.BytesIO(d)).convert("RGB") for d in pngs]
    if crop:
        flat = [im for im in ims if plain(im)]
        ims = flat or ims
    tiles = []
    for im in ims:
        if crop and plain(im):
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


