"""Pivot-style renderer: antialiased sticks, flat colours, clean composition.

Everything is authored in the app's 960x540 design space and drawn at whatever
output width is asked for, so the same scene renders at 540p or 4K.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .core import SEG, SEGMENT_ORDER, Skeleton, Pose, solve

DESIGN_W, DESIGN_H = 960, 540
INK = (43, 43, 43)


class Cam:
    """Design space -> screen. ``sqy`` squashes vertically, which is how a high
    camera is faked without a second projection: the figures are drawn shorter
    than they are wide, exactly as a body looks from above."""

    def __init__(self, x: float = 480.0, y: float = 300.0, zoom: float = 1.0,
                 shake_x: float = 0.0, shake_y: float = 0.0, roll: float = 0.0,
                 sqy: float = 1.0):
        self.x, self.y, self.zoom = x, y, zoom
        self.sx, self.sy, self.roll = shake_x, shake_y, roll
        self.sqy = sqy

    def to_screen(self, p, w: int, h: int):
        k = (w / DESIGN_W) * self.zoom
        return (w * 0.5 + (p[0] - self.x + self.sx) * k,
                h * 0.5 + (p[1] - self.y + self.sy) * k * self.sqy)


class Canvas:
    """Thin wrapper over aggdraw with a camera, round caps and soft shadows."""

    def __init__(self, w: int, h: int, cam: Cam):
        self.w, self.h = w, h
        self.cam = cam
        self.img = Image.new("RGB", (w, h), (242, 240, 235))
        self.d = ImageDraw.Draw(self.img)
        self._draw = None

    # -- primitives ------------------------------------------------------
    def _agg(self):
        if self._draw is None:
            import aggdraw
            self._aggdraw = aggdraw
            self._draw = aggdraw.Draw(self.img)
        return self._draw

    def flush(self):
        if self._draw is not None:
            self._draw.flush()
            self._draw = None

    def line(self, p0, p1, w: float, color, alpha: int = 255, caps: bool = True):
        a = self._agg()
        pen = self._aggdraw.Pen(_rgba(color, alpha), w)
        a.line([p0[0], p0[1], p1[0], p1[1]], pen)
        if caps:
            r = w * 0.5
            brush = self._aggdraw.Brush(_rgba(color, alpha))
            for p in (p0, p1):
                a.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], pen, brush)

    def polyline(self, pts, w: float, color, alpha: int = 255):
        a = self._agg()
        pen = self._aggdraw.Pen(_rgba(color, alpha), w)
        flat = []
        for p in pts:
            flat += [p[0], p[1]]
        a.line(flat, pen)
        brush = self._aggdraw.Brush(_rgba(color, alpha))
        r = w * 0.5
        for p in (pts[0], pts[-1]):
            a.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], pen, brush)

    def circle(self, c, r: float, color, width: float = 0.0, fill=None, alpha: int = 255):
        a = self._agg()
        pen = self._aggdraw.Pen(_rgba(color, alpha), width) if width > 0 else None
        brush = self._aggdraw.Brush(_rgba(fill if fill is not None else color, alpha)) if (
            fill is not None or width <= 0) else None
        a.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], pen, brush)

    def disc(self, c, r: float, color):
        self.d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=color)

    def polygon(self, pts, color, alpha: int = 255, width: float = 0.0, outline=None):
        a = self._agg()
        flat = []
        for p in pts:
            flat += [p[0], p[1]]
        brush = self._aggdraw.Brush(_rgba(color, alpha))
        pen = self._aggdraw.Pen(_rgba(outline, 255), width) if outline else None
        a.polygon(flat, pen, brush)

    # -- camera helpers --------------------------------------------------
    def wp(self, p):
        return self.cam.to_screen(p, self.w, self.h)

    def wl(self, a, b):
        return self.wp(a), self.wp(b)

    def unit(self) -> float:
        """Pixels per design unit — line widths scale with the output."""
        return (self.w / DESIGN_W) * self.cam.zoom


def _rgba(color, alpha: int):
    r, g, b = color[:3]
    return (int(r), int(g), int(b)) if alpha >= 255 else (int(r), int(g), int(b), int(alpha))


# ---------------------------------------------------------------- background
def draw_background(cv: Canvas):
    """Flat two-tone backdrop with a big warm disc, a floor and a horizon band."""
    w, h = cv.w, cv.h
    top = np.array([246, 243, 236], np.float32)
    bot = np.array([214, 210, 202], np.float32)
    ramp = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    arr = (top * (1 - ramp) + bot * ramp)
    arr = np.broadcast_to(arr, (h, w, 3)).astype(np.uint8)
    cv.img.paste(Image.fromarray(arr, "RGB"), (0, 0))

    # the disc: a low sun / spotlight behind the fighters
    cx, cy = cv.wp((520, 250))
    r = 205 * cv.unit()
    for i, (rr, a) in enumerate(((r * 1.5, 26), (r * 1.22, 30), (r, 34))):
        cv.flush()
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(250, 226, 180, a))
        cv.img.paste(Image.alpha_composite(cv.img.convert("RGBA"), overlay).convert("RGB"), (0, 0))
    # ground band
    gy = cv.wp((0, 432))[1]
    cv.flush()
    cv.d.rectangle([0, gy, w, h], fill=(203, 199, 190))
    cv.flush()
    cv.d.line([0, gy, w, gy], fill=(150, 146, 138), width=max(2, int(3 * cv.unit())))
    cv.d = ImageDraw.Draw(cv.img)


def shadow(cv: Canvas, pose: Pose, alpha: int = 60, squash: float = 0.30):
    sk = solve(pose)
    foot_x = (sk.pts[8][0] + sk.pts[10][0]) * 0.5
    foot_y = max(sk.pts[8][1], sk.pts[10][1])
    c = cv.wp((foot_x, foot_y + 4))
    rx = 62 * cv.unit() * pose.scale
    ry = rx * squash
    cv.flush()
    overlay = Image.new("RGBA", (cv.w, cv.h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.ellipse([c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry], fill=(60, 56, 50, alpha))
    cv.img.paste(Image.alpha_composite(cv.img.convert("RGBA"), overlay).convert("RGB"), (0, 0))
    cv.d = ImageDraw.Draw(cv.img)


# -------------------------------------------------------------------- figure
def draw_figure(cv: Canvas, pose: Pose, color=INK, accent=None, width_mul: float = 1.0,
                alpha: int = 255, head_fill=None):
    """Draw one Pivot figure: round-capped limbs, outlined head, optional accent."""
    sk = solve(pose)
    u = cv.unit() * pose.scale * width_mul
    for sid in SEGMENT_ORDER:
        _id, _parent, length, thick, kind = SEG[sid]
        start, end = sk.starts[sid], sk.pts[sid]
        p0, p1 = cv.wp(start), cv.wp(end)
        if kind == "circle":
            # Pivot draws the head as a white-filled circle with an ink outline;
            # the accent colour replaces that outline so each fighter reads at a glance
            cv.circle(cv.wp(sk.head), sk.head_r * cv.unit() * pose.scale,
                      accent if accent is not None else color,
                      width=max(1.5, thick * u), fill=head_fill or (255, 255, 255), alpha=alpha)
        else:
            cv.line(p0, p1, max(1.0, thick * u), color, alpha=alpha)



# --------------------------------------------------------------------- scale
def figure_height(pose: Pose) -> float:
    sk = solve(pose)
    return (max(sk.pts[8][1], sk.pts[10][1]) - (sk.head[1] - sk.head_r)) / max(pose.scale, 1e-6)
