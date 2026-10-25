"""Real motion blur: the frame dragged along the direction it is travelling.

The whip pan used to be a *smear*: the finished frame was squashed horizontally
and blended over itself. That says "the camera moved" the way a badly cut GIF
says it — everything stretches, including the parts that should stay round, and
the streak runs left-right even when the camera goes up.

This is the real thing, and it is cheap: the frame is shifted along the camera's
velocity in a handful of sub-steps and averaged. A point that moved 40 px during
the exposure is drawn as a 40 px streak *along its path*, and a point that did
not move is unchanged — which is exactly what a shutter does.

``direction`` is the screen-space velocity of the *world* during the frame, in
pixels: the negative of the camera's own motion.
"""
from __future__ import annotations

import numpy as np
from PIL import Image


def directional(img: Image.Image, dx: float, dy: float, samples: int = 5,
                weight: float = 1.0) -> Image.Image:
    """Average the frame over ``samples`` positions along (dx, dy).

    ``dx``/``dy`` are the *world* displacement over the exposure. Two things
    keep it cheap enough to run on every frame of a whip: the frame is padded
    once by edge replication (so a shifted copy never brings the far side of the
    picture in, which is what a ``roll`` would do), and the accumulation is
    unsigned 16-bit rather than float, which is eight times less memory traffic
    for the same result at 8 bits per channel.
    """
    if weight <= 0.02 or (abs(dx) < 0.75 and abs(dy) < 0.75):
        return img
    a = np.asarray(img._Image__img if hasattr(img, "_Image__img") else img)
    if a.ndim != 3:
        return img
    h, w = a.shape[:2]
    pad = int(max(abs(dx), abs(dy))) + 2
    big = np.pad(a, ((pad, pad), (pad, pad), (0, 0)), mode="edge")
    acc = big[pad:pad + h, pad:pad + w].astype(np.uint16)
    n = max(2, samples)
    for i in range(1, n):
        f = i / (n - 1) - 0.5
        sx = int(round(dx * f))
        sy = int(round(dy * f))
        acc += big[pad + sy:pad + sy + h, pad + sx:pad + sx + w]
    out = (acc // n).astype(np.uint8)
    if weight >= 0.999:
        return Image.fromarray(out)
    mixed = (a.astype(np.uint16) * int((1.0 - weight) * 256) +
             out.astype(np.uint16) * int(weight * 256)) >> 8
    return Image.fromarray(mixed.astype(np.uint8))


def shutter(cam, prev_centre, unit: float) -> tuple:
    """World displacement on screen for one frame, in pixels.

    ``cam`` is the finished camera state; ``prev_centre`` the camera centre one
    frame earlier; ``unit`` the pixels-per-design-unit of the frame (the canvas
    already knows it). The world moves opposite to the camera.
    """
    x, y = cam["x"], cam["y"]
    px, py = prev_centre
    return (-(x - px) * unit, -(y - py) * unit)
