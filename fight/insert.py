"""The close-up register: when the fight is too fast for the wide shot.

A stickman reads a fight at a distance; a body blow at full speed does not. So
the film cuts — on the frame the blow lands, not near it — and for half a second
the simple figure is gone: a face with two eyes and a jaw, or, on the finisher,
the skull taking the hit.

Everything here is drawn in finished-frame pixels (1280x720), not design units:
an insert is a cut, so it has its own composition and does not ride the camera.
Curves go through `_spline`, because a head built from straight polygon facets
reads as a lumpy blob — that was the first version, and it looked it.

    from fight.insert import cut_at, draw_insert
    cut = cut_at(t)               # None, or (spec, progress 0..1)
    if cut:
        draw_insert(cv, cut, scene)
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

# (start, duration, side, expression, register)
# Each `start` is the frame the blow lands on: the cut has to be instantaneous,
# so the last of the pre-impact frames must never be the one the cut begins on.
#   side        whose face fills the frame
#   expression  what the face is doing
#   register    "face" or "xray"
CUTS = (
    (13.44, 0.42, "red", "grit", "face"),     # the fist clash
    (18.40, 0.54, "blue", "hit", "face"),     # red's aerial kick, on the head
    (24.72, 0.48, "red", "ko", "xray"),       # the finisher, bone and all
)

# the slow-motion hold, in fractions of the cut: snap, hold, settle
SNAP, HOLD = 0.16, 0.46


def cut_at(t: float):
    for start, dur, side, expr, kind in CUTS:
        if start <= t < start + dur:
            return (start, dur, side, expr, kind), (t - start) / dur
    return None


def _snap(phase: float) -> float:
    """The deformation curve of the shot: instant, then held, then released.

    This is what makes the cut read as slow motion. The head is already thrown
    at full recoil on the first frame of the cut, holds there while the frame
    pushes in, and only then settles back.
    """
    if phase < SNAP:
        return phase / SNAP
    if phase < HOLD:
        return 1.0
    return max(0.0, 1.0 - (phase - HOLD) / (1.0 - HOLD))


def _spline(pts, closed: bool = True, steps: int = 10):
    """Catmull-Rom through the control points: a smooth outline, not facets."""
    n = len(pts)
    if n < 3:
        return list(pts)
    out = []
    rng = range(n) if closed else range(n - 1)
    for i in rng:
        p0 = pts[(i - 1) % n] if closed else pts[max(0, i - 1)]
        p1 = pts[i % n]
        p2 = pts[(i + 1) % n] if closed else pts[min(n - 1, i + 1)]
        p3 = pts[(i + 2) % n] if closed else pts[min(n - 1, i + 2)]
        for s in range(steps):
            t = s / steps
            t2, t3 = t * t, t * t * t
            out.append((
                0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t
                       + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                       + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t
                       + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                       + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)))
    return out


def _grad(w: int, h: int, top, bot) -> np.ndarray:
    ramp = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    a = np.array(top, np.float32)
    b = np.array(bot, np.float32)
    return np.ascontiguousarray(np.broadcast_to(a * (1 - ramp) + b * ramp,
                                                (h, w, 3)).astype(np.uint8))


def _focus_lines(cv, c, r: float, n: int = 46, tint=(255, 250, 236)) -> None:
    """Manga speed lines: wedges running from just outside the head to the edge."""
    for i in range(n):
        a = (i / n) * 2 * math.pi + 0.11
        half = 0.006 + 0.010 * ((i * 7) % 5) / 4.0
        r0 = r * (0.96 + 0.24 * ((i * 3) % 4) / 3.0)
        p0 = (c[0] + math.cos(a - half) * r0, c[1] + math.sin(a - half) * r0)
        p1 = (c[0] + math.cos(a + half) * r0, c[1] + math.sin(a + half) * r0)
        far = 1500.0
        p2 = (c[0] + math.cos(a + half * 5.0) * far, c[1] + math.sin(a + half * 5.0) * far)
        p3 = (c[0] + math.cos(a - half * 5.0) * far, c[1] + math.sin(a - half * 5.0) * far)
        cv.polygon([p0, p1, p2, p3], tint, alpha=14 + 12 * (i % 3))


def _tube(cv, pts, widths, colour, alpha: int = 255) -> None:
    """A tapering band through a joint chain: neck, tendon, vertebra."""
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        w0, w1 = widths[i] * 0.5, widths[i + 1] * 0.5
        d = math.hypot(x1 - x0, y1 - y0) or 1.0
        nx, ny = -(y1 - y0) / d, (x1 - x0) / d
        cv.polygon([(x0 + nx * w0, y0 + ny * w0), (x1 + nx * w1, y1 + ny * w1),
                    (x1 - nx * w1, y1 - ny * w1), (x0 - nx * w0, y0 - ny * w0)],
                   colour, alpha=alpha)
        cv.circle((x0, y0), w0, colour, width=0, fill=colour, alpha=alpha)
    cv.circle(pts[-1], widths[-1] * 0.5, colour, width=0, fill=colour, alpha=alpha)


def _eye(cv, c, f: int, w: float, hgt: float, iris, pupil, blink: float,
         glow: float) -> None:
    """One anime eye: tall almond, amber iris with a dark rim, heavy lash."""
    hgt = max(1.2, hgt * blink)
    cx, cy = c
    # sclera
    cv.polygon(_spline([(cx + f * w, cy + hgt * 0.10),
                        (cx + f * w * 0.30, cy - hgt * 1.00),
                        (cx - f * w * 0.42, cy - hgt * 0.86),
                        (cx - f * w, cy - hgt * 0.02),
                        (cx - f * w * 0.36, cy + hgt * 0.92),
                        (cx + f * w * 0.44, cy + hgt * 0.86)], steps=7), (249, 249, 244))
    # iris: rim, body, pupil, catchlight
    ix, iy = cx + f * w * 0.16, cy - hgt * 0.06
    ir = min(w * 0.72, hgt * 1.02)
    if glow > 0.25:
        cv.circle((ix, iy), ir * 1.55, (255, 176, 84), width=0,
                  fill=(255, 176, 84), alpha=int(30 + 40 * glow))
    cv.circle((ix, iy), ir, (146, 92, 34), width=0, fill=(146, 92, 34))
    cv.circle((ix, iy), ir * 0.86, iris, width=0, fill=iris)
    cv.circle((ix, iy), ir * 0.42, pupil, width=0, fill=pupil)
    cv.circle((ix - f * ir * 0.26, iy - ir * 0.34), ir * 0.28, (255, 255, 253),
              width=0, fill=(255, 255, 253))
    cv.circle((ix + f * ir * 0.40, iy + ir * 0.36), ir * 0.14, (255, 255, 253),
              width=0, fill=(255, 255, 253), alpha=200)
    # upper lash: heavy, past the outer corner, clipping the iris
    cv.polygon(_spline([(cx + f * w * 1.22, cy + hgt * 0.02),
                        (cx + f * w * 0.30, cy - hgt * 1.12),
                        (cx - f * w * 0.46, cy - hgt * 0.96),
                        (cx - f * w * 1.10, cy - hgt * 0.10),
                        (cx - f * w * 0.96, cy + hgt * 0.06),
                        (cx - f * w * 0.40, cy - hgt * 0.62),
                        (cx + f * w * 0.34, cy - hgt * 0.76)],
                       steps=7, closed=False), (26, 22, 26))
    # lower lid, thin
    cv.polyline([(cx + f * w * 0.96, cy + hgt * 0.16),
                 (cx + f * w * 0.20, cy + hgt * 0.94),
                 (cx - f * w * 0.72, cy + hgt * 0.62)],
                max(1.0, hgt * 0.10), (26, 22, 26), alpha=170)


NECK = ((-0.24, 0.78), (0.24, 0.74), (0.44, 1.62), (-0.42, 1.58))
HEAD = ((0.60, -0.92), (0.90, -0.48), (0.86, -0.06), (0.78, 0.26),
        (0.54, 0.64), (0.22, 0.94), (0.00, 1.02), (-0.30, 0.88),
        (-0.58, 0.54), (-0.74, 0.14), (-0.82, -0.30), (-0.62, -0.78),
        (-0.12, -1.00))


def _bust(cv, c, r: float, f: int, colour, dark, phase: float,
          expr: str, hurt: float) -> None:
    """Head, neck and shoulder. A portrait, not a circle with parts stuck on.

    The head is one silhouette: cranium, cheek, jaw, chin. The eyes are tall
    almonds one eye apart on the centre line, with a heavy upper lash — at this
    size the lash and the chin are what make it a face. Soft shading polygons
    were the mistake: they read as blotches, so there is none.
    """
    rr = r * (1.0 + 0.085 * phase)

    def P(x, y):
        return (c[0] + f * x * rr, c[1] + y * rr)

    # ---- shoulders, then the neck behind the head
    cv.polygon(_spline([P(-2.9, 4.2), P(-2.3, 1.92), P(-1.35, 1.50),
                        P(-0.30, 1.34), P(0.95, 1.40), P(2.10, 1.84),
                        P(2.9, 4.2)], steps=9), dark)
    cv.circle(P(1.62, 2.42), rr * 1.16, colour, width=0, fill=colour)   # near deltoid
    cv.circle(P(1.30, 2.10), rr * 0.90, colour, width=0, fill=colour)
    cv.line(P(1.16, 1.76), P(1.78, 3.00), rr * 0.05, dark, alpha=60, caps=False)
    cv.polygon(_spline([P(x, y) for x, y in NECK], steps=7), colour)
    cv.polygon(_spline([P(-0.20, 0.80), P(0.26, 0.76), P(0.38, 1.24),
                        P(-0.14, 1.20)], steps=6), dark, alpha=95)       # jaw shadow

    # ---- the head, one silhouette
    cv.polygon(_spline([P(x, y) for x, y in HEAD], steps=10), colour)

    # ---- eyes
    blink = 0.20 if expr == "ko" else (1.0 if expr == "hit" else 0.90)
    glow = 0.0 if expr == "grit" else (0.55 if expr == "hit" else 1.0)
    ew, eh = rr * 0.245, rr * 0.185
    for (ex, sc, g) in ((0.33, 1.0, glow), (-0.31, 0.80, glow * 0.6)):
        _eye(cv, P(ex, 0.02), f, ew * sc, eh * sc * blink, (252, 198, 104),
             (24, 18, 20), 1.0, g)

    # ---- brows: thin wedges, thick at the outer end, tilted toward the nose
    angry = 0.10 + 0.16 * hurt
    for (xi, xo) in ((0.12, 0.66), (-0.66, -0.10)):
        cv.polygon(_spline([P(xo, -0.44), P((xi + xo) * 0.5, -0.50),
                            P(xi, -0.38 + angry), P(xi, -0.33 + angry),
                            P((xi + xo) * 0.5, -0.42), P(xo, -0.37)], steps=6), dark)

    # ---- nose and mouth
    cv.polyline([P(0.50, 0.18), P(0.56, 0.38), P(0.40, 0.40)], rr * 0.022, dark,
                alpha=120)
    my = 0.66
    if expr in ("ko", "hit"):
        gap = 0.15 if expr == "ko" else 0.085
        cv.polygon(_spline([P(0.42, my - 0.06), P(0.06, my - 0.07),
                            P(0.04, my + gap), P(0.40, my + gap + 0.03)], steps=6),
                   (30, 16, 18))
        cv.polygon(_spline([P(0.40, my - 0.05), P(0.07, my - 0.06),
                            P(0.07, my + gap * 0.36), P(0.38, my + gap * 0.42)],
                           steps=5), (236, 234, 226))
    elif expr == "grit":
        cv.polygon(_spline([P(0.42, my - 0.01), P(0.24, my + 0.02), P(0.05, my - 0.01),
                            P(0.06, my + 0.10), P(0.24, my + 0.13),
                            P(0.41, my + 0.09)], steps=6), (238, 236, 228))
        for i in range(3):
            x = 0.34 - 0.10 * i
            cv.line(P(x, my - 0.005), P(x - 0.005, my + 0.105), rr * 0.012,
                    (60, 54, 56), alpha=200, caps=False)
        cv.polyline([P(0.43, my - 0.02), P(0.24, my + 0.01), P(0.04, my - 0.02)],
                    rr * 0.018, dark, alpha=230)
    else:
        cv.polygon(_spline([P(0.40, my), P(0.24, my + 0.035), P(0.06, my + 0.005),
                            P(0.07, my + 0.055), P(0.24, my + 0.085),
                            P(0.39, my + 0.05)], steps=6), dark, alpha=210)

    # ---- sweat and spit, hanging in the slow motion
    for i in range(7):
        a = -1.15 + 0.36 * i
        dist = rr * (0.55 + 1.55 * phase) * (1.0 + 0.09 * i)
        px = c[0] + f * math.cos(a) * dist
        py = c[1] + rr * 0.02 + math.sin(a) * dist * 0.55
        cv.circle((px, py), rr * (0.034 - 0.003 * i), (240, 246, 252),
                  width=0, fill=(240, 246, 252), alpha=max(0, int(170 * (1 - phase))))


SKULL = ((0.10, -1.04), (0.56, -0.94), (0.86, -0.66), (0.94, -0.32),
         (0.88, -0.18), (0.92, -0.02), (0.94, 0.10), (0.80, 0.22),
         (0.78, 0.34), (0.34, 0.38), (0.30, 0.48), (0.18, 0.74),
         (-0.04, 0.80), (-0.40, 0.62), (-0.62, 0.32), (-0.96, 0.06),
         (-0.98, -0.30), (-0.74, -0.76), (-0.36, -0.98))


def _xray(cv, c, r: float, f: int, phase: float) -> None:
    """The finisher, inside the skull: bone, orbits, teeth, and the crack.

    A white disc with two rectangles in it is a diagram. What makes it a skull is
    the profile — brow ridge, nasion, nasal spine, maxilla, chin, jaw angle,
    occiput — plus the holes: the orbits and the nasal aperture are what the eye
    recognises before it recognises anything else.
    """
    bone, shade, hole = (242, 244, 236), (203, 208, 199), (12, 17, 23)

    def P(x, y, k=1.0):
        return (c[0] + f * x * r * k, c[1] + y * r * k)

    # the body in silhouette behind the bone, so the skull belongs to someone
    cv.polygon(_spline([P(-2.6, 3.9), P(-1.9, 1.66), P(-0.5, 1.36),
                        P(0.9, 1.50), P(2.6, 3.9)], steps=8), (26, 34, 42))
    cv.circle(P(1.34, 2.66), r * 0.98, (30, 38, 46), width=0, fill=(30, 38, 46))
    # the cranium with a shadow side, then the bone over it
    cv.polygon([(x - f * r * 0.10, y + r * 0.09) for x, y in
                _spline([P(a, b) for a, b in SKULL], steps=9)], shade)
    cv.polygon(_spline([P(a, b) for a, b in SKULL], steps=9), bone)
    # temporal hollow
    cv.polygon(_spline([P(-0.72, -0.34), P(-0.34, -0.40), P(-0.26, 0.10),
                        P(-0.64, 0.16)], steps=6), shade, alpha=120)
    # orbit: rounded, deep, with a brow ridge over it
    cv.polygon(_spline([P(0.20, -0.34), P(0.58, -0.30), P(0.70, -0.06),
                        P(0.56, 0.12), P(0.26, 0.10), P(0.14, -0.10)], steps=7), hole)
    cv.polygon(_spline([P(-0.44, -0.32), P(-0.10, -0.26), P(-0.06, 0.00),
                        P(-0.30, 0.12), P(-0.50, -0.04)], steps=7), hole)
    # nasal aperture, a pear pointing up, and the nasal spine below it
    cv.polygon(_spline([P(0.60, 0.02), P(0.70, 0.16), P(0.58, 0.30),
                        P(0.44, 0.26), P(0.44, 0.08)], steps=7), hole)
    cv.polygon([P(0.60, 0.30), P(0.66, 0.36), P(0.50, 0.36)], hole)
    # zygomatic arch running back from the cheekbone, and the maxilla
    cv.polygon(_spline([P(0.74, 0.10), P(0.30, 0.24), P(-0.20, 0.34),
                        P(-0.14, 0.44), P(0.34, 0.36), P(0.78, 0.22)], steps=6),
               shade, alpha=170)
    cv.polygon(_spline([P(0.74, 0.24), P(0.40, 0.34), P(0.10, 0.36),
                        P(0.14, 0.50), P(0.44, 0.46), P(0.76, 0.34)], steps=6), bone)
    # teeth: a row cut into the maxilla
    for i in range(6):
        x = 0.70 - 0.085 * i
        cv.polygon([P(x, 0.34), P(x - 0.05, 0.34), P(x - 0.045, 0.47), P(x + 0.005, 0.47)],
                   hole)
    # mandible: ramus up to the hinge, then the body of the jaw
    cv.polygon(_spline([P(0.76, 0.26), P(0.66, 0.74), P(0.20, 0.86),
                        P(-0.18, 0.72), P(-0.12, 0.56), P(0.26, 0.58),
                        P(0.56, 0.48)], steps=8), bone)
    cv.polygon(_spline([P(0.60, 0.54), P(0.24, 0.66), P(-0.10, 0.64),
                        P(-0.08, 0.74), P(0.22, 0.80), P(0.64, 0.70)], steps=6),
               shade, alpha=150)
    cv.polyline([P(0.82, 0.40), P(0.36, 0.50), P(-0.12, 0.52)], r * 0.028, hole,
                alpha=225)                                  # the jaw seam
    # cervical spine: vertebral bodies, discs and spinous processes
    for i in range(5):
        yy = 0.92 + 0.26 * i
        w = 0.26 - 0.018 * i
        cv.polygon(_spline([P(w, yy), P(-w, yy + 0.02), P(-w - 0.02, yy + 0.17),
                            P(w + 0.02, yy + 0.14)], steps=6), bone)
        cv.polygon([P(w + 0.02, yy + 0.15), P(-w - 0.04, yy + 0.18),
                    P(-w - 0.03, yy + 0.24), P(w + 0.03, yy + 0.21)], hole)
        cv.polygon([P(-w - 0.02, yy + 0.03), P(-w - 0.20, yy + 0.10),
                    P(-w - 0.18, yy + 0.16), P(-w - 0.01, yy + 0.15)], shade)
    # the fracture: a hairline crack that opens with the blow, and the bloom
    if phase > 0.10:
        g = min(1.0, (phase - 0.10) / 0.35)
        crack = ((0.90, -0.26), (0.74, -0.44), (0.56, -0.40), (0.46, -0.62),
                 (0.30, -0.66), (0.18, -0.86), (0.04, -0.80))
        pts = [P(x, y + (0.016 if i % 2 else -0.016) * g) for i, (x, y) in enumerate(crack)]
        cv.polyline(pts, r * 0.020 * (0.6 + g), (150, 30, 30))
        cv.polyline([(x, y + r * 0.010 * g) for x, y in pts], r * 0.009, (62, 12, 12))
        # a chip of bone knocked loose, drifting off the impact
        cx, cy = P(0.86, -0.24)
        cv.polygon(_spline([(cx, cy), (cx + r * 0.10 * g, cy + r * 0.04),
                            (cx + r * 0.07 * g, cy + r * 0.12),
                            (cx - r * 0.03, cy + r * 0.09)], steps=5), bone)
        cv.circle(P(0.96, -0.26), r * (0.40 + 0.42 * g), (196, 44, 36),
                  width=0, fill=(196, 44, 36), alpha=int(88 * (1 - phase)))


def draw_insert(cv, cut, scene) -> None:
    """Compose one insert: backdrop, focus lines, the bust or the skull."""
    (start, dur, side, expr, kind), phase = cut
    track = scene[side]
    f = 1 if track.pose_at(start).facing > 0 else -1
    colour, dark = track.colour, track.dark
    w, h = cv.w, cv.h
    k = w / 1280.0

    top, bot = ((6, 10, 18), (16, 26, 38)) if kind == "xray" else ((10, 12, 18), (30, 34, 46))
    cv.img.paste(Image.fromarray(_grad(w, h, top, bot)))
    cv.d = ImageDraw.Draw(cv.img)
    cv._draw = None

    # the frame pushes in across the whole cut, and the head is thrown back on
    # the first frame and hangs there: that hold is the slow motion
    snap = _snap(phase)
    push = 1.03 + 0.12 * (phase ** 0.55)
    c = (w * 0.50 + f * w * 0.055 - f * w * 0.070 * snap,
         h * 0.45 + h * 0.016 * snap)
    r = (196.0 if kind == "xray" else 172.0) * k * push

    _focus_lines(cv, c, r, tint=(255, 246, 226) if kind == "xray" else (236, 240, 250))
    if kind == "xray":
        _xray(cv, c, r, f, phase)
    else:
        hurt = 1.0 if expr in ("hit", "ko") else 0.35
        cv.circle(c, r * 1.46, (255, 138, 66), width=0, fill=(255, 138, 66),
                  alpha=int(34 + 30 * (1 - abs(phase - 0.3) * 2)))
        _bust(cv, c, r, f, colour, dark, phase, expr, hurt)

    # impact streaks on the first frames, thrown out of the point of contact
    if phase < 0.5:
        g = 1.0 - phase / 0.5
        for i in range(6):
            a = -0.62 + 0.26 * i
            r0 = r * 1.28
            ln = r * (0.5 + 0.7 * g)
            p0 = (c[0] + f * math.cos(a) * r0, c[1] + math.sin(a) * r0)
            p1 = (c[0] + f * math.cos(a) * (r0 + ln), c[1] + math.sin(a) * (r0 + ln))
            cv.line(p0, p1, 5.5 * k * (0.4 + g), (255, 250, 238),
                    alpha=int(200 * g), caps=False)
    cv.flush()
