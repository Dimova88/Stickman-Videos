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
BAND = 0.20

_cache: dict = {}


def _rock(d, rng, x, y, w, h, col):
    """A lump of rock: a polygon with a flat base and a broken top."""
    pts = [(x, y)]
    n = max(4, int(w / 26))
    for i in range(n + 1):
        u = i / n
        px = x + w * u
        py = y - h * (0.25 + 0.75 * math.sin(math.pi * u) ** 0.7) * rng.uniform(0.7, 1.15)
        pts.append((px, py))
    pts.append((x + w, y))
    d.polygon(pts, fill=col)


def _pine(d, rng, x, y, h, col):
    w = h * rng.uniform(0.30, 0.42)
    for tier in range(3):
        v = 1.0 - tier * 0.24
        top = y - h * (1.0 - tier * 0.22)
        d.polygon([(x, top), (x - w * v * 0.5, top + h * 0.55), (x, top + h * 0.44),
                   (x + w * v * 0.5, top + h * 0.55)], fill=col)
    d.rectangle([x - w * 0.06, y - h * 0.16, x + w * 0.06, y], fill=col)


def foreground(set_name: str, w: int, h: int) -> Image.Image:
    """The near layer, ``2.6`` frames wide and ``1.5`` tall, cached."""
    key = ("fg", set_name, w, h)
    if key in _cache:
        return _cache[key]
    lw, lh = int(w * 2.6), int(h * 1.5)
    rng = random.Random(7 if set_name == "mountain" else 19)
    img = Image.new("RGB", (lw, lh), (0, 0, 0))
    mask = Image.new("L", (lw, lh), 0)
    d = ImageDraw.Draw(mask)

    # the visible window sits in the middle of the layer, so the silhouettes
    # have to stand on the window's bottom edge, not on the layer's
    base = (lh + h) * 0.5 - 2
    # the band: a soft ridge of ground that never rises far into the frame
    step = max(40, w // 26)
    ridge = []
    for x in range(-step, lw + step, step):
        rise = rng.uniform(0.0, 0.55) * h * BAND * 0.55
        ridge.append((x, base - rise))
    poly = [(x, lh + 10) for x, _ in ridge] + list(reversed(ridge))
    d.polygon(poly, fill=225)

    if set_name == "mountain":
        for _ in range(int(lw / 150)):
            x = rng.uniform(0, lw)
            _rock(d, rng, x - 90, base, rng.uniform(110, 230), rng.uniform(40, 120), 255)
        for _ in range(int(lw / 110)):
            x = rng.uniform(0, lw)
            _pine(d, rng, x, base - rng.uniform(0, 14), rng.uniform(60, 150), 255)
    else:
        # dunes: long, low, and much softer than rock
        for _ in range(int(lw / 260)):
            x = rng.uniform(0, lw)
            ww = rng.uniform(260, 520)
            d.pieslice([x, base - ww * 0.30, x + ww, base + ww * 0.30], 180, 360, fill=235)
        for _ in range(int(lw / 420)):
            x = rng.uniform(0, lw)
            _rock(d, rng, x - 70, base, rng.uniform(90, 170), rng.uniform(36, 78), 255)

    mask = mask.filter(ImageFilter.GaussianBlur(w * 0.006))
    # it is a near-lens element: out of focus, and never fully opaque
    alpha = mask.point(lambda v: int(v * 0.80))
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
