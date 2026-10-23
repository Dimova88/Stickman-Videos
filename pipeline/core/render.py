"""Software renderer: anti-aliased vector canvas + cinematic post-processing.

Design notes
------------
* The canvas is float32 RGB in 0..1 (display-referred, i.e. what you see).
* Strokes use an analytic distance field over each segment's bounding box, which
  gives smooth sub-pixel anti-aliasing, exact tapering and additive "energy"
  blending without extra supersampling.
* Fills/plates use PIL + aggdraw (C, anti-aliased).
* Every bright element can also write into a half-resolution glow buffer that is
  blurred once per frame and added back: that single trick is most of the
  "cinematic" look.
* Final grade: bloom, anamorphic streak, chromatic aberration, vignette, grain,
  letterbox. All resolution independent, so 480p previews and 2160p finals match.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np
import aggdraw
from PIL import Image, ImageDraw, ImageFont

from .camera import Camera, CameraState

FONT_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
_FONTS: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    key = (name, size)
    if key not in _FONTS:
        path = FONT_DIR / {"bold": "NotoSans-Bold.ttf", "regular": "NotoSans-Regular.ttf"}.get(name, name)
        _FONTS[key] = ImageFont.truetype(str(path), size)
    return _FONTS[key]


def pack(color: Sequence[float], alpha: float = 1.0) -> np.ndarray:
    c = np.asarray(color, dtype=np.float32)
    return c * alpha


def rgba(color, alpha=1.0):
    r, g, b = [int(max(0, min(1, float(v))) * 255) for v in color[:3]]
    a = int(max(0.0, min(1.0, alpha)) * 255)
    return (r, g, b, a)


# --------------------------------------------------------------------------
@dataclass
class Post:
    """Per-frame post-processing settings (also used to drive impact frames)."""
    bloom: float = 0.40
    bloom_threshold: float = 0.80
    streak: float = 0.10           # horizontal anamorphic flare
    glow_gain: float = 0.0         # extra additive from the glow buffer
    ca: float = 0.9                # chromatic aberration, px at 1080p
    vignette: float = 0.30
    grain: float = 0.022
    exposure: float = 1.0
    contrast: float = 1.10
    saturation: float = 1.06
    letterbox: float = 0.0         # fraction of height per bar
    flash: float = 0.0             # white flash amount
    flash_color: tuple = (1, 1, 1)
    fade: float = 0.0              # black fade amount
    aberration_radial: float = 0.35
    sharpen: float = 0.25
    motion_blur: float = 0.0      # horizontal smear in px at 1080p (whip pans)
    invert: float = 0.0           # anime impact frame (inverted polarity)
    posterize: float = 0.0        # 0..1, crushes tones for a stylised impact frame
    tone_k: float = 1.45          # highlight roll-off (0 disables tone mapping)
    tone_shoulder: float = 0.82   # where compression starts


def gaussian_blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Fast separable box-approximated gaussian (3 boxes ~ gaussian)."""
    if sigma <= 0.3:
        return a
    import scipy.ndimage as ndi
    return ndi.gaussian_filter(a, sigma=(sigma, sigma, 0) if a.ndim == 3 else sigma,
                               mode="nearest", truncate=3.0)


