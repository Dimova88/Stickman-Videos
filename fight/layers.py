"""Depth: a foreground layer that moves against the camera.

The landscape is one painted plate, so on its own it can only ever be a backdrop.
Two things give it depth:

* the plate is cropped **behind** the camera (36 % of its travel), so the scenery
  lags the fighters — that is the parallax the eye reads first;
* a near-camera layer of rock and brush sits **in front** of everything and
  travels at 175 % of the camera, out of focus, dark, only along the bottom of
  the frame. It is what turns a pan into a move through space.

The layer is drawn procedurally, twice as wide as the frame, so it is all
original geometry and it costs one crop and one alpha paste per frame.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

#: how much faster than the camera the near layer travels
PARALLAX = 1.75
#: how much of the frame height the layer is allowed to reach
BAND = 0.13

_cache: dict = {}


def _boulder(d, rng, x, y, w, h, col):
    """One big angular lump, flat on the ground line.

    Small repeated bumps along the bottom edge read as a row of heads — an
    audience sitting in the dark — so the near layer is a handful of large
    corners instead: a ledge we are standing behind, not a crowd.
    """
    n = rng.randint(4, 6)
    pts = [(x, y)]
    for i in range(n + 1):
        u = i / n
        px = x + w * u
        py = y - h * (0.30 + 0.70 * math.sin(math.pi * u) ** 0.5) * rng.uniform(0.75, 1.2)
        pts.append((px, py))
    pts.append((x + w, y))
    d.polygon(pts, fill=col)


def _ledge(d, rng, base, lw, h, span, col, soft: bool):
    """The near edge of the ground: a long angular silhouette.

    ``soft`` gives the desert its dune curve; anything else is broken rock, but
    both are made of a few long slopes so nothing in the band can be mistaken
    for a line of small figures.
    """
    step = max(240, lw // 5)
    pts = []
    x = -step
    while x < lw + step:
        level = span * (0.35 if soft else rng.uniform(0.10, 1.0))
        if soft:
            level = span * (0.30 + 0.35 * math.sin(x / (lw * 0.42) * math.pi))
        pts.append((x, base - level))
        x += step * (0.7 if soft else rng.uniform(0.45, 1.0))
    poly = [(px, base + h) for px, _ in pts] + list(reversed(pts))
    d.polygon(poly, fill=col)


def foreground(set_name: str, w: int, h: int) -> Image.Image:
    """The near layer, ``2.6`` frames wide and ``1.5`` tall, cached."""
    key = ("fg", set_name, w, h)
    if key in _cache:
        return _cache[key]
    lw, lh = int(w * 2.6), int(h * 1.5)
    rng = random.Random(7 if set_name == "mountain" else 19)
    mask = Image.new("L", (lw, lh), 0)
    d = ImageDraw.Draw(mask)

    # the visible window sits in the middle of the layer, so the ledge has to
    # stand on the window's bottom edge, not on the layer's
    base = (lh + h) * 0.5 - 2
    span = h * BAND * 0.85
    _ledge(d, rng, base, lw, lh, span, 235, soft=(set_name != "mountain"))
    # two or three big corners breaking the line
    for _ in range(max(2, int(lw / 900))):
        x = rng.uniform(-w * 0.2, lw - w * 0.2)
        _boulder(d, rng, x, base, rng.uniform(w * 0.26, w * 0.52),
                 rng.uniform(span * 0.55, span * 1.15), 255)

    mask = mask.filter(ImageFilter.GaussianBlur(w * 0.006))
    # it is a near-lens element: out of focus, and never fully opaque
    alpha = mask.point(lambda v: int(v * 0.66))
    img = Image.new("RGB", (lw, lh), (0, 0, 0))
    layer = Image.merge("RGBA", (*img.split(), alpha))
    tint = Image.new("RGB", (lw, lh), (14, 12, 15))
    layer = Image.composite(tint.convert("RGBA"), Image.new("RGBA", (lw, lh), (0, 0, 0, 0)),
                            mask).convert("RGBA")
    layer.putalpha(alpha)
    layer = layer.filter(ImageFilter.GaussianBlur(max(2.0, w * 0.0045)))
    _cache[key] = layer
    return layer


def draw_foreground(cv, cam: dict, set_name: str) -> None:
    """Crop the near layer where the parallax puts it and lay it over the frame."""
    if cam.get("foreground", 1.0) <= 0.01:
        return
    w, h = cv.w, cv.h
    layer = foreground(set_name, w, h)
    fx = (cam["x"] - w * 0.5) * PARALLAX
    fy = (cam["y"] - h * 0.5) * PARALLAX * 0.55
    x0 = int(round((layer.width - w) * 0.5 - fx))
    y0 = int(round((layer.height - h) * 0.5 - fy))
    x0 = min(max(0, x0), layer.width - w)
    y0 = min(max(0, y0), layer.height - h)
    piece = layer.crop((x0, y0, x0 + w, y0 + h))
    if cam.get("foreground", 1.0) < 0.99:
        a = piece.split()[3].point(lambda v: int(v * cam["foreground"]))
        piece.putalpha(a)
    cv.flush()
    cv.img.paste(piece, (0, 0), piece)
