"""Air, earth, steel and blood: everything that is not a body.

The renderer draws the world in a strict order — plate, ground marks, shadows,
bodies, effects — and this module owns the three layers that were missing:

* **earth** (`ground_marks`): craters under every slam, blood where a shot split
  something open, and the dust a running fighter kicks up. Marks are permanent:
  they are laid on the floor at the moment they happen and are still there a
  minute later, which is what makes an arena feel used.
* **air** (`shockwaves`): on a clash or a heavy hit a translucent disc of
  compressed air snaps out and a ring rides its edge. Two frames of white star
  burst say "impact"; a wave that travels says "force".
* **light** (`bloom`, `impact_frame`): a cheap screen-space bloom so the eyes
  and the sparks bleed, and — on the heaviest hits — one or two frames of pure
  black with the two bodies in white ink over calligraphy, the anime impact
  frame.

Everything is deterministic: a given frame index renders the same picture every
time, in any order.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

#: how long a shockwave lives
WAVE_LIFE = 0.26
#: floor marks are laid on the ground plane, in design pixels
GROUND_Y = 590.0


# --------------------------------------------------------------------- helpers
def circle_xy(cv, c, rx: float, ry: float, colour, width: float = 0.0,
              fill=None, alpha: int = 255) -> None:
    """An ellipse ring or disc on the render canvas (``Canvas`` has no ellipse)."""
    if width and width > 0.0:
        n = max(24, int(min(72, 18 + rx * 0.5)))
        pts = [(c[0] + rx * math.cos(math.tau * i / n),
                c[1] + ry * math.sin(math.tau * i / n)) for i in range(n)]
        cv.polyline(pts + [pts[0]], width, colour, alpha=alpha)
    if fill is not None:
        n = max(24, int(min(72, 14 + rx * 0.35)))
        pts = [(c[0] + rx * math.cos(math.tau * i / n),
                c[1] + ry * math.sin(math.tau * i / n)) for i in range(n)]
        cv.polygon(pts, fill, alpha=alpha)


def _brush(cv, p0, p1, w0: float, w1: float, colour, alpha: int = 255) -> None:
    """A tapered stroke: thick at the start, thin at the end, round at both."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    cv.polygon([(p0[0] + nx * w0, p0[1] + ny * w0),
                (p1[0] + nx * w1, p1[1] + ny * w1),
                (p1[0] - nx * w1, p1[1] - ny * w1),
                (p0[0] - nx * w0, p0[1] - ny * w0)], colour, alpha=alpha)
    cv.disc(p0, w0, colour)
    cv.disc(p1, w1, colour)


# ------------------------------------------------------------------ running dust
def build_puffs(tracks, t0: float = 0.0, t1: float = 30.0) -> list:
    """Where a foot hits the ground hard enough to throw dust.

    Sampled once per scene from the same speed the footwork uses, so a fighter
    who runs kicks up a trail and one who stands still does not.
    """
    from . import footwork
    out = []
    step = 0.05
    t = t0
    while t < t1:
        for tr in tracks:
            v = footwork.speed(tr, t)
            a = footwork.accel(tr, t)
            if abs(v) > 170.0 or (abs(v) > 50.0 and a < -520.0):
                _, x = tr.sample(t)
                out.append((round(t, 3), round(x - tr.facing * 16.0, 2)))
        t += step
    return out


def draw_puffs(cv, puffs, t: float, ground: float = GROUND_Y) -> None:
    """Dust kicked up by the feet, in the last third of a second.

    Drawn as a translucent batch, not as solid discs: at 720p a solid pebble at
    a foot reads as a stone that was always there. It grows and fades instead.
    """
    u = cv.unit()
    live = [p for p in puffs if 0.0 <= t - p[0] < 0.30]
    if not live:
        return
    shapes = []
    for t0, x in live:
        k = (t - t0) / 0.30
        rng = np.random.default_rng(int(t0 * 1000) % 977)
        for j in range(3):
            ang = rng.uniform(-2.7, -0.4)
            dist = (3.0 + 20.0 * k) * u * rng.uniform(0.6, 1.4)
            c = cv.wp((x + math.cos(ang) * dist / u,
                       ground + math.sin(ang) * dist / u * 0.5))
            rr = (1.6 + 2.4 * k) * u * rng.uniform(0.7, 1.3)
            if rr > 0.5:
                shapes.append((c, rr, int(70 * (1 - k) ** 1.3)))
    if not shapes:
        return
    x0 = min(c[0] - r for c, r, _a in shapes) - 2
    y0 = min(c[1] - r for c, r, _a in shapes) - 2
    x1 = max(c[0] + r for c, r, _a in shapes) + 2
    y1 = max(c[1] + r for c, r, _a in shapes) + 2
    from .clashfilm import Overlay
    ov = Overlay(cv, (x0, y0, x1, y1))
    if ov.layer is None:
        return
    for c, r, a in shapes:
        ov.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r),
                   fill=(214, 204, 186, a))
    ov.flush()


