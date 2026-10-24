"""The close-up register: when the fight is too fast for the wide shot.

A stickman reads a fight at a distance, but a body blow at full speed has no
detail left at that size — so the film cuts. For a fifth of a second, on the
heaviest impacts, the simple figure is abandoned for a bust: a face with both
eyes, a shoulder with a deltoid, a neck with tendons, and on the finisher an
X-ray of the skull taking the hit.

Everything here is drawn in finished-frame pixels (1280x720), not design units:
an insert is a cut, so it has its own composition and does not ride the camera.

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
#   side        which fighter fills the frame
#   expression  what the face is doing
#   register    "face" or "xray"
CUTS = (
    (9.56, 0.30, "blue", "hit", "face"),      # red's uppercut arrives
    (13.38, 0.26, "red", "grit", "face"),     # the fist clash
    (24.28, 0.40, "blue", "ko", "xray"),      # the finisher, bone and all
)

# frames of black on the cut so the edit does not read as a glitch
LEAD = 0.042


def cut_at(t: float):
    for start, dur, side, expr, kind in CUTS:
        if start <= t < start + dur:
            return (start, dur, side, expr, kind), (t - start) / dur
    return None


def _grad(w: int, h: int, top, bot) -> np.ndarray:
    ramp = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    a = np.array(top, np.float32)
    b = np.array(bot, np.float32)
    return np.broadcast_to(a * (1 - ramp) + b * ramp, (h, w, 3)).astype(np.uint8)


def _focus_lines(cv, c, r: float, n: int = 44, tint=(255, 250, 236)) -> None:
    """Manga speed lines: wedges running from just outside the head to the edge."""
    for i in range(n):
        a = (i / n) * 2 * math.pi + 0.11
        half = (0.006 + 0.010 * ((i * 7) % 5) / 4.0)
        r0 = r * (0.92 + 0.22 * ((i * 3) % 4) / 3.0)
        p0 = (c[0] + math.cos(a - half) * r0, c[1] + math.sin(a - half) * r0)
        p1 = (c[0] + math.cos(a + half) * r0, c[1] + math.sin(a + half) * r0)
        far = 1500.0
        p2 = (c[0] + math.cos(a + half * 5.0) * far, c[1] + math.sin(a + half * 5.0) * far)
        p3 = (c[0] + math.cos(a - half * 5.0) * far, c[1] + math.sin(a - half * 5.0) * far)
        cv.polygon([p0, p1, p2, p3], tint, alpha=16 + 12 * (i % 3))


def _tube(cv, pts, widths, colour, alpha: int = 255) -> None:
    """A tapering band through a joint chain: neck, tendon, rib."""
    n = len(pts)
    for i in range(n - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        w0, w1 = widths[i] * 0.5, widths[i + 1] * 0.5
        d = math.hypot(x1 - x0, y1 - y0) or 1.0
        nx, ny = -(y1 - y0) / d, (x1 - x0) / d
        cv.polygon([(x0 + nx * w0, y0 + ny * w0), (x1 + nx * w1, y1 + ny * w1),
                    (x1 - nx * w1, y1 - ny * w1), (x0 - nx * w0, y0 - ny * w0)],
                   colour, alpha=alpha)
        cv.circle((x0, y0), w0, colour, width=0, fill=colour, alpha=alpha)
    cv.circle(pts[-1], widths[-1] * 0.5, colour, width=0, fill=colour, alpha=alpha)


def _bust(cv, c, r: float, f: int, colour, dark, phase: float,
          expr: str, hurt: float) -> None:
    """Head, neck and shoulder, built like a portrait rather than a circle."""
    # ---- shoulders: the far one in shadow, the near deltoid catching the light
    sy = c[1] + r * 1.86
    cv.polygon([(c[0] - r * 2.4, c[1] + r * 4.0), (c[0] - r * 2.0, sy + r * 0.18),
                (c[0] - r * 1.05, sy - r * 0.10), (c[0] - r * 0.30, sy - r * 0.42),
                (c[0] + r * 0.60, sy - r * 0.44), (c[0] + r * 1.45, sy - r * 0.02),
                (c[0] + r * 2.10, sy + r * 0.60), (c[0] + r * 2.4, c[1] + r * 4.0)], dark)
    cv.circle((c[0] + f * r * 1.42, sy + r * 0.72), r * 0.92, colour,
              width=0, fill=colour)                              # near deltoid
    cv.circle((c[0] - f * r * 1.30, sy + r * 0.86), r * 0.60, dark,
              width=0, fill=dark)                                # far deltoid
    cv.line((c[0] + f * r * 1.02, sy + r * 0.24),
            (c[0] + f * r * 1.42, sy + r * 1.30), r * 0.07, dark, alpha=80,
            caps=False)                                        # deltoid / pec seam
    # ---- neck, with the sterno-mastoid running down to the collarbone
    neck = [(c[0] + f * r * 0.02, c[1] + r * 0.56),
            (c[0] + f * r * 0.10, c[1] + r * 0.94),
            (c[0] + f * r * 0.02, c[1] + r * 1.38)]
    _tube(cv, neck, [r * 0.62, r * 0.76, r * 1.10], colour)
    cv.line((c[0] + f * r * 0.24, c[1] + r * 0.72),
            (c[0] + f * r * 0.38, c[1] + r * 1.44), r * 0.07, dark, alpha=120,
            caps=False)
    cv.line((c[0] - f * r * 0.26, c[1] + r * 0.80),
            (c[0] - f * r * 0.16, c[1] + r * 1.44), r * 0.05, dark, alpha=80,
            caps=False)

    # ---- the head, cut as a profile: this silhouette is what makes a bust
    # read as a face and not as a ball with features painted on it
    head = [(c[0] - f * r * 0.10, c[1] - r * 1.00),
            (c[0] + f * r * 0.44, c[1] - r * 0.90),
            (c[0] + f * r * 0.66, c[1] - r * 0.60),
            (c[0] + f * r * 0.76, c[1] - r * 0.26),
            (c[0] + f * r * 0.98, c[1] + r * 0.04),
            (c[0] + f * r * 0.84, c[1] + r * 0.14),
            (c[0] + f * r * 0.88, c[1] + r * 0.28),
            (c[0] + f * r * 0.78, c[1] + r * 0.42),
            (c[0] + f * r * 0.64, c[1] + r * 0.62),
            (c[0] + f * r * 0.32, c[1] + r * 0.78),
            (c[0] - f * r * 0.12, c[1] + r * 0.80),
            (c[0] - f * r * 0.50, c[1] + r * 0.58),
            (c[0] - f * r * 0.74, c[1] + r * 0.22),
            (c[0] - f * r * 0.94, c[1] - r * 0.18),
            (c[0] - f * r * 0.72, c[1] - r * 0.72)]
    cv.polygon(head, colour)
    # planes: cheekbone, jaw shadow, temple — flat blocks, no outline
    cv.polygon([(c[0] + f * r * 0.30, c[1] + r * 0.06),
                (c[0] + f * r * 0.74, c[1] + r * 0.12),
                (c[0] + f * r * 0.52, c[1] + r * 0.48),
                (c[0] + f * r * 0.16, c[1] + r * 0.44)], dark, alpha=45)
    cv.polygon([(c[0] + f * r * 0.60, c[1] + r * 0.46),
                (c[0] + f * r * 0.26, c[1] + r * 0.78),
                (c[0] - f * r * 0.20, c[1] + r * 0.70),
                (c[0] + f * r * 0.16, c[1] + r * 0.40)], dark, alpha=38)
    cv.circle((c[0] - f * r * 0.60, c[1] + r * 0.04), r * 0.10, dark,
              width=0, fill=dark, alpha=120)                    # ear
    cv.line((c[0] + f * r * 0.80, c[1] + r * 0.02),
            (c[0] + f * r * 0.66, c[1] + r * 0.14), r * 0.04, dark, alpha=110,
            caps=False)                                         # nostril

    # ---- eyes: white almond, big amber iris, hard lid — they read at any size
    blink = 0.30 if expr == "ko" else (1.08 if expr == "hit" else 0.92)
    for i, (e, s) in enumerate((((c[0] + f * r * 0.30, c[1] - r * 0.16), 1.0),
                                ((c[0] - f * r * 0.34, c[1] - r * 0.10), 0.66))):
        w, hgt = r * 0.28 * s, r * 0.19 * s * blink
        almond = [(e[0] + f * w, e[1] + r * 0.02 * s),
                  (e[0] + f * w * 0.15, e[1] - hgt * 1.25),
                  (e[0] - f * w, e[1] - hgt * 0.30),
                  (e[0] - f * w * 0.10, e[1] + hgt * 1.05)]
        cv.polygon(almond, (246, 246, 240))
        ir = hgt * 1.00
        ix = e[0] + f * w * 0.28
        cv.circle((ix, e[1] - hgt * 0.10), ir * 2.2, (255, 176, 84),
                  width=0, fill=(255, 176, 84), alpha=55 if i == 0 else 30)
        cv.circle((ix, e[1] - hgt * 0.10), ir, (250, 196, 108),
                  width=0, fill=(250, 196, 108))
        cv.circle((ix, e[1] - hgt * 0.10), ir * 0.46, (26, 20, 22),
                  width=0, fill=(26, 20, 22))
        cv.circle((ix - ir * 0.20, e[1] - hgt * 0.10 - ir * 0.32), ir * 0.30,
                  (255, 255, 252), width=0, fill=(255, 255, 252))
        # upper lid: a thin dark line hugging the top of the almond
        cv.polyline([(e[0] + f * w * 1.04, e[1] + r * 0.03 * s),
                     (e[0] + f * w * 0.10, e[1] - hgt * 1.30),
                     (e[0] - f * w * 1.02, e[1] - hgt * 0.40)],
                    r * 0.055 * s, dark)

    # ---- brow: thick at the temple, riding down toward the nose
    bz = c[1] - r * (0.46 + 0.03 * hurt)
    cv.polygon([(c[0] - f * r * 0.62, bz - r * 0.14),
                (c[0] + f * r * 0.54, bz + r * (0.16 - 0.05 * hurt)),
                (c[0] + f * r * 0.50, bz + r * (0.28 - 0.05 * hurt)),
                (c[0] - f * r * 0.64, bz + r * 0.08)], dark)
    for i, yy in enumerate((0.0, 0.14)):
        cv.line((c[0] - f * r * (0.32 - 0.04 * i), c[1] - r * (0.66 + yy)),
                (c[0] + f * r * (0.26 - 0.05 * i), c[1] - r * (0.62 + yy)),
                r * 0.04, dark, alpha=70, caps=False)

    # ---- mouth: clenched for effort, open with teeth showing for the finisher
    mx = c[0] + f * r * 0.62
    my = c[1] + r * 0.34
    if expr in ("ko", "hit"):
        gap = r * (0.17 if expr == "ko" else 0.10)
        cv.polygon([(mx - f * r * 0.16, my - gap * 0.3),
                    (mx + f * r * 0.16, my - gap * 0.2),
                    (mx + f * r * 0.13, my + gap), (mx - f * r * 0.15, my + gap * 0.8)],
                   (26, 14, 16))
        cv.polygon([(mx - f * r * 0.15, my - gap * 0.30),
                    (mx + f * r * 0.15, my - gap * 0.20),
                    (mx + f * r * 0.14, my), (mx - f * r * 0.15, my + gap * 0.10)],
                   (236, 234, 226))
    else:
        cv.polygon([(mx - f * r * 0.15, my), (mx + f * r * 0.14, my - r * 0.05),
                    (mx + f * r * 0.13, my + r * 0.02), (mx - f * r * 0.15, my + r * 0.07)],
                   dark, alpha=225)

    # ---- sweat and spit thrown off the impact
    for i in range(6):
        a = -1.1 + 0.40 * i
        dist = r * (0.62 + 1.7 * phase) * (1.0 + 0.10 * i)
        px = c[0] + f * math.cos(a) * dist
        py = c[1] + r * 0.05 + math.sin(a) * dist * 0.55
        cv.circle((px, py), r * (0.038 - 0.004 * i), (240, 246, 252),
                  width=0, fill=(240, 246, 252), alpha=max(0, int(160 * (1 - phase))))


SKULL = ((0.05, -1.00), (0.52, -0.86), (0.80, -0.52), (0.92, -0.28),
         (0.84, -0.16), (0.88, 0.00), (0.90, 0.10), (0.78, 0.20),
         (0.74, 0.34), (0.30, 0.36), (0.26, 0.46), (0.14, 0.72),
         (-0.06, 0.78), (-0.42, 0.60), (-0.60, 0.30), (-0.92, 0.05),
         (-0.90, -0.30), (-0.70, -0.75), (-0.35, -0.95))


def _xray(cv, c, r: float, f: int, phase: float) -> None:
    """The money shot: the skull taking the blow, in bone.

    A white disc with two rectangles in it is a diagram. What makes it a skull
    is the profile — brow ridge, nasion, nasal spine, maxilla, chin, jaw angle,
    occiput — so the silhouette is authored as a polygon and the orbits, the
    nasal aperture and the teeth are then cut out of it.
    """
    bone = (241, 243, 235)
    shade = (200, 205, 196)

    def path(dx=0.0, dy=0.0, k=1.0):
        return [(c[0] + f * x * r * k + dx, c[1] + y * r * k + dy) for x, y in SKULL]

    # the body in silhouette behind the bone, so the skull is attached to someone
    cv.polygon([(c[0] - r * 2.4, c[1] + r * 3.6), (c[0] - r * 1.7, c[1] + r * 1.55),
                (c[0] - r * 0.4, c[1] + r * 1.30), (c[0] + r * 0.9, c[1] + r * 1.45),
                (c[0] + r * 2.4, c[1] + r * 3.6)], (26, 34, 42))
    cv.circle((c[0] + f * r * 1.30, c[1] + r * 2.6), r * 0.95, (30, 38, 46),
              width=0, fill=(30, 38, 46))
    # the cranium, then a darker copy nudged back: a shadow side without an outline
    cv.polygon(path(-f * r * 0.10, r * 0.08), shade)
    cv.polygon(path(), bone)

    # orbit
    cv.polygon([(c[0] + f * r * 0.24, c[1] - r * 0.30),
                (c[0] + f * r * 0.62, c[1] - r * 0.20),
                (c[0] + f * r * 0.64, c[1] + r * 0.04),
                (c[0] + f * r * 0.30, c[1] + r * 0.06),
                (c[0] + f * r * 0.20, c[1] - r * 0.12)], (10, 15, 21))
    # nasal aperture, a pear pointing up
    cv.polygon([(c[0] + f * r * 0.60, c[1] + r * 0.02),
                (c[0] + f * r * 0.68, c[1] + r * 0.16),
                (c[0] + f * r * 0.52, c[1] + r * 0.22),
                (c[0] + f * r * 0.50, c[1] + r * 0.06)], (10, 15, 21))
    # zygomatic arch running back from the cheekbone
    cv.line((c[0] + f * r * 0.66, c[1] + r * 0.08),
            (c[0] - f * r * 0.14, c[1] + r * 0.34), r * 0.10, (10, 15, 21),
            alpha=200, caps=False)
    # teeth: one row, cut into the maxilla
    for i in range(6):
        x = c[0] + f * r * (0.66 - 0.075 * i)
        cv.polygon([(x, c[1] + r * 0.16), (x - f * r * 0.045, c[1] + r * 0.16),
                    (x - f * r * 0.04, c[1] + r * 0.31), (x + f * r * 0.005, c[1] + r * 0.31)],
                   (18, 23, 29))
    # mandible: the jaw is a separate bone, hanging under the maxilla
    cv.polygon([(c[0] + f * r * 0.72, c[1] + r * 0.26),
                (c[0] + f * r * 0.60, c[1] + r * 0.66),
                (c[0] + f * r * 0.16, c[1] + r * 0.80),
                (c[0] - f * r * 0.26, c[1] + r * 0.64),
                (c[0] - f * r * 0.16, c[1] + r * 0.48),
                (c[0] + f * r * 0.24, c[1] + r * 0.50),
                (c[0] + f * r * 0.48, c[1] + r * 0.42)], bone)
    cv.line((c[0] + f * r * 0.52, c[1] + r * 0.50),
            (c[0] - f * r * 0.10, c[1] + r * 0.66), r * 0.05, (18, 23, 29),
            alpha=170, caps=False)
    # cervical column: a dark gap for the discs, bone bodies on top of it
    _tube(cv, [(c[0] + f * r * 0.06, c[1] + r * 0.72),
               (c[0] - f * r * 0.02, c[1] + r * 1.30),
               (c[0] - f * r * 0.10, c[1] + r * 2.00)],
          [r * 0.34, r * 0.40, r * 0.46], (26, 34, 42))
    for i in range(5):
        yy = c[1] + r * (0.74 + 0.24 * i)
        cv.polygon([(c[0] + f * r * (0.22 - 0.03 * i), yy),
                    (c[0] - f * r * (0.20 - 0.03 * i), yy + r * 0.02),
                    (c[0] - f * r * (0.22 - 0.03 * i), yy + r * 0.15),
                    (c[0] + f * r * (0.24 - 0.03 * i), yy + r * 0.12)], bone)
        cv.line((c[0] - f * r * 0.18, yy + r * 0.155),
                (c[0] + f * r * 0.20, yy + r * 0.125), r * 0.04, (18, 23, 29),
                alpha=170, caps=False)
    # the fracture, opening with the impact
    if phase > 0.14:
        g = min(1.0, (phase - 0.14) / 0.40)
        crack = ((0.90, -0.34), (0.72, -0.42), (0.60, -0.26), (0.44, -0.32),
                 (0.38, -0.12), (0.46, 0.02), (0.26, 0.12), (0.20, 0.30),
                 (0.34, 0.40))
        pts = [(c[0] + f * x * r, c[1] + (y + (0.018 if i % 2 else -0.018) * g) * r)
               for i, (x, y) in enumerate(crack)]
        cv.polyline(pts, r * 0.022 * (0.5 + g), (150, 30, 30))
        cv.polyline([(x, y + r * 0.012 * g) for x, y in pts], r * 0.010, (60, 12, 12))
        # the bloom of the impact itself
        cv.circle((c[0] + f * r * 0.86, c[1] - r * 0.34), r * (0.42 + 0.5 * g),
                  (188, 36, 30), width=0, fill=(188, 36, 30),
                  alpha=int(80 * (1 - phase)))


def draw_insert(cv, cut, scene) -> None:
    """Compose one insert: backdrop, focus lines, bust, impact flash."""
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

    # the frame pushes in over the cut, and the head snaps back off the blow
    # and settles: two curves, one for the camera and one for the body
    push = 1.02 + 0.13 * (phase ** 0.6)
    kick = (1.0 - phase) ** 1.6
    c = (w * 0.50 + f * w * 0.06 - f * w * 0.055 * kick,
         h * 0.44 + h * 0.012 * kick)
    r = 190.0 * k * push

    _focus_lines(cv, c, r, tint=(255, 246, 226) if kind == "xray" else (236, 240, 250))
    if kind == "xray":
        _xray(cv, c, r, f, phase)
    else:
        hurt = 1.0 if expr in ("hit", "ko") else 0.4
        # a warm rim behind the head: the impact light
        cv.circle(c, r * 1.42, (255, 140, 70), width=0, fill=(255, 140, 70),
                  alpha=int(38 + 34 * (1 - abs(phase - 0.3) * 2)))
        _bust(cv, c, r, f, colour, dark, phase, expr, hurt)

    if kind != "xray" and phase < 0.55:
        g = 1.0 - phase / 0.55
        for i in range(5):
            a = -0.55 + 0.30 * i
            r0 = r * 1.30
            ln = r * (0.55 + 0.65 * g)
            p0 = (c[0] + f * math.cos(a) * r0, c[1] + math.sin(a) * r0)
            p1 = (c[0] + f * math.cos(a) * (r0 + ln), c[1] + math.sin(a) * (r0 + ln))
            cv.line(p0, p1, 5.0 * k * (0.4 + g), (255, 250, 238),
                    alpha=int(190 * g), caps=False)
    cv.flush()
