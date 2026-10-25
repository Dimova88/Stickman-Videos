"""Grade the sunset plates to the blue hour, so a film can be shot at night.

The painted plates are the only backdrops the project owns, and the third film
needs a night that is not a filter: a filter would keep the sky the brightest
thing in frame and the fighters would still read as silhouettes against daylight.
So the grade does three things in order —

1. **the sky is rebuilt**, not multiplied: a vertical ramp from near-black blue
   at the top to a cold violet at the horizon, with the original clouds lifted
   out of it as a soft texture;
2. **the sun becomes a low moon**: the disc is kept and tinted, the warm bloom
   around it is cooled, and the rim light it threw on the peaks is dragged down
   so the ridge reads as a black shape, not a lit one;
3. **stars and a ground that is almost out of light**, with just enough value in
   the stone to read the cracks.

    .venv/bin/python tools/make_night_plates.py
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")

#: the sun in ``mountain_background.png``, in pixels of the 1376x768 plate
SUN = (556.0, 253.0)
SUN_R = 42.0
#: where the moon goes: high, left of the ridge, clear of the pines
MOON = (452.0, 128.0)
MOON_R = 27.0


def smoothstep(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def sky_ramp(h: int, w: int) -> np.ndarray:
    """The new sky, top to horizon: near-black blue into a cold violet."""
    top = np.array([9.0, 13.0, 30.0])
    mid = np.array([30.0, 40.0, 78.0])
    hor = np.array([86.0, 78.0, 108.0])
    y = np.linspace(0.0, 1.0, h)[:, None]
    col = np.empty((h, 3), dtype=np.float32)
    for c in range(3):
        a = top[c] + (mid[c] - top[c]) * np.clip(y[:, 0] / 0.55, 0, 1)
        b = mid[c] + (hor[c] - mid[c]) * np.clip((y[:, 0] - 0.55) / 0.45, 0, 1)
        col[:, c] = np.where(y[:, 0] < 0.55, a, b)
    return np.broadcast_to(col[:, None, :], (h, w, 3)).copy()


def stars(w: int, h: int, horizon: int, n: int = 340, seed: int = 1904) -> Image.Image:
    """A deterministic star field, denser high up and thinning to the horizon."""
    rng = np.random.default_rng(seed)
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    for _ in range(n):
        x = rng.uniform(0, w)
        y = rng.uniform(0, horizon * 0.92)
        fade = 1.0 - (y / (horizon * 0.92)) ** 1.7
        if rng.random() > fade * 0.95 + 0.05:
            continue
        r = rng.uniform(0.5, 1.5)
        v = int(120 + 120 * fade * rng.uniform(0.4, 1.0))
        d.ellipse((x - r, y - r, x + r, y + r), fill=v)
    return layer.filter(ImageFilter.GaussianBlur(0.45))


def grade_far(path: str, out: str) -> None:
    im = Image.open(path).convert("RGB")
    w, h = im.size
    a = np.asarray(im).astype(np.float32) / 255.0

    lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    # where the sky is: everything above the ridge line of the plate
    horizon = int(h * 0.62)
    sky = sky_ramp(h, w)
    # the painted clouds survive as *texture*: their detail, not their colour
    detail = (lum - np.clip(lum, 0.30, 1.0).mean()) * 90.0
    sky = np.clip(sky + detail[:, :, None] * 0.55, 0, 255) / 255.0

    y = np.arange(h)[:, None]
    sky_mix = np.clip((horizon - y) / (horizon * 0.55), 0, 1) ** 0.7
    out_a = a * (1.0 - sky_mix[:, :, None]) + sky * sky_mix[:, :, None]

    # the peaks: black-blue, lit only on the very top edge
    ridge = out_a.copy()
    ramp = np.array([0.30, 0.34, 0.52], dtype=np.float32)
    ridge = ridge * ramp + np.array([0.02, 0.03, 0.06], dtype=np.float32)
    edge = np.clip((lum - 0.62) * 3.4, 0, 1) * np.clip((y - horizon * 0.55) / 90.0, 0, 1)
    ridge = ridge + edge[:, :, None] * np.array([0.34, 0.30, 0.36], dtype=np.float32)

    # the sun's own bloom is the one thing that must go: it is a daylight cue
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    dist = np.hypot(xx - SUN[0], yy - SUN[1]) / (SUN_R * 5.2)
    bloom = np.clip(1.0 - dist, 0, 1) ** 2
    out_a = ridge * (1.0 - 0.55 * bloom[:, :, None]) + sky * (0.55 * bloom[:, :, None])

    # the old sun is *painted out*, not dimmed: two moons in one sky is the one
    # thing an audience will never forgive
    disc = np.clip((SUN_R * 3.2 - np.hypot(xx - SUN[0], yy - SUN[1])) / (SUN_R * 1.4), 0, 1)
    disc = disc * disc * (3.0 - 2.0 * disc)
    out_a = out_a * (1.0 - disc[:, :, None]) + sky * disc[:, :, None]

    img = Image.fromarray((np.clip(out_a, 0, 1) * 255).astype(np.uint8))
    img = img.filter(ImageFilter.GaussianBlur(0.4))

    # the real moon, high and clean, with the halo of a hazy night
    halo = Image.new("L", (w, h), 0)
    hd = ImageDraw.Draw(halo)
    for i, (r, v) in enumerate(((MOON_R * 4.2, 26), (MOON_R * 2.6, 40),
                                (MOON_R * 1.7, 58), (MOON_R * 1.15, 90))):
        hd.ellipse((MOON[0] - r, MOON[1] - r, MOON[0] + r, MOON[1] + r), fill=v)
    halo = halo.filter(ImageFilter.GaussianBlur(18))
    img = Image.composite(Image.new("RGB", (w, h), (196, 206, 236)), img, halo)

    md = ImageDraw.Draw(img)
    md.ellipse((MOON[0] - MOON_R, MOON[1] - MOON_R, MOON[0] + MOON_R, MOON[1] + MOON_R),
               fill=(238, 240, 250))
    # two craters, because a flat white circle is a hole in the sky
    for (dx, dy, r) in ((-7, -5, 6.0), (6, 7, 4.0), (8, -9, 3.0)):
        md.ellipse((MOON[0] + dx - r, MOON[1] + dy - r,
                    MOON[0] + dx + r, MOON[1] + dy + r), fill=(214, 218, 232))

    st = stars(w, h, int(h * 0.40))
    img = Image.composite(Image.new("RGB", (w, h), (206, 214, 240)), img, st)

    img.save(out)
    print(f"[night] {os.path.basename(out)} {img.size}")


def grade_ground(path: str, out: str) -> None:
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.float32) / 255.0
    lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    # value first: the stone keeps its cracks, loses its daylight
    v = np.clip(lum * 1.10 + 0.015, 0, 1) ** 1.28
    tint = np.array([0.34, 0.36, 0.46], dtype=np.float32)
    out_a = v[:, :, None] * tint * np.array([1.05, 1.0, 1.12], dtype=np.float32)
    # a cold rim from the moon on the top-left quadrant
    h, w = lum.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.hypot((xx - w * 0.30) / (w * 0.55), (yy - h * 0.15) / (h * 0.6))
    rim = np.clip(1.0 - d, 0, 1) ** 2 * 0.20
    out_a = out_a + rim[:, :, None] * np.array([0.55, 0.58, 0.72], dtype=np.float32)
    img = Image.fromarray((np.clip(out_a, 0, 1) * 255).astype(np.uint8))
    img.save(out)
    print(f"[night] {os.path.basename(out)} {img.size}")


def main() -> int:
    grade_far(os.path.join(ASSETS, "mountain_background.png"),
              os.path.join(ASSETS, "night_background.png"))
    grade_ground(os.path.join(ASSETS, "ground_mountain.png"),
                 os.path.join(ASSETS, "ground_night.png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
