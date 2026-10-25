"""Export the fight's original art as standalone PNG assets.

Every picture the renderer draws is procedural, which means the pieces can also
be saved on their own: the katana, the crescent a swing leaves behind, the spark
burst, the ink glyph wall. They are written to ``assets/steel`` and
``assets/ink`` with an alpha channel so they can be dropped into a thumbnail,
a title card or a future film without re-running a fight.

    .venv/bin/python tools/make_assets.py

Regenerating is deterministic: no randomness outside fixed seeds.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from fight import steelblade, vfx
from fight.draw import Canvas, Cam

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")


def _page(w: int, h: int, cx: float = 0.0, cy: float = 0.0) -> Canvas:
    """A transparent page whose design units are one pixel wide."""
    return Canvas(w, h, Cam(x=cx, y=cy, zoom=1.0), bg=None)


def _save(cv: Canvas, path: str) -> None:
    cv.flush()
    full = os.path.join(OUT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    cv.img.save(full)
    print("[asset] %s" % os.path.relpath(full, ROOT))


# ---------------------------------------------------------------------- blade
def katana() -> None:
    """One katana, pointing right, hilt at the left. 960x200, alpha."""
    cv = Canvas(1920, 360, Cam(x=0.0, y=0.0, zoom=2.0), bg=None)
    steelblade.draw_blade(cv, (-190.0, 0.0), 0.0, 420.0, glow=0.25,
                          handle=True)
    cv.flush()
    # trim the empty margins so the PNG is the blade and nothing else
    bbox = cv.img.split()[3].getbbox()
    cv.img = cv.img.crop(bbox)
    _save(cv, "steel/katana.png")


# --------------------------------------------------------------------- slash
def slash() -> None:
    """The crescent a fast swing leaves: sampled from a real tip path."""
    w, h = 1100, 1100
    cv = _page(w, h)
    wrist = (0.0, 430.0)
    length = 430.0
    samples = []
    n = 17
    for i in range(n):
        # a downward diagonal cut, eased at both ends so the crescent has a
        # whisker of a tail and a heavy leading edge
        f = i / (n - 1)
        e = f * f * (3 - 2 * f) * 0.35 + f * 0.65
        samples.append((wrist, math.radians(-104 + 168 * e)))
    steelblade.slash_arc(cv, samples, length, 1.0, flat=True)
    cv.flush()
    bbox = cv.img.split()[3].getbbox()
    cv.img = cv.img.crop(bbox)
    _save(cv, "steel/slash_crescent.png")


# -------------------------------------------------------------------- sparks
def spark_strip() -> None:
    """Six frames of the metal-on-steel spark burst, as a horizontal strip."""
    cell = 480
    frames = 6
    out = Image.new("RGBA", (cell * frames, cell), (0, 0, 0, 0))
    for i in range(frames):
        age = i * 0.42 / (frames - 1)
        # one design unit per pixel, contact point in the middle of the cell
        one = Canvas(cell, cell, Cam(x=0.0, y=0.0, zoom=960.0 / cell), bg=None)
        steelblade.sparks(one, cell * 0.5, cell * 0.5, age, 0.9, seed=3.0)
        one.flush()
        out.alpha_composite(one.img, (i * cell, 0))
    full = os.path.join(OUT, "steel/sparks_strip.png")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    out.save(full)
    print("[asset] %s" % os.path.relpath(full, ROOT))


# ----------------------------------------------------------------------- ink
def ink_wall() -> None:
    """The calligraphy behind an impact frame, on transparent black."""
    w, h = 1280, 720
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    rng = np.random.default_rng(7)
    spots = [(0.08, 0.28, 0.60), (0.88, 0.20, 0.50), (0.16, 0.82, 0.52),
             (0.78, 0.80, 0.56)]
    for sx, sy, sc in spots:
        vfx._glyph(d, w * sx + rng.uniform(-0.03, 0.03) * w,
                   h * sy + rng.uniform(-0.03, 0.03) * h,
                   h * sc * rng.uniform(0.85, 1.1), rng)
    layer = layer.filter(ImageFilter.GaussianBlur(1.4))
    img = Image.new("RGBA", (w, h), (236, 230, 218, 0))
    img.putalpha(layer.point(lambda v: min(255, int(v * 3.0))))
    full = os.path.join(OUT, "ink/glyph_wall.png")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    img.save(full)
    print("[asset] %s" % os.path.relpath(full, ROOT))


# --------------------------------------------------------------------- sheet
def sheet() -> None:
    """A single contact sheet of everything above, for a quick look."""
    names = ["steel/katana.png", "steel/slash_crescent.png",
             "steel/sparks_strip.png", "ink/glyph_wall.png"]
    tiles = []
    for n in names:
        im = Image.open(os.path.join(OUT, n)).convert("RGBA")
        im.thumbnail((620, 220), Image.LANCZOS)
        tiles.append((n, im))
    sh = Image.new("RGB", (1280, 720), (18, 18, 20))
    d = ImageDraw.Draw(sh)
    y = 12
    for i, (n, im) in enumerate(tiles):
        x = 16 if i % 2 == 0 else 656
        if i % 2 == 0 and i:
            y += 350
        sh.paste(im, (x, y + 22), im)
        d.text((x, y + 4), n, fill=(240, 240, 240))
    full = os.path.join(OUT, "steel_assets_sheet.png")
    sh.save(full)
    print("[asset] %s" % os.path.relpath(full, ROOT))


if __name__ == "__main__":
    katana()
    slash()
    spark_strip()
    ink_wall()
    sheet()