# --------------------------------------------------------------------- shockwave
def shockwaves(cv, impacts, t: float) -> None:
    """Compressed air: a disc and a ring, on clashes and heavy blows."""
    u = cv.unit()
    for e in impacts:
        age = t - e["t"]
        size = e.get("size", 1.0)
        if size < 0.55 or not (0.0 <= age < WAVE_LIFE):
            continue
        if e.get("x") is None:
            continue
        k = age / WAVE_LIFE
        grow = 1.0 - (1.0 - k) ** 3
        cx, cy = cv.wp((e["x"], e["y"]))
        r = (14.0 + 62.0 * size) * u * (0.35 + 0.85 * grow)
        # a ring of air, not a lens flare: an ellipse seen slightly from below,
        # three strokes of falling alpha instead of one hard circle
        ry = r * 0.62
        for w, a in ((2.2, 150), (5.0, 58), (9.0, 22)):
            circle_xy(cv, (cx, cy), r, ry, (255, 253, 246), width=max(1.0, w * u),
                         alpha=int(a * (1 - k) ** 1.6 * min(1.5, size)))
        # and a wash of displaced air inside it
        if k < 0.75:
            circle_xy(cv, (cx, cy), r * 0.86, ry * 0.86, (255, 250, 240),
                         width=0, fill=(255, 250, 240),
                         alpha=int(26 * (1 - k / 0.75) ** 1.4 * size))


# ------------------------------------------------------------------ ground marks
def _crater(cv, x: float, r: float, u: float, alpha: float) -> None:
    """A scuffed ellipse with cracks running out of it."""
    cx, cy = cv.wp((x, GROUND_Y))
    rx, ry = r * u, r * u * 0.30
    cv.circle((cx, cy), rx, (24, 20, 18), width=0, fill=(24, 20, 18),
              alpha=int(70 * alpha))
    rng = np.random.default_rng(int(x * 7) % 9973)
    for i in range(7):
        a = rng.uniform(0, math.tau)
        ln = rx * rng.uniform(0.7, 1.9)
        p0 = (cx + math.cos(a) * rx * 0.7, cy + math.sin(a) * ry * 0.7)
        p1 = (cx + math.cos(a) * ln, cy + math.sin(a) * ln * 0.32)
        cv.line(p0, p1, max(1.0, 1.6 * u), (26, 22, 20), alpha=int(110 * alpha))
    for i in range(5):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(0.3, 1.1) * rx
        cv.disc((cx + math.cos(a) * d, cy + math.sin(a) * ry * 1.4),
                max(1.0, rng.uniform(1.2, 3.0) * u), (32, 27, 24))


