"""The two shots that cannot be a crop: a fist at the lens, and a shoulder.

Both of them break the flat side-on projection the rest of the film is drawn in,
and both are pure geometry, so they cost nothing to draw and nothing to generate:

The foreshortened punch is not in here: the first version drew a big hand in
front of the lens and it read as a blue blob. The camera dives at the striking
fist instead (see ``camera.SHOTS``, the ``rush`` anchor) — same effect, and the
hand stays the hand the rest of the film is built from.

``draw_ots``
    Over the shoulder: the fighter whose back we are behind becomes a dark,
    defocused mass filling one edge of the frame, with a warm rim light on the
    side facing the fight. The opponent is drawn normally in the mid-ground,
    so the near body needs no rig at all: it is one blurred patch with a mask.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def _dark(colour, f: float = 0.20):
    return tuple(int(c * f) for c in colour[:3])


# ------------------------------------------------------- over-the-shoulder
_ots_cache: dict = {}


def draw_ots(cv, side: str, colour, blur: float = 9.0) -> None:
    """A dark shoulder and head filling one edge of the frame.

    ``side`` is ``"left"`` or ``"right"``: the edge the near fighter is on. The
    mass has to be big — a third of the frame wide, a head half the frame tall
    — or it reads as a vignette instead of a body in front of the lens. Focus
    is on the far fighter, so the whole patch is blurred, and the only thing
    that reads is the warm rim light where the sun grazes the shoulder.
    """
    w, h = cv.w, cv.h
    key = (w, h, side, tuple(colour), blur)
    hit = _ots_cache.get(key)
    if hit is None:
        hit = _build_ots(w, h, side, colour, blur)
        _ots_cache[key] = hit
    patch, mask = hit
    cv.flush()
    x = 0 if side == "left" else w - patch.width
    cv.img.paste(patch, (x, 0), mask)
    cv.d = ImageDraw.Draw(cv.img)
    cv._draw = None


def _build_ots(w: int, h: int, side: str, colour, blur: float):
    """The shoulder patch, built once per (size, side, colour).

    Nothing in it moves, so a shot re-uses the same two images and the cost per
    frame is a single masked paste instead of two Gaussian blurs.

    Shape matters more than shading: a circle reads as a balloon, so the mass is
    a skull (slightly egg-shaped, with the ear and jaw on the fight side), a
    trapezius, and a mantle of shoulder that runs off the bottom of the frame.
    Everything is nearly black — the near fighter is a silhouette, not a figure
    — and the only light on it is the warm rim where the sun grazes the edge.
    """
    pw = int(w * 0.38)
    mask = Image.new("L", (pw, h), 0)
    d = ImageDraw.Draw(mask)
    # -1 when the near fighter is on the right of frame, +1 on the left
    fight = 1 if side == "left" else -1
    hx = (pw * 0.34) if side == "left" else (pw * 0.66)
    hy = h * 0.42
    r = h * 0.31

    # skull: back of the head, a touch egg-shaped, with a jaw coming forward
    d.ellipse([hx - r * 0.74, hy - r * 1.02, hx + r * 0.78, hy + r * 0.92],
              fill=255)
    d.ellipse([hx + fight * r * 0.30 - r * 0.30, hy + r * 0.24,
               hx + fight * r * 0.30 + r * 0.46, hy + r * 0.86], fill=255)
    # the ear, which is the one landmark that says "head" from behind
    d.ellipse([hx + fight * r * 0.42 - r * 0.20, hy - r * 0.10,
               hx + fight * r * 0.42 + r * 0.26, hy + r * 0.42], fill=255)
    # neck
    d.polygon([(hx - r * 0.26, hy + r * 0.70), (hx + fight * r * 0.30, hy + r * 0.66),
               (hx + fight * r * 0.44, hy + r * 1.16), (hx - r * 0.34, hy + r * 1.20)],
              fill=255)
    # trapezius and the shoulder running out of the bottom corner
    d.polygon([(hx - fight * r * 0.34, hy + r * 1.10), (hx + fight * r * 0.54, hy + r * 1.06),
               (hx + fight * r * 1.15, hy + r * 1.55), (hx + fight * r * 1.60, h + r),
               (hx - fight * r * 1.90, h + r), (hx - fight * r * 1.10, hy + r * 1.50)],
              fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(blur))
    base = _dark(colour, 0.11)
    patch = Image.new("RGB", (pw, h), base)

    # the rim: one arc on the skull, one along the top of the shoulder, both
    # only on the side the light comes from
    rim = Image.new("RGB", (pw, h), (0, 0, 0))
    rd = ImageDraw.Draw(rim)
    lw = max(8, int(h * 0.042))
    box = [hx - r * 0.74, hy - r * 1.02, hx + r * 0.78, hy + r * 0.92]
    if side == "left":
        rd.arc(box, 292, 62, fill=(255, 214, 168), width=lw)
        rd.line([(hx + r * 0.40, hy + r * 1.10), (hx + r * 1.25, hy + r * 1.62)],
                fill=(255, 200, 152), width=lw)
    else:
        rd.arc(box, 118, 248, fill=(255, 214, 168), width=lw)
        rd.line([(hx - r * 0.40, hy + r * 1.10), (hx - r * 1.25, hy + r * 1.62)],
                fill=(255, 200, 152), width=lw)
    rim = rim.filter(ImageFilter.GaussianBlur(blur * 1.15))
    patch = Image.fromarray(
        np.clip(np.asarray(patch, np.float32) +
                np.asarray(rim, np.float32) * 0.62, 0, 255).astype(np.uint8))
    return patch, mask