class Painter:
    """One frame of drawing for one camera state."""

    def __init__(self, w: int, h: int, cam: Camera, st: CameraState, bg=(0.02, 0.02, 0.03)):
        self.w, self.h = w, h
        self.cam = cam
        self.st = st
        self.s = cam.s
        self.col = np.empty((h, w, 3), np.float32)
        self.col[:] = np.asarray(bg, np.float32)
        self.gw, self.gh = (w + 1) // 2, (h + 1) // 2
        self.glow = np.zeros((self.gh, self.gw, 3), np.float32)

    # ------------------------------------------------------------- primitives
    def _scaled(self, pts, depth):
        return self.cam.project_pts(pts, self.st, depth)

    def line(self, pts, width: float, color, alpha: float = 1.0, depth: float = 1.0,
             glow: float = 0.0, glow_color=None, taper: float = 1.0, additive: bool = False,
             closed: bool = False, colors=None, softness: float = 1.0, glow_radius: float = 1.0):
        """Draw a polyline.

        pts      : world-space points
        width    : world-space width
        taper    : width multiplier at the end of the stroke (0.2 = blade)
        colors   : optional per-vertex RGB (world list) for energy gradients
        """
        if len(pts) < 2:
            return
        P = self._scaled(pts, depth)
        k = self.cam.scale(self.st, depth)
        n = len(P)
        half = [max(0.35, width * k * 0.5 * (1.0 + (taper - 1.0) * (i / (n - 1)))) for i in range(n)]
        if closed:
            P = P + [P[0]]
            half = half + [half[0]]
        if colors is None:
            cols = [np.asarray(color, np.float32)] * (len(P) - 1)
        else:
            cols = [np.asarray(colors[min(i, len(colors) - 1)], np.float32) for i in range(len(P) - 1)]
        soft = max(0.5, softness)
        for i in range(len(P) - 1):
            self._seg(P[i], P[i + 1], half[i], half[i + 1], cols[i], alpha, additive, soft)
        if glow > 0:
            gc = np.asarray(glow_color if glow_color is not None else (color if colors is None else cols[len(cols) // 2]), np.float32)
            gk = 0.5
            for i in range(len(P) - 1):
                self._seg_glow((P[i][0] * gk, P[i][1] * gk), (P[i + 1][0] * gk, P[i + 1][1] * gk),
                               half[i] * gk, half[i + 1] * gk, gc, glow, glow_radius)

    def _seg(self, p0, p1, h0, h1, color, alpha, additive, soft=1.0):
        x0, y0 = p0
        x1, y1 = p1
        hw = max(h0, h1)
        pad = hw + 2.0 + soft
        x_lo = max(0, int(min(x0, x1) - pad)); x_hi = min(self.w, int(max(x0, x1) + pad) + 1)
        y_lo = max(0, int(min(y0, y1) - pad)); y_hi = min(self.h, int(max(y0, y1) + pad) + 1)
        if x_lo >= x_hi or y_lo >= y_hi:
            return
        yy, xx = np.mgrid[y_lo:y_hi, x_lo:x_hi]
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        px, py = xx + 0.5 - x0, yy + 0.5 - y0
        if L2 < 1e-9:
            t = np.zeros_like(px)
            dist = np.hypot(px, py)
        else:
            t = np.clip((px * dx + py * dy) / L2, 0.0, 1.0)
            dist = np.hypot(px - t * dx, py - t * dy)
        hwv = h0 + (h1 - h0) * t
        cov = np.clip((hwv + 0.5 * soft - dist) / soft, 0.0, 1.0).astype(np.float32)
        if alpha < 1.0:
            cov *= alpha
        sub = self.col[y_lo:y_hi, x_lo:x_hi]
        if additive:
            sub += cov[..., None] * color
        else:
            sub *= (1.0 - cov[..., None])
            sub += cov[..., None] * color

    def _seg_glow(self, p0, p1, h0, h1, color, amount, radius=1.0):
        x0, y0 = p0
        x1, y1 = p1
        hw = max(h0, h1) * 1.6 * radius
        pad = hw + 2.0
        x_lo = max(0, int(min(x0, x1) - pad)); x_hi = min(self.gw, int(max(x0, x1) + pad) + 1)
        y_lo = max(0, int(min(y0, y1) - pad)); y_hi = min(self.gh, int(max(y0, y1) + pad) + 1)
        if x_lo >= x_hi or y_lo >= y_hi:
            return
        yy, xx = np.mgrid[y_lo:y_hi, x_lo:x_hi]
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        px, py = xx + 0.5 - x0, yy + 0.5 - y0
        if L2 < 1e-9:
            t = np.zeros_like(px); dist = np.hypot(px, py)
        else:
            t = np.clip((px * dx + py * dy) / L2, 0.0, 1.0)
            dist = np.hypot(px - t * dx, py - t * dy)
        hwv = h0 + (h1 - h0) * t
        cov = np.clip((hwv + 0.5 - dist), 0.0, 1.0)
        falloff = np.clip(1.0 - (dist - hwv) / (hw + 1e-6), 0.0, 1.0) ** 2
        self.glow[y_lo:y_hi, x_lo:x_hi] += (cov * 1.0 + falloff * 0.55)[..., None] * color * amount

    def circle(self, c, r: float, color, alpha: float = 1.0, depth: float = 1.0, glow: float = 0.0,
               ring: float = 0.0, glow_color=None, softness: float = 1.0, additive=False):
        """r in world units; ring>0 draws an annulus of that thickness."""
        cx, cy = self.cam.project(c, self.st, depth)
        rr = r * self.cam.scale(self.st, depth)
        pad = rr + 2 + softness
        x_lo = max(0, int(cx - pad)); x_hi = min(self.w, int(cx + pad) + 1)
        y_lo = max(0, int(cy - pad)); y_hi = min(self.h, int(cy + pad) + 1)
        if x_lo < x_hi and y_lo < y_hi:
            yy, xx = np.mgrid[y_lo:y_hi, x_lo:x_hi]
            d = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy)
            outer = np.clip((rr + 0.5 * softness - d) / softness, 0, 1)
            if ring > 0:
                inner = np.clip((d - (rr - ring * self.cam.scale(self.st, depth)) + 0.5) / max(softness, 0.7), 0, 1)
                cov = outer * inner
            else:
                cov = outer
            cov = (cov * alpha).astype(np.float32)
            sub = self.col[y_lo:y_hi, x_lo:x_hi]
            if additive:
                sub += cov[..., None] * np.asarray(color, np.float32)
            else:
                sub *= (1 - cov[..., None])
                sub += cov[..., None] * np.asarray(color, np.float32)
        if glow > 0:
            gx, gy = cx * 0.5, cy * 0.5
            gr = max(rr * 0.5, 0.6)
            pad = gr * 2 + 2
            x_lo = max(0, int(gx - pad)); x_hi = min(self.gw, int(gx + pad) + 1)
            y_lo = max(0, int(gy - pad)); y_hi = min(self.gh, int(gy + pad) + 1)
            if x_lo < x_hi and y_lo < y_hi:
                yy, xx = np.mgrid[y_lo:y_hi, x_lo:x_hi]
                d = np.hypot(xx + 0.5 - gx, yy + 0.5 - gy)
                if ring > 0:
                    m = np.clip((d - (gr - ring * self.cam.scale(self.st, depth) * 0.5)) / 1.0, 0, 1) * \
                        np.clip((gr + ring * self.cam.scale(self.st, depth) * 0.5 + 1 - d) / 1.0, 0, 1)
                    core = m
                    fall = m * np.clip(1 - np.abs(d - gr) / (gr * 0.5 + 1.0), 0, 1) ** 2
                else:
                    core = np.exp(-(d / max(gr, 1e-3)) ** 2 * 3.0)
                    fall = np.exp(-(d / max(gr * 1.35, 1e-3)) ** 2 * 1.4)
                g = np.asarray(glow_color if glow_color is not None else color, np.float32)
                self.glow[y_lo:y_hi, x_lo:x_hi] += (core + fall * 0.6)[..., None] * g * glow

    def blob(self, c, r: float, color, alpha: float = 1.0, depth: float = 1.0, soft: float = 1.6,
             additive: bool = False):
        """Gaussian-soft disc — smoke, dust, bokeh, ambient haze."""
        cx, cy = self.cam.project(c, self.st, depth)
        rr = r * self.cam.scale(self.st, depth)
        pad = rr * 2.2 + 2
        x_lo = max(0, int(cx - pad)); x_hi = min(self.w, int(cx + pad) + 1)
        y_lo = max(0, int(cy - pad)); y_hi = min(self.h, int(cy + pad) + 1)
        if x_lo >= x_hi or y_lo >= y_hi:
            return
        yy, xx = np.mgrid[y_lo:y_hi, x_lo:x_hi]
        d = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) / max(rr, 1e-3)
        cov = (np.exp(-(d ** 2) * soft) * alpha).astype(np.float32)
        sub = self.col[y_lo:y_hi, x_lo:x_hi]
        cc = np.asarray(color, np.float32)
        if additive:
            sub += cov[..., None] * cc
        else:
            sub *= (1 - cov[..., None])
            sub += cov[..., None] * cc

    def arc(self, c, r: float, a0: float, a1: float, width: float, color, alpha: float = 1.0,
            depth: float = 1.0, glow: float = 0.0, glow_color=None, additive: bool = False,
            world: bool = True):
        """Annulus segment. Angles in radians, screen-style (y down)."""
        if world:
            cx, cy = self.cam.project(c, self.st, depth)
        else:
            cx, cy = c
        rr = r * self.cam.scale(self.st, depth)
        hw = max(0.6, width * self.cam.scale(self.st, depth) * 0.5)
        pad = rr + hw + 3
        x_lo = max(0, int(cx - pad)); x_hi = min(self.w, int(cx + pad) + 1)
        y_lo = max(0, int(cy - pad)); y_hi = min(self.h, int(cy + pad) + 1)
        if x_lo >= x_hi or y_lo >= y_hi:
            return
        yy, xx = np.mgrid[y_lo:y_hi, x_lo:x_hi]
        dx, dy = xx + 0.5 - cx, yy + 0.5 - cy
        d = np.hypot(dx, dy)
        ang = np.arctan2(dy, dx)
        span = (a1 - a0) % (2 * math.pi) or 2 * math.pi
        rel = (ang - a0) % (2 * math.pi)
        amask = (rel <= span).astype(np.float32)
        cov = np.clip((rr + hw - d) / 1.0, 0, 1) * np.clip((d - (rr - hw)) / 1.0, 0, 1) * amask * alpha
        cov = cov.astype(np.float32)
        sub = self.col[y_lo:y_hi, x_lo:x_hi]
        cc = np.asarray(color, np.float32)
        if additive:
            sub += cov[..., None] * cc
        else:
            sub *= (1 - cov[..., None])
            sub += cov[..., None] * cc
        if glow > 0:
            self.circle(c, r, color, alpha=0.0, depth=depth, glow=0.0)
            gx, gy = cx * 0.5, cy * 0.5
            gr = max(rr * 0.5, 0.5)
            gp = gr + hw + 4
            x0 = max(0, int(gx - gp)); x1 = min(self.gw, int(gx + gp) + 1)
            y0 = max(0, int(gy - gp)); y1 = min(self.gh, int(gy + gp) + 1)
            if x1 > x0 and y1 > y0:
                yy2, xx2 = np.mgrid[y0:y1, x0:x1]
                dx2, dy2 = xx2 + 0.5 - gx, yy2 + 0.5 - gy
                d2 = np.hypot(dx2, dy2)
                ang2 = np.arctan2(dy2, dx2)
                rel2 = (ang2 - a0) % (2 * math.pi)
                am2 = (rel2 <= span).astype(np.float32)
                core = np.clip(gr + hw * 0.5 + 0.8 - d2, 0, 1) * am2
                fall = np.clip(1 - np.maximum(np.abs(d2 - gr) - hw * 0.5, 0) / (hw + 3.0), 0, 1) ** 2 * am2
                gc = np.asarray(glow_color if glow_color is not None else color, np.float32)
                self.glow[y0:y1, x0:x1] += (core + fall * 0.7)[..., None] * gc * glow

    def ribbon(self, pts, widths, colors, alpha=1.0, depth=1.0, glow=0.0):
        """Filled quad ribbon with per-vertex width and colour — blades, trails."""
        P = self._scaled(pts, depth)
        k = self.cam.scale(self.st, depth)
        n = len(P)
        if n < 2:
            return
        # norize per vertex by adjacent tangent
        for i in range(n - 1):
            cols = [np.asarray(colors[i], np.float32), np.asarray(colors[min(i + 1, n - 1)], np.float32)]
            w0 = widths[i] * k * 0.5
            w1 = widths[min(i + 1, n - 1)] * k * 0.5
            self._quad(P[i], P[i + 1], w0, w1, cols, alpha)
        if glow > 0:
            self.line(pts, max(widths) * 1.05, colors[len(colors) // 2], alpha, depth, glow=glow,
                      glow_color=colors[len(colors) // 2])

    def _quad(self, p0, p1, w0, w1, cols, alpha):
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        L = math.hypot(dx, dy) or 1e-6
        nx, ny = -dy / L, dx / L
        quad = [
            (p0[0] + nx * w0, p0[1] + ny * w0),
            (p1[0] + nx * w1, p1[1] + ny * w1),
            (p1[0] - nx * w1, p1[1] - ny * w1),
            (p0[0] - nx * w0, p0[1] - ny * w0),
        ]
        self.poly(quad, cols[0], alpha=alpha, blend_over=True)

    def poly(self, pts, color, alpha: float = 1.0, blur: float = 0.0, additive=False,
             gradient: tuple | None = None, blend_over=False):
        """Anti-aliased filled polygon in *screen* coordinates.

        gradient = (c0, c1) fills vertically (top→bottom) for skies/ao.
        """
        if len(pts) < 3:
            return
        xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
        x_lo = max(-2, int(math.floor(min(xs))) - 1)
        y_lo = max(-2, int(math.floor(min(ys))) - 1)
        x_hi = min(self.w + 2, int(math.ceil(max(xs))) + 1)
        y_hi = min(self.h + 2, int(math.ceil(max(ys))) + 1)
        bw, bh = x_hi - x_lo, y_hi - y_lo
        if bw < 1 or bh < 1:
            return
        mask = Image.new("L", (bw, bh), 0)
        d = aggdraw.Draw(mask)
        local = [(q[0] - x_lo, q[1] - y_lo) for q in pts]
        path = aggdraw.Path()
        path.moveto(*local[0])
        for q in local[1:]:
            path.lineto(*q)
        path.close()
        d.path(path, None, aggdraw.Brush(255))
        d.flush()
        m = np.asarray(mask, np.float32) / 255.0
        if blur > 0:
            m = gaussian_blur(m, blur)
        m = (m * alpha)[..., None]
        if x_lo >= self.w or y_lo >= self.h or x_hi <= 0 or y_hi <= 0:
            return
        x0, y0 = max(0, x_lo), max(0, y_lo)
        x1, y1 = min(self.w, x_hi), min(self.h, y_hi)
        m = m[y0 - y_lo:y1 - y_lo, x0 - x_lo:x1 - x_lo]
        sub = self.col[y0:y1, x0:x1]
        if gradient is not None:
            t = np.linspace((y0 - y_lo) / max(bh - 1, 1), (y1 - 1 - y_lo) / max(bh - 1, 1),
                            m.shape[0], dtype=np.float32)[:, None, None]
            gc = (1 - t) * np.asarray(gradient[0], np.float32) + t * np.asarray(gradient[1], np.float32)
            c = np.broadcast_to(gc, sub.shape)
        else:
            c = np.asarray(color, np.float32)
        if additive:
            sub += c * m
        else:
            sub *= (1 - m)
            sub += c * m

    def polygon_world(self, pts, color, alpha=1.0, depth=1.0, **kw):
        self.poly(self._scaled(pts, depth), color, alpha=alpha, **kw)

    # ------------------------------------------------------------------ text
    def text(self, s, xy, size, color=(1, 1, 1), alpha=1.0, anchor="mm", bold=True,
             spacing=1.0, glow=0.0, world=False, depth=1.0, stroke=0, tracking=0.0):
        f = font("bold" if bold else "regular", int(size))
        if world:
            x, y = self.cam.project(xy, self.st, depth)
        else:
            x, y = xy
        if tracking:
            widths = [f.getbbox(ch)[2] - f.getbbox(ch)[0] for ch in s]
            total = sum(widths) + tracking * (len(s) - 1)
            x0 = x - total / 2 if anchor[0] == "m" else x
            for ch, w in zip(s, widths):
                if ch != " ":
                    self._text_at(ch, (x0 + w / 2, y), f, color, alpha, glow)
                x0 += w + tracking
            return
        self._text_at(s, (x, y), f, color, alpha, glow)

    def _text_at(self, s, xy, f, color, alpha, glow):
        bbox = f.getbbox(s)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = int(max(w, h) * 0.35) + 4
        img = Image.new("L", (w + pad * 2, h + pad * 2), 0)
        ImageDraw.Draw(img).text((pad - bbox[0], pad - bbox[1]), s, font=f, fill=255)
        m = np.asarray(img, np.float32) / 255.0 * alpha
        x = int(xy[0] - (w + pad * 2) / 2); y = int(xy[1] - (h + pad * 2) / 2)
        self._blit(m, x, y, color)
        if glow > 0:
            g = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).resize(
                ((w + pad * 2) // 2, (h + pad * 2) // 2), Image.BILINEAR), np.float32) / 255.0
            gx, gy = x // 2, y // 2
            H, W = g.shape
            x0, y0 = max(0, gx), max(0, gy)
            x1, y1 = min(self.gw, gx + W), min(self.gh, gy + H)
            if x1 > x0 and y1 > y0:
                self.glow[y0:y1, x0:x1] += g[y0 - gy:y1 - gy, x0 - gx:x1 - gx][..., None] * np.asarray(color, np.float32) * glow

    def _blit(self, m, x, y, color, additive=False):
        H, W = m.shape
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(self.w, x + W), min(self.h, y + H)
        if x1 <= x0 or y1 <= y0:
            return
        mm = m[y0 - y:y1 - y, x0 - x:x1 - x][..., None]
        sub = self.col[y0:y1, x0:x1]
        if additive:
            sub += mm * np.asarray(color, np.float32)
        else:
            sub *= (1 - mm)
            sub += mm * np.asarray(color, np.float32)

    # ----------------------------------------------------------------- plates
    def plate(self, img: Image.Image, rect, depth=0.25, alpha=1.0, additive=False):
        """Draw an image plate under the camera transform (parallax layer)."""
        iw, ih = img.size
        a, b, c, d, e, f = self.cam.image_coeffs(self.st, rect, (iw, ih), depth)
        out = img.transform((self.w, self.h), Image.AFFINE, (a, b, c, d, e, f), resample=Image.BILINEAR)
        arr = np.asarray(out.convert("RGB"), np.float32) / 255.0 * alpha
        if additive:
            self.col += arr
        else:
            self.col *= (1 - alpha) if alpha < 1 else 0.0
            self.col += arr


# ---------------------------------------------------------------- post stack
def resize_f(a: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Bilinear resize of a float array (2-D or HxWxC)."""
    w, h = size
    if a.shape[1] == w and a.shape[0] == h:
        return a
    if a.ndim == 2:
        return np.asarray(Image.fromarray(a.astype(np.float32, copy=False), mode="F")
                          .resize((w, h), Image.BILINEAR), np.float32)
    return np.stack([resize_f(a[..., i], size) for i in range(a.shape[2])], axis=2)


def gaussian_blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Separable gaussian on a float array (2-D or HxWxC)."""
    if sigma <= 0.25:
        return a
    import scipy.ndimage as ndi
    if a.ndim == 3:
        return ndi.gaussian_filter(a, sigma=(sigma, sigma, 0), mode="nearest", truncate=2.5)
    return ndi.gaussian_filter(a, sigma=sigma, mode="nearest", truncate=2.5)


def hblur(a: np.ndarray, sigma: float) -> np.ndarray:
    import scipy.ndimage as ndi
    if a.ndim == 3:
        return ndi.gaussian_filter1d(a, sigma=sigma, axis=1, mode="nearest", truncate=4.0)
    return ndi.gaussian_filter1d(a, sigma=sigma, axis=1, mode="nearest", truncate=4.0)


def vignette_mask(w, h, amount=0.42, roundness=0.5):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx = (xx - w / 2) / (w / 2)
    ny = (yy - h / 2) / (h / 2)
    r = np.sqrt(nx * nx * (1 - roundness * 0.35) + ny * ny * (1 + roundness * 0.55))
    m = np.clip(1.0 - amount * np.clip(r - 0.42, 0, 3) ** 1.45, 0, 1)
    return m[..., None].astype(np.float32)


def _warp(chan: np.ndarray, scale: float, cx: float, cy: float) -> np.ndarray:
    if abs(scale - 1.0) < 1e-5:
        return chan
    inv = 1.0 / scale
    coeffs = (inv, 0, cx - cx * inv, 0, inv, cy - cy * inv)
    return np.asarray(Image.fromarray(chan.astype(np.float32, copy=False), mode="F").transform(
        chan.shape[::-1], Image.AFFINE, coeffs, resample=Image.BILINEAR), np.float32)


def finish(col: np.ndarray, post: Post, t: float = 0.0, glow: np.ndarray | None = None,
           rng_seed: int = 0) -> np.ndarray:
    """Apply the full post stack. Returns float32 HxWx3 in 0..1."""
    h, w, _ = col.shape
    out = col.astype(np.float32, copy=True)
    hs = h / 1080.0

    # 1. accumulated glow layer (bokeh bloom of bright strokes)
    if glow is not None and float(glow.max()) > 1e-4:
        g = gaussian_blur(glow, sigma=max(1.0, 2.2 * hs))
        out += resize_f(g, (w, h))

    # 2. scene bloom: threshold bright areas, blur at low res, add back
    if post.bloom > 0:
        bright = np.clip(out - post.bloom_threshold, 0, None)
        small = resize_f(bright, (max(1, w // 4), max(1, h // 4)))
        small = gaussian_blur(small, sigma=max(1.0, 2.2 * hs))
        out += resize_f(small, (w, h)) * post.bloom
        # 3. anamorphic horizontal streak (2nd, wider pass)
        if post.streak > 0:
            tall = resize_f(small, (max(8, w // 15), max(8, h // 15)))
            streak = hblur(tall, sigma=max(2.5, 9 * hs))
            streak = resize_f(streak, (w, h))
            out += streak * np.array([0.6, 0.78, 1.0], np.float32) * post.streak

    # 3b. tone map the HDR accumulation so highlights roll off like film
    if post.tone_k > 0:
        k = post.tone_k
        knee = post.tone_shoulder
        x = np.clip(out, 0, None)
        # soft-knee Reinhard: linear below knee, asymptotic above
        lin = x / (1.0 + np.maximum(x - knee, 0) * k)
        out = np.where(x < knee, x, knee + (lin - knee) * 1.0) if False else lin
        out = np.clip(out, 0, 1)

    # 4. chromatic aberration (radial, cheap two-channel warp)
    if post.ca > 0.15:
        ca = post.ca * 0.0016 * hs
        cx, cy = w / 2.0, h / 2.0
        if post.aberration_radial > 0:
            out[..., 0] = _warp(out[..., 0], 1.0 + ca, cx, cy)
            out[..., 2] = _warp(out[..., 2], 1.0 - ca, cx, cy)
        else:
            out[..., 0] = _shift(out[..., 0], ca * w, 0)
            out[..., 2] = _shift(out[..., 2], -ca * w, 0)

    # 4b. directional motion blur (whip pans / speed ramps)
    if post.motion_blur > 0.5:
        mb = post.motion_blur * hs
        acc = np.zeros_like(out)
        taps, weight = 9, 0.0
        import scipy.ndimage as ndi
        for i in range(taps):
            f = (i / (taps - 1) - 0.5) * 2.0
            wgt = 1.0 - abs(f) * 0.6
            acc += ndi.shift(out, (0.0, mb * f, 0.0), order=1, mode="nearest") * wgt
            weight += wgt
        out = acc / weight

    # 5. grade
    out *= post.exposure
    if post.contrast != 1.0:
        out = (out - 0.5) * post.contrast + 0.5
    if post.saturation != 1.0:
        lum = (out @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
        out = lum + (out - lum) * post.saturation
    if post.sharpen > 0:
        soft = gaussian_blur(out, sigma=max(0.7, 1.1 * hs))
        out = out + (out - soft) * post.sharpen * 0.55
    if post.vignette > 0:
        out *= vignette_mask(w, h, post.vignette)

    # 5b. anime impact frame: inverted polarity + crushed tones
    if post.invert > 0:
        inv = 1.0 - np.clip(out, 0, 1)
        out = out * (1 - post.invert) + inv * post.invert
    if post.posterize > 0:
        steps = max(2.0, 6.0 * (1 - post.posterize) + 2.0)
        out = out * (1 - post.posterize) + (np.round(out * steps) / steps) * post.posterize

    # 6. flashes / fades / grain / bars
    if post.flash > 0:
        out += (np.asarray(post.flash_color, np.float32) - out) * np.clip(post.flash, 0, 1)
    out = np.clip(out, 0, 1)
    if post.grain > 0:
        rng = np.random.default_rng(rng_seed * 7919 + int(t * 1000))
        n = rng.standard_normal((h // 2 + 1, w // 2 + 1), dtype=np.float32)
        n = np.repeat(np.repeat(n, 2, axis=0), 2, axis=1)[:h, :w]
        out = np.clip(out + n[..., None] * post.grain, 0, 1)
    if post.fade > 0:
        out *= np.clip(1 - post.fade, 0, 1)
    if post.letterbox > 0:
        bar = int(h * post.letterbox)
        out[:bar] = 0.0
        out[h - bar:] = 0.0
    return out


def _shift(chan: np.ndarray, dx: float, dy: float) -> np.ndarray:
    coeffs = (1, 0, -dx, 0, 1, -dy)
    return np.asarray(Image.fromarray(chan.astype(np.float32, copy=False), mode="F").transform(
        chan.shape[::-1], Image.AFFINE, coeffs, resample=Image.BILINEAR), np.float32)


def to_uint8(a: np.ndarray) -> np.ndarray:
    return (np.clip(a, 0, 1) * 255.0 + 0.5).astype(np.uint8)