def _blood_pool(cv, x: float, r: float, u: float, alpha: float) -> None:
    """A dark stain on the rock, not a red sticker.

    Built in a small RGBA patch and blurred before it is laid down: a hard disc
    of red at this size reads as litter on the floor, a soft blotch reads as
    something that soaked in.
    """
    cx, cy = cv.wp((x, GROUND_Y))
    rng = np.random.default_rng(int(x * 13) % 7919)
    pad = int(r * u * 2.2) + 6
    patch = Image.new("RGBA", (pad * 2, pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(patch)
    for i in range(5):
        dx = rng.uniform(-0.7, 0.7) * r * u
        dy = rng.uniform(-0.16, 0.30) * r * u
        rr = rng.uniform(0.30, 0.85) * r * u
        d.ellipse([pad + dx - rr, pad + dy - rr * 0.55,
                   pad + dx + rr, pad + dy + rr * 0.55],
                  fill=(72, 15, 19, int(185 * alpha)))
    patch = patch.filter(ImageFilter.GaussianBlur(max(1.0, r * u * 0.18)))
    cv.flush()
    cv.img.paste(patch, (int(cx - pad), int(cy - pad)), patch)
    cv.d = ImageDraw.Draw(cv.img)
    cv._draw = None


def marks(scene) -> list:
    """The permanent marks on the floor, built once per scene.

    Craters come from the slams (the same list that shakes the camera), pools of
    blood from the heaviest landed blows on a body. Both are keyed off the
    impact list, so re-choreographing moves the marks with the fight.
    """
    if "_marks" in scene:
        return scene["_marks"]
    out = []
    for e in scene["impacts"]:
        size = e.get("size", 1.0)
        if e.get("x") is None:
            continue
        if e["kind"] == "final":
            out.append({"t": e["t"] + 0.9, "x": e["x"] + 12.0, "r": 19.0,
                        "kind": "blood"})
        if e["kind"] == "final" and e.get("anchor") != "fists":
            out.append({"t": e["t"] + 0.02, "x": e["x"], "r": 26.0,
                        "kind": "crater"})
    for t0 in scene.get("dusts", []):
        tr = scene["red"] if scene["red"].sample(t0)[0].get("hip", 99) < 70 \
            else scene["blue"]
        out.append({"t": t0, "x": tr.sample(t0)[1], "r": 22.0, "kind": "crater"})
    scene["_marks"] = out
    return out


def draw_marks(cv, scene, t: float) -> None:
    """Lay the marks down in the order they happened, oldest first."""
    u = cv.unit()
    for m in marks(scene):
        age = t - m["t"]
        if age < 0.0:
            continue
        # a crater appears in a quarter of a second; blood creeps for longer
        grow = min(1.0, age / (0.22 if m["kind"] == "crater" else 0.9))
        a = 0.35 + 0.65 * grow
        if m["kind"] == "crater":
            _crater(cv, m["x"], m["r"] * (0.7 + 0.3 * grow), u, a)
        else:
            _blood_pool(cv, m["x"], m["r"] * (0.5 + 0.5 * grow), u, a)


# -------------------------------------------------------------------- blood spray
def blood_spray(cv, impacts, t: float) -> None:
    """A short, ugly burst at the moment a heavy shot lands."""
    u = cv.unit()
    for e in impacts:
        age = t - e["t"]
        size = e.get("size", 1.0)
        if size < 0.85 or e.get("x") is None:
            continue
        if not (0.0 <= age < 0.30):
            continue
        k = age / 0.30
        cx, cy = cv.wp((e["x"], e["y"]))
        rng = np.random.default_rng(int(e["t"] * 1000) % 4999)
        for i in range(9):
            a = rng.uniform(-math.pi, math.pi)
            spd = rng.uniform(0.4, 1.4) * (1.0 + e.get("dx", 0.0) * 0.5)
            d = (10 + 86 * k * spd) * u
            rr = max(0.8, (3.2 - 2.4 * k) * u * rng.uniform(0.6, 1.3))
            cv.disc((cx + math.cos(a) * d, cy + math.sin(a) * d * 0.8 + 18 * u * k),
                    rr, (108, 16, 20))


# ------------------------------------------------------------------- impact frame
#: hits big enough to deserve a drawn impact frame rather than a lens flare
IMPACT_FRAME = (10.94, 13.44, 15.80, 18.40, 18.98, 21.40, 23.28, 23.84, 24.72)
#: frames held. Two frames at 24 fps is the anime cut: long enough to read,
#: short enough that the eye fills in the motion
IMPACT_FRAMES = 2


def impact_frame_index(scene, t: float, fps: float = 24.0):
    """Is this instant inside a drawn impact frame, and how far into it.

    Only the *heavy* ones: a clash, the final blow, or a landed hit of size 1.0
    and up. A hard cut to ink on every jab would be a strobe, not an accent.
    """
    for e in scene["impacts"]:
        if e["kind"] == "block":
            continue
        if e["kind"] not in ("clash", "final") and e.get("size", 1.0) < 0.95:
            continue
        d = t - e["t"]
        if 0.0 <= d < IMPACT_FRAMES / fps * 1.0001:
            return e["t"], d * fps
    return None


def _arc(d, cx, cy, r, a0, a1, w0, w1, alpha, rng):
    """A tapered arc: the curved sweep that makes a stroke look brushed."""
    steps = 14
    for k in range(steps):
        f0, f1 = k / steps, (k + 1) / steps
        p0 = (cx + math.cos(a0 + (a1 - a0) * f0) * r,
              cy + math.sin(a0 + (a1 - a0) * f0) * r)
        p1 = (cx + math.cos(a0 + (a1 - a0) * f1) * r,
              cy + math.sin(a0 + (a1 - a0) * f1) * r)
        d.line([p0, p1], fill=alpha, width=max(1, int(w0 + (w1 - w0) * f0)))


def _glyph(d, cx, cy, size, rng):
    """One brush character.

    Not a real kanji — a typeface would be an asset — but thick tapered strokes
    of unequal weight, one of them curved, inside a rough square read as
    calligraphy at a glance. Thin even bars read as a hash mark, which is what
    the first version looked like.
    """
    def stroke(p0, p1, w0, w1, a):
        steps = 7
        for k in range(steps):
            f0, f1 = k / steps, (k + 1) / steps
            q0 = (p0[0] + (p1[0] - p0[0]) * f0, p0[1] + (p1[1] - p0[1]) * f0)
            q1 = (p0[0] + (p1[0] - p0[0]) * f1, p0[1] + (p1[1] - p0[1]) * f1)
            d.line([q0, q1], fill=a, width=max(1, int(w0 + (w1 - w0) * f0)))

    h = size * 0.5
    heavy, light = size * 0.105, size * 0.045
    # two bars, both wide, the lower one shorter and lower
    for r in range(2):
        y = cy - h * (0.42 - 0.75 * r)
        x0 = cx - h * (0.95 - 0.25 * r)
        x1 = cx + h * (0.70 + 0.25 * r)
        stroke((x0, y), (x1, y + rng.uniform(-0.04, 0.04) * size),
               heavy * rng.uniform(0.9, 1.15), light, int(rng.uniform(150, 225)))
    # one heavy vertical, slightly slanted
    x = cx + rng.uniform(-0.2, 0.2) * h
    stroke((x, cy - h * 0.95), (x + rng.uniform(-0.12, 0.12) * h, cy + h * 0.95),
           heavy, light, int(rng.uniform(150, 225)))
    # and a swept hook on one side
    if rng.random() < 0.85:
        _arc(d, cx, cy + h * 0.55, h * 0.62,
             math.pi * (0.05 + 0.2 * rng.random()), math.pi * (0.85 + 0.25 * rng.random()),
             heavy * 0.75, light * 0.6, int(rng.uniform(120, 200)), rng)


def _calligraphy(cv, seed: float) -> None:
    """A wall of ink behind the bodies: six big characters, deliberately free."""
    from PIL import ImageDraw
    w, h = cv.w, cv.h
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    rng = np.random.default_rng(int(seed * 1000) % 65521)
    spots = [(0.08, 0.28, 0.60), (0.88, 0.20, 0.50), (0.16, 0.82, 0.52),
             (0.78, 0.80, 0.56)]
    for sx, sy, sc in spots:
        _glyph(d, w * sx + rng.uniform(-0.03, 0.03) * w,
               h * sy + rng.uniform(-0.03, 0.03) * h,
               h * sc * rng.uniform(0.85, 1.1), rng)
    layer = layer.filter(ImageFilter.GaussianBlur(1.4))
    ink = Image.new("RGB", (w, h), (236, 230, 218))
    cv.flush()
    cv.img.paste(ink, (0, 0), layer.point(lambda v: int(v * 0.34)))
    cv.d = ImageDraw.Draw(cv.img)
    cv._draw = None


def impact_frame(cv, tracks, ta: float, seed: float, draw_fighter) -> None:
    """Black page, ink behind, the two bodies in white — the anime hit frame.

    The real silhouettes are drawn, through the real camera, with the fighter
    colours swapped for white: nothing is re-posed and nothing can drift out of
    step with the fight. ``draw_fighter`` is the renderer's own body painter.
    """
    from PIL import Image as _I
    w, h = cv.w, cv.h
    cv.flush()
    cv.img = _I.new("RGB", (w, h), (7, 6, 8))
    cv.d = ImageDraw.Draw(cv.img)
    cv._draw = None
    _calligraphy(cv, seed)
    saved = [(tr, tr.colour, tr.dark) for tr in tracks]
    for tr, _c, _d in saved:
        tr.colour, tr.dark = (250, 246, 238), (250, 246, 238)
    cv.mono = True
    for tr in tracks:
        draw_fighter(cv, tr, ta)
    cv.flush()
    cv.mono = False
    for tr, c, d in saved:
        tr.colour, tr.dark = c, d


# ------------------------------------------------------------------------- bloom
def bloom(img: Image.Image, amount: float = 0.55) -> Image.Image:
    """Cheap screen-space bloom: threshold, blur small, add back.

    A Gaussian on the full frame is 24 ms; a quarter-size copy is 3 ms and the
    eye cannot tell the difference at this softness.
    """
    sw, sh = max(1, img.width // 4), max(1, img.height // 4)
    small = img.resize((sw, sh), Image.BILINEAR)
    a = np.asarray(small, np.float32)
    lum = a.max(axis=2, keepdims=True)
    mask = np.clip((lum - 132.0) / 100.0, 0.0, 1.0)
    glow = Image.fromarray((a * mask).astype(np.uint8))
    glow = glow.filter(ImageFilter.GaussianBlur(5.0)).resize(img.size,
                                                             Image.BICUBIC)
    base = np.asarray(img, np.float32)
    out = np.clip(base + np.asarray(glow, np.float32) * amount, 0, 255)
    return Image.fromarray(out.astype(np.uint8))
