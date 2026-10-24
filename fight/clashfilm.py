"""Mountains Clash, 30 s test — renderer.

One frame = background crop (with camera drift and impact shake, vignette
already in the plate) -> contact shadows -> fighters -> motion trails -> impact
effects -> dust -> HUD (health bars, timer, titles, cinematic bars) -> fades.
Frames go straight into FFmpeg as raw RGB, never written to disk as stills, and
the synthesised WAV is muxed on afterwards.
"""
from __future__ import annotations

import math
import os
import subprocess
import time
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .camera import camera
from .layers import draw_foreground
from . import steelblade, vfx
from .blur import directional, shutter

FRAME = 1.0 / 24.0
from .clash import (BLUE, BLUE_DARK, DESIGN_H, DESIGN_W, DURATION, FIG_SCALE, FPS,
                    GROUND, INK, RED, RED_DARK, STANCE, build)
from .poses import to_pose
from .insert import CUTS as INSERTS, draw_insert
from .core import SEG, SEGMENT_ORDER, solve
from .draw import Canvas, Cam

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "assets")
SET_FILES = {"mountain": "mountain_background.png",
             "desert": "desert_background.png"}
#: a top-down floor plate, for the shots from above
GROUND_FILES = {"mountain": "ground_mountain.png", "desert": "ground_desert.png"}
GROUND_FILE_ASPECT = 1.0                       # both generated plates are square
SR = 44100

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_REG = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
FONT_MONO = os.path.join(FONT_DIR, "DejaVuSansMono-Bold.ttf")

# the reference pipeline: 1376x768 source -> 1320x742 -> a 1280x720 window
BG_W, BG_H = 1376, 768
BG_SCALED = (1320, 742)

_fonts: dict = {}


def font(size: int, mono: bool = False):
    key = (size, mono)
    if key not in _fonts:
        try:
            _fonts[key] = ImageFont.truetype(FONT_MONO if mono else FONT_REG, size)
        except OSError:
            _fonts[key] = ImageFont.load_default()
    return _fonts[key]


# ------------------------------------------------------------------ background
# The landscape never moves in 3D: the camera is a crop of one painted plate.
# Panning + a slow push-in used to mean a fresh 1280x720 resample every frame
# (11 ms of the 38 ms it took to build a frame). Instead the plate is scaled to
# every zoom level once, at startup, with the vignette already baked in, and a
# frame is then an integer crop, blended with the neighbouring level by the
# fraction of a step it sits between. The blend is what keeps the push-in from
# stepping; it softens the frame by under a quarter of a pixel, measured.
BG_PAD_X, BG_PAD_Y = 20, 11          # how far the camera may pan
ZOOM_LEVELS = 65                     # 0.6 px of scale between neighbours: the
#                                      blend that hides the stepping costs 0.2 px
#                                      of sharpness, measured, not assumed
_bg_cache: dict = {}


def _plate(path: str) -> Image.Image:
    """The painted plate, at its own resolution, vignette baked in.

    There used to be a ladder of 65 pre-zoomed plates: a frame was an integer
    crop, which was fast but froze the camera at one place. Now the camera
    moves, so a frame is a resample of one high-res plate. The vignette is
    baked into the plate rather than composited per frame: a full-frame alpha
    composite costs ~8 ms, and this way it is free.
    """
    if isinstance(path, tuple):                 # ("high", set) -> composite
        return _high_plate(path[1])
    key = ("plate", path)
    if _bg_cache.get("key") == key:
        return _bg_cache["plate"]
    from PIL import Image as _I
    src = _I.open(path).convert("RGB")
    # exact 16:9, so a crop at zoom 1 fills the frame instead of coming up a few
    # pixels short on one axis. Cover-crop, not letterbox: the painted plates are
    # a hair wider than 16:9, the generated ground plates are square, and a
    # square source used to leave black bars down the sides.
    want_w = round(src.height * DESIGN_W / DESIGN_H)
    want_h = round(src.width * DESIGN_H / DESIGN_W)
    if src.width > want_w:
        x0 = (src.width - want_w) // 2
        src = src.crop((x0, 0, x0 + want_w, src.height))
    elif src.height > want_h:
        y0 = (src.height - want_h) // 2
        src = src.crop((0, y0, src.width, y0 + want_h))
    vig = vignette()
    if vig.size != src.size:
        vig = vig.resize(src.size, _I.LANCZOS)
    src = _I.alpha_composite(src.convert("RGBA"), vig).convert("RGB")
    if os.path.basename(path).startswith("ground_"):
        # a floor plate seen from straight above is lit flat and reads much
        # brighter than the landscape it replaces, so it is pulled down and
        # cooled a touch: the fighters have to be the brightest thing in shot
        src = _I.merge("RGB", [ch.point(lambda v, f=f: int(v * f))
                               for ch, f in zip(src.split(), (0.80, 0.81, 0.86))])
    _bg_cache["plate"] = src
    _bg_cache["key"] = key
    return src


def _high_plate(set_name: str) -> Image.Image:
    """The plate for a raised camera: the arena floor in perspective.

    A straight-down view cannot work here — the fight is staged in a plane
    parallel to the lens, so from directly above both fighters would collapse
    into a line, and drawing a side-view body on a top-down floor plate (the
    first attempt) reads as a sticker on a texture. What a raised camera really
    does is show the ground receding to a horizon, so the floor plate is mapped
    through a perspective mesh: rows near the horizon are compressed and narrow,
    rows at the feet are stretched wide, and the painted landscape sits above
    the horizon line.
    """
    key = ("high", set_name)
    if _bg_cache.get("key") == key:
        return _bg_cache["plate"]
    from PIL import Image as _I
    w, h = DESIGN_W * 2, DESIGN_H * 2
    far = _plate(os.path.join(ASSETS, SET_FILES.get(set_name, "mountain_background.png")))
    floor = _plate(os.path.join(ASSETS, GROUND_FILES.get(set_name, "ground_mountain.png")))
    horizon = int(h * 0.46)
    out = Image.new("RGB", (w, h))
    # sky and peaks above the horizon: the top of the landscape, squashed
    strip = far.resize((w, int(h * 0.70)), _I.BILINEAR).crop((0, 0, w, horizon))
    out.paste(strip, (0, 0))

    # the floor: rows near the horizon compress and widen, rows at the feet are
    # stretched and narrow — the inverse-perspective row map, built at a quarter
    # of the frame size and upscaled (it is a soft background either way)
    fh = h - horizon
    R, CW = 168, 480
    src = np.asarray(floor, dtype=np.uint8)
    sh_, sw_ = src.shape[:2]
    rows = np.zeros((R, CW, 3), np.uint8)
    xs0 = np.arange(CW)
    norm = 1.0 - 1.0 / (1.0 + 4.2)
    for j in range(R):
        t = (j + 0.5) / R
        va = (1.0 - 1.0 / (1.0 + 4.2 * t)) / norm
        v = min(sh_ - 1, int(va * (sh_ - 1)))
        k = 0.22 + 0.68 * (1.0 - t) ** 1.3
        xs = np.clip(((xs0 - CW * 0.5) / CW * k + 0.5) * sw_, 0, sw_ - 1).astype(int)
        rows[j] = src[v][xs]
    out.paste(_I.fromarray(rows).resize((w, fh), _I.BILINEAR), (0, horizon))

    # haze along the horizon: without it the two plates meet in a hard line
    haze = Image.new("L", (w, h), 0)
    hd = ImageDraw.Draw(haze)
    band = int(h * 0.14)
    for i in range(band):
        y = horizon - band // 2 + i
        if 0 <= y < h:
            hd.line([(0, y), (w, y)], fill=int(150 * math.sin(math.pi * i / band) ** 0.7))
    tint = Image.new("RGB", (w, h), (226, 208, 188) if set_name == "mountain"
                     else (232, 206, 172))
    out = Image.composite(tint, out, haze.point(lambda v: int(v * 0.5)))
    src = out
    vig = vignette()
    if vig.size != src.size:
        vig = vig.resize(src.size, _I.LANCZOS)
    src = _I.alpha_composite(src.convert("RGBA"), vig).convert("RGB")
    _bg_cache["plate"] = src
    _bg_cache["key"] = key
    return src


def background(cx: float, cy: float, zoom: float, w: int, h: int, path: str):
    """The plate as the camera sees it: a crop around (cx, cy) at ``zoom``.

    Design space maps onto the plate 1:1 at zoom 1, so a crop is a straight
    scale of the design coordinates.
    """
    src = _plate(path)
    k = (src.width / DESIGN_W) / max(zoom, 1.0)
    rw, rh = w * k, h * k
    u = cx * src.width / DESIGN_W
    v = cy * src.height / DESIGN_H
    x0 = min(max(0.0, u - rw * 0.5), max(0.0, src.width - rw))
    y0 = min(max(0.0, v - rh * 0.5), max(0.0, src.height - rh))
    return src.resize((w, h), Image.BILINEAR, box=(x0, y0, x0 + rw, y0 + rh))


def vignette() -> Image.Image:
    """Soft vertical + radial darkening so the fighters read against the peaks."""
    if "v" in _bg_cache:
        return _bg_cache["v"]
    w, h = DESIGN_W, DESIGN_H
    yy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    edge = 1.0 - 0.22 * (yy ** 2.2) - 0.10 * ((1.0 - yy) ** 2.6)
    xx = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    edge = edge * (1.0 - 0.16 * (np.abs(xx) ** 2.6))
    alpha = np.clip((1.0 - edge) * 255.0 * 1.35, 0, 255).astype(np.uint8)
    layer = np.zeros((h, w, 4), np.uint8)
    layer[..., 0] = 14
    layer[..., 1] = 12
    layer[..., 2] = 16
    layer[..., 3] = alpha
    _bg_cache["v"] = Image.fromarray(layer, "RGBA")
    return _bg_cache["v"]


# ---------------------------------------------------------------------- camera
# --------------------------------------------------------------------- drawing
def draw_background(cv: Canvas, cam: dict, scene, w: int = DESIGN_W,
                    h: int = DESIGN_H) -> None:
    """Paint the plate where the camera is looking, then blur it if the shot is
    a close one (the fighters are always sharp: the lens is on them)."""
    from .camera import background_parallax
    bx, by = background_parallax(cam)
    # from above the painted landscape is not in shot at all: the floor is
    bg = background(bx, by, cam["zoom"], w, h,
                    ("high", scene["set"]) if cam.get("high") else scene["bg_path"])
    if cam["dof"] > 0.02:
        # bokeh the cheap way: blur a sixth-size copy and blow it back up. A
        # Gaussian on the full frame costs 24 ms; this costs 2 and reads softer
        small = bg.resize((w // 6, h // 6), Image.BILINEAR)
        r = 0.8 + 2.4 * cam["dof"]
        bg = small.filter(ImageFilter.GaussianBlur(r)).resize(
            (w, h), Image.BICUBIC)
    cv.img = bg
    cv.d = ImageDraw.Draw(bg)
    cv._draw = None


class Overlay:
    """A batch of translucent shapes drawn into one small patch.

    Compositing a full 1280x720 layer costs ~8 ms; the shadows under two
    fighters and the dust of a landing only cover a few hundred pixels wide
    band, so the patch is a bounding box and the composite is one small paste.
    """

    def __init__(self, cv: Canvas, box):
        x0, y0, x1, y1 = box
        x0 = max(0, int(math.floor(x0)))
        y0 = max(0, int(math.floor(y0)))
        x1 = min(cv.w, int(math.ceil(x1)))
        y1 = min(cv.h, int(math.ceil(y1)))
        if x1 - x0 < 1 or y1 - y0 < 1:
            self.layer = None
            return
        self.cv, self.ox, self.oy = cv, x0, y0
        self.box = (x0, y0, x1, y1)
        self.layer = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.layer)

    def ellipse(self, box, fill):
        if self.layer is None:
            return
        x0, y0, x1, y1 = box
        self.d.ellipse([x0 - self.ox, y0 - self.oy, x1 - self.ox, y1 - self.oy],
                       fill=fill)

    def flush(self):
        if self.layer is None:
            return
        cv = self.cv
        cv.flush()
        region = cv.img.crop(self.box).convert("RGBA")
        out = Image.alpha_composite(region, self.layer)
        cv.img.paste(out.convert("RGB"), self.box[:2])
        cv.d = ImageDraw.Draw(cv.img)
        self.layer = None


_scene_cache = {}


def cuts_of(scene):
    return scene.get("cuts") or INSERTS


def cut_at(t: float, scene=None):
    """The close-up register: instant on the blow, then a held push-in."""
    for start, dur, side, expr, kind in cuts_of(scene or {}):
        if start <= t < start + dur:
            return (start, dur, side, expr, kind), (t - start) / dur
    return None


def scene(set_name: str = "mountain"):
    """The choreography is deterministic: build it once per process and set."""
    if set_name not in _scene_cache:
        if set_name.startswith("steel"):
            from .steel import build as steel_build
            base = "desert" if "desert" in set_name else "mountain"
            sc = steel_build(base)
        else:
            base = set_name
            sc = build(set_name)
        sc["bg_path"] = os.path.join(ASSETS, SET_FILES.get(base, "mountain_background.png"))
        sc["ground_path"] = os.path.join(
            ASSETS, GROUND_FILES.get(base, "ground_mountain.png"))
        sc["puffs"] = vfx.build_puffs((sc["red"], sc["blue"]))
        _scene_cache[set_name] = sc
    return _scene_cache[set_name]


def shadow_box(cv: Canvas, sk, lift: float):
    """Where the contact shadow of one fighter sits, in screen pixels.

    Measured from the body's own horizontal extent, so a fighter lying on the
    floor gets a long thin shadow under the whole body instead of a round blob
    under a pair of feet that are nowhere near it.
    """
    xs = [p[0] for p in sk.pts.values()] + [sk.head[0]]
    cx = (min(xs) + max(xs)) * 0.5
    span = (max(xs) - min(xs)) * 0.5
    c = cv.wp((cx, GROUND - 2))
    if cv.cam.sqy < 0.98:
        # from above the shadow falls away from the body, long and to one side
        c = (c[0] + 18.0 * cv.unit(), c[1] + 8.0 * cv.unit())
    # a body in the air casts a shadow that shrinks and thins: the lift term is
    # negative on purpose, the opposite of what it used to do
    rx = (26.0 + span * 0.86 - 14.0 * min(1.6, lift)) * cv.unit() * sk.scale
    if cv.cam.sqy < 0.98:
        # from above the shadow is a pool at the feet, not a band across the
        # floor: keep it under the body or the patch reads as a grey slab
        rx *= 0.80
    lying = sk.pts[1][1] > GROUND - 74.0
    ry = rx * (0.085 if lying else (0.125 - 0.02 * min(lift, 1.0)))
    return (c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry)


def shadow(ov: "Overlay", sk, lift: float) -> None:
    """A flat contact shadow: wide and faint under an airborne fighter."""
    if ov.layer is None:
        return
    alpha = int(max(9, 62 - 34 * lift))
    if ov.cv.cam.sqy < 0.98:
        # from above the shadow is the main thing separating a body from the rock
        alpha = int(min(80, alpha * 1.5))
    ov.ellipse(shadow_box(ov.cv, sk, lift), fill=(20, 16, 14, alpha))


# ------------------------------------------------------------------- anatomy
# A body is a set of tapered tubes with a width profile, not a row of sticks.
# The numbers are rig units (the same space the poses are authored in):
# deltoid and biceps wider than the elbow, quad wider than the knee, calf wider
# than the ankle — that is all it takes for a limb to stop reading as a pipe.
SPINE_W = (14.6, 13.2, 11.8, 11.1, 12.3, 13.9, 14.8, 13.4, 12.2)  # 9 samples
ARM_W = (11.6, 11.2, 8.8)          # shoulder, biceps, elbow
FORE_W = (8.8, 8.4, 7.6)           # elbow, forearm, wrist
THIGH_W = (13.4, 14.3, 10.4)       # hip, quad, knee
SHIN_W = (10.4, 11.5, 6.4)         # knee, calf, ankle
FOOT_LEN, FOOT_HEEL, FOOT_T = 22.0, 6.0, 8.6
FIST_R, PALM_R, FINGER_L = 12.5, 8.6, 10.5
STRETCH_MAX = 0.26                 # how much a limb may elongate while swinging


def _capsule(cv: Canvas, a, b, w0: float, w1: float, colour, alpha: int = 255) -> None:
    """A tapered bone with rounded ends, and no cap wider than the bone."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    r0, r1 = w0 * 0.5, w1 * 0.5
    cv.polygon([(a[0] + nx * r0, a[1] + ny * r0),
                (b[0] + nx * r1, b[1] + ny * r1),
                (b[0] - nx * r1, b[1] - ny * r1),
                (a[0] - nx * r0, a[1] - ny * r0)], colour, alpha=alpha)
    if r0 > 0.4:
        cv.circle(a, r0, colour, width=0, fill=colour, alpha=alpha)
    if r1 > 0.4:
        cv.circle(b, r1, colour, width=0, fill=colour, alpha=alpha)


def _tube(cv: Canvas, pts, widths, colour, alpha: int = 255) -> None:
    """Draw a chain as one smooth tube: capsule per span, disc at every joint."""
    for i in range(len(pts) - 1):
        _capsule(cv, pts[i], pts[i + 1], widths[i], widths[i + 1], colour, alpha)


def _bend(pts, dirx: float, diry: float, k: float):
    """Bow a chain: the joints lag behind the direction of travel.

    This is the cheap half of squash & stretch — a swinging arm or leg arcs
    instead of rotating like a compass needle.
    """
    if k <= 0.0 or len(pts) < 3:
        return list(pts)
    n = len(pts) - 1
    out = [pts[0]]
    for i in range(1, n):
        f = 1.0 - abs(i / n - 0.5) * 1.1
        out.append((pts[i][0] - dirx * k * f, pts[i][1] - diry * k * f))
    out.append(pts[-1])
    return out


def _swing_deform(joints, vel, k: float, stretch: float):
    """Elongate a limb along its own motion and thin it while it travels."""
    if k <= 0.0:
        return joints, 1.0
    sx, sy = joints[0][0]
    ex, ey = joints[-1][0]
    dx, dy = ex - sx, ey - sy
    L = math.hypot(dx, dy) or 1.0
    vx, vy = vel
    sp = math.hypot(vx, vy) or 1.0
    align = max(0.0, (dx * vx + dy * vy) / (L * sp))
    amt = STRETCH_MAX * stretch * k * align
    vdir = (vx / sp, vy / sp)
    out = []
    for i, (p, w) in enumerate(joints):
        f = i / (len(joints) - 1)
        # stretch grows along the limb and reaches the tip
        px = sx + (p[0] - sx) * (1 + amt * f)
        py = sy + (p[1] - sy) * (1 + amt * f)
        # and the joints trail a little behind the swing
        drag = 3.2 * k * (1.0 - abs(f - 0.5) * 1.2) * (1 - f * 0.35)
        out.append(((px - vdir[0] * drag, py - vdir[1] * drag), w * (1.0 - 0.22 * amt)))
    return out, 1.0


def _tube_pts(joints):
    """Expand (point, width) joints into a dense chain so the tapers are smooth."""
    pts, ws = [joints[0][0]], [joints[0][1]]
    for (pa, wa), (pb, wb) in zip(joints, joints[1:]):
        pts.append(((pa[0] + pb[0]) * 0.5, (pa[1] + pb[1]) * 0.5))
        ws.append((wa + wb) * 0.5)
        pts.append(pb)
        ws.append(wb)
    return pts, ws


def _lerp(p, q, f):
    return (p[0] + (q[0] - p[0]) * f, p[1] + (q[1] - p[1]) * f)


def _limb(cv: Canvas, pts, widths, colour, cap=None, alpha: int = 255) -> tuple:
    """A whole limb as ONE polygon: the chain, then the hand or the foot.

    The old build drew the arm and its fist (or the leg and its foot) as two
    shapes that merely met at the joint, so the join read as a seam — a notch
    where the thin end of one piece hit the wide end of the other. Here the
    silhouette is swept once: down one side of the chain, around the hand or
    foot, and back up the other side. One polygon, no seam.

    Returns the points actually drawn, so the caller can hang details off them.
    """
    n = len(pts)
    left, right = [], []
    for i in range(n):
        if i == 0:
            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
            d = math.hypot(dx, dy) or 1.0
            dx, dy = dx / d, dy / d
        elif i == n - 1:
            dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
            d = math.hypot(dx, dy) or 1.0
            dx, dy = dx / d, dy / d
        else:
            ax, ay = pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]
            bx, by = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
            la, lb = math.hypot(ax, ay) or 1.0, math.hypot(bx, by) or 1.0
            dx, dy = ax / la + bx / lb, ay / la + by / lb
            d = math.hypot(dx, dy) or 1.0
            dx, dy = dx / d, dy / d
        nx, ny = -dy, dx
        hw = widths[i] * 0.5
        left.append((pts[i][0] + nx * hw, pts[i][1] + ny * hw))
        right.append((pts[i][0] - nx * hw, pts[i][1] - ny * hw))
    poly = list(left)
    if cap:
        poly += list(cap)
    poly += right[::-1]
    cv.polygon(poly, colour, alpha=alpha)
    return poly


def _foot_pts(ankle, tilt: float, facing: int, drop: float):
    """The foot silhouette, walked from the ankle round the toe and the heel.

    ``drop`` is how far the sole sits below the ankle: a planted foot drops all
    the way to the floor line, so the sole of every standing foot lands on the
    same ground plane instead of hovering wherever the IK left the ankle.
    """
    L, hb, t = FOOT_LEN, FOOT_HEEL, FOOT_T
    rot = tilt * facing
    ca, sa = math.cos(rot), math.sin(rot)

    def w(x, y):
        x *= facing
        return (ankle[0] + x * ca - y * sa, ankle[1] + x * sa + y * ca)

    return [w(-hb * 0.52, -t * 0.16),          # back of the ankle
            w(-hb * 0.14, -t * 0.50),          # Achilles into the instep
            w(L * 0.34, -t * 0.46),            # instep crest
            w(L * 0.74, -t * 0.26),            # top of the foot
            w(L, -t * 0.06),                   # toe cap
            w(L * 0.96, drop * 0.72),          # toe
            w(L * 0.60, drop),                 # sole under the toes
            w(L * 0.02, drop),                 # sole
            w(-hb, drop * 0.66),               # heel
            w(-hb * 0.98, t * 0.04)]           # back of the heel


def _fist_pts(centre, ang: float, r: float):
    """A closed fist as a ring of points, thrown forward of the wrist."""
    ca, sa = math.cos(ang), math.sin(ang)
    out = []
    for deg in (168, 120, 62, 0, -62, -120, -168):
        a = math.radians(deg)
        rr = r * (1.0 if abs(deg) < 100 else 0.86)
        x, y = math.cos(a) * rr * 1.04, math.sin(a) * rr * 0.86
        out.append((centre[0] + x * ca - y * sa, centre[1] + x * sa + y * ca))
    return out


def _hand_open(cv, wrist, ang: float, grip: float, colour, u: float,
               alpha: int = 255) -> None:
    """An open hand: the fingers fan out of the palm, which the limb already
    covers, so only the fingers are drawn on top of the one-piece silhouette."""
    open_k = 1.0 - grip / 0.5
    for i, spread in enumerate((-0.30, -0.04, 0.22, 0.52)):
        a2 = ang + spread * (0.4 + 0.6 * open_k)
        ln = FINGER_L * u * (0.80 if i == 3 else 1.0) * max(0.15, open_k)
        tip = (wrist[0] + math.cos(a2) * ln, wrist[1] + math.sin(a2) * ln)
        _capsule(cv, wrist, tip, 4.6 * u, 3.0 * u, colour, alpha)


def _head(cv: Canvas, c, r: float, facing: int, colour, dark, u: float,
          glow: float = 0.0, hurt: float = 0.0) -> None:
    """The head: skull, jaw, and an anime eye under a hard brow.

    A flat circle reads as a ball on a stick. Three shapes turn it into a face:
    a jaw pushed toward the facing direction, a white eye lens with a dark iris,
    and a brow that slants down toward the nose — the slant is the expression,
    and it steepens when the fighter is swinging or taking a shot.
    """
    fx = facing
    cv.circle(c, r, colour, width=0, fill=colour)
    cv.circle((c[0] + fx * r * 0.17, c[1] + r * 0.34), r * 0.60, colour,
              width=0, fill=colour)
    # muzzle / brow ridge, so the profile has a nose instead of a smooth ball
    cv.polygon([(c[0] + fx * r * 0.86, c[1] - r * 0.02),
                (c[0] + fx * r * 1.02, c[1] + r * 0.10),
                (c[0] + fx * r * 0.80, c[1] + r * 0.16),
                (c[0] + fx * r * 0.70, c[1] + r * 0.02)], colour)

    if getattr(cv, "mono", False):
        # the ink frame: one black slash where the eye is, and nothing else —
        # a face painted in white on black has no room for an iris
        cv.line((c[0] - fx * r * 0.55, c[1] - r * 0.16),
                (c[0] + fx * r * 0.55, c[1] - r * 0.28),
                max(2.0, 0.22 * r), INK, alpha=255, caps=True)
        return

    ex = c[0] + fx * r * 0.32
    ey = c[1] - r * 0.06
    # a small almond, not a mask: at forty pixels the head only has room for a
    # dot of an eye and a line of brow, and anything bigger turns the face into
    # a dark smear with a slash across it
    front = (ex + fx * r * 0.19, ey + r * 0.03)      # toward the nose, low
    back = (ex - fx * r * 0.19, ey - r * 0.05)       # outer corner, high
    topm = (ex + fx * r * 0.01, ey - r * 0.10)
    botm = (ex + fx * r * 0.00, ey + r * 0.07)
    cv.polygon([front, topm, back, botm], dark)
    # the iris burns inside the socket: this is the "glowing eye", and it is
    # what carries the expression when the head is only forty pixels across
    ix, iy = ex + fx * r * 0.10, ey - r * 0.02
    ir = r * (0.062 + 0.020 * min(1.0, glow))
    if glow > 0.02:
        # the aura: bloom picks this up and the eye reads as lit from inside
        cv.circle((ix, iy), ir * 4.6, (255, 190, 110),
                  width=0, fill=(255, 190, 110), alpha=int(26 + 78 * glow))
        cv.circle((ix, iy), ir * 2.4, (255, 208, 140),
                  width=0, fill=(255, 208, 140), alpha=int(40 + 120 * glow))
    cv.circle((ix, iy), ir, (255, 226, 158), width=0, fill=(255, 226, 158))
    cv.circle((ix + fx * ir * 0.18, iy - ir * 0.22), ir * 0.44, (255, 252, 240),
              width=0, fill=(255, 252, 240))
    # the brow is a thin stroke *above* the eye, never a slab welded to it: at
    # this size a filled wedge turns the whole face into one dark smear
    droop = 0.05 + 0.12 * hurt - 0.03 * min(1.0, glow)
    cv.line((ex - fx * r * 0.22, ey - r * 0.34 - r * droop * 0.5),
            (ex + fx * r * 0.22, ey - r * 0.28 + r * droop),
            max(1.4, 0.055 * r), dark, alpha=215, caps=True)

    # a short mouth line, thinner than the socket, pulled down when hurt
    mx, my = c[0] + fx * r * 0.46, c[1] + r * 0.40
    cv.line((mx - fx * r * 0.15, my - r * 0.02),
            (mx + fx * r * 0.13, my - r * 0.02 - r * 0.04 * hurt),
            2.6 * u, dark, alpha=170, caps=False)


def _speed(now, then, sid: int, dt: float = 0.05):
    """Where a limb tip is heading and how fast, in design units per second."""
    a = then.pts[sid]
    b = now.pts[sid]
    return (b[0] - a[0], b[1] - a[1]), math.hypot(b[0] - a[0], b[1] - a[1]) / dt


def pose_of(track, t: float, squash: float = 0.0, push: float = 0.0):
    """The drawable pose: choreography, footwork, the blow, then the IK solve.

    Footwork is applied *before* ``to_pose`` because it only edits the pose dict
    — the foot offsets and lifts the step cycle computes — so the leg IK still
    does the solve it was tuned against.
    """
    from . import footwork
    from .impact import compress
    p, x = track.sample(t)
    p = footwork.apply(track, t, p)
    if squash > 0.002:
        p = compress(p, squash)
    return to_pose(p, x + push, GROUND, facing=track.facing,
                   scale=FIG_SCALE, widen=STANCE)


def body(track, t: float, squash: float = 0.0, push: float = 0.0):
    """The skeleton of one fighter at animation time ``t``.

    ``squash`` folds the pose around the blow that just landed (see
    ``impact.compress``) and ``push`` shoves it back off its feet; both come
    from the same envelope, so the shadow and the smear follow the body.
    """
    return solve(pose_of(track, t, squash, push))


def draw_fighter(cv: Canvas, track, t: float) -> None:
    """The body: bowed spine, tapered limbs, feet on the floor, hands, face.

    The skeleton still comes from the same IK solve the choreography was written
    against — the anatomy only changes how that skeleton is painted, plus the
    speed-driven deformation (stretch along the swing, joints trailing behind).
    """
    squash = getattr(track, "_squash", 0.0)
    push = getattr(track, "_push", 0.0)
    pose = pose_of(track, t, squash, push)
    sk = solve(pose)
    u = cv.unit() * pose.scale
    colour, dark = track.colour, track.dark
    g = GROUND

    then = body(track, max(0.0, t - 0.05), squash, push) if t > 0.06 else sk

    def k_of(sid: int):
        vel, spd = _speed(sk, then, sid)
        return vel, min(1.0, max(0.0, (spd - 300.0) / 850.0))

    def arm(sid_up: int, sid_lo: int, grip: float, col):
        sh, elbow, wrist = sk.starts[sid_up], sk.pts[sid_up], sk.pts[sid_lo]
        vel, k = k_of(sid_lo)
        joints = [(sh, ARM_W[0] * u),
                  (_lerp(sh, elbow, 0.45), ARM_W[1] * u),
                  (elbow, ARM_W[2] * u),
                  (_lerp(elbow, wrist, 0.55), FORE_W[1] * u),
                  (wrist, FORE_W[2] * u)]
        joints, _ = _swing_deform(joints, vel, k, 1.0)
        sp = math.hypot(*vel) or 1.0
        pts = [p for p, _w in joints]
        pts = _bend(pts, vel[0] / sp, vel[1] / sp, 2.2 * u * k)
        widths = [w for _p, w in joints]
        # the limb is drawn once, all the way through the hand
        ang = sk.tip_angle(sid_lo)
        cap = None
        if grip > 0.5:
            r = FIST_R * (0.94 + 0.10 * grip)
            centre = (wrist[0] + math.cos(ang) * r * 0.46,
                      wrist[1] + math.sin(ang) * r * 0.46)
            cap = _fist_pts(centre, ang, r)
        else:
            cap = _fist_pts(wrist, ang, PALM_R * 0.92)
        tp, tw = _tube_pts(list(zip(pts, widths)))
        _limb(cv, [cv.wp(p) for p in tp], list(tw), col, cap=[cv.wp(p) for p in cap])
        if grip <= 0.5:
            _hand_open(cv, cv.wp(wrist), ang, grip, col, u)

    def leg(sid_up: int, sid_lo: int, pitch: float, col):
        hip, knee, ankle = sk.starts[sid_up], sk.pts[sid_up], sk.pts[sid_lo]
        vel, k = k_of(sid_lo)
        joints = [(hip, THIGH_W[0] * u),
                  (_lerp(hip, knee, 0.45), THIGH_W[1] * u),
                  (knee, THIGH_W[2] * u),
                  (_lerp(knee, ankle, 0.42), SHIN_W[1] * u),
                  (ankle, SHIN_W[2] * u)]
        joints, _ = _swing_deform(joints, vel, k, 0.85)
        sp = math.hypot(*vel) or 1.0
        pts = [p for p, _w in joints]
        pts = _bend(pts, vel[0] / sp, vel[1] / sp, 2.2 * u * k)
        widths = [w for _p, w in joints]
        ank = pts[-1]
        planted = (pose.lift_a if sid_lo == 8 else pose.lift_b) <= 0.6
        fwd = 0.0 if pose.facing > 0 else math.pi
        if planted:
            # the IK leaves the ankle a little above the floor, so the shin is
            # carried down to where the ankle bone would be and the sole is put
            # on the floor line: a foot of a fixed height, on the ground, always
            sole = g - 3.0
            drop = FOOT_T * 0.62
            ank = (ank[0] + pose.facing * 1.6, sole - drop)
            pts = pts[:-1] + [ank]
            tilt = 0.0
        else:
            # a foot in the air points along the shin only when the shin is
            # already driving forward (a kick); a foot merely off the floor
            # hangs flat instead of pointing at the ground behind
            drop = FOOT_T * 0.62
            sh = sk.tip_angle(sid_lo)
            if math.sin(sh) < -0.15:
                tilt = 1.48
            else:
                align = max(0.0, math.cos(sh - fwd))
                rel = (sh - fwd + math.pi) % (2 * math.pi) - math.pi
                rel = max(-0.35, min(1.30, rel))
                tilt = rel * (0.18 + 0.82 * align) + pitch
        cap = _foot_pts(ank, tilt, pose.facing, drop)
        tp, tw = _tube_pts(list(zip(pts, widths)))
        wp = [cv.wp(p) for p in tp]
        capw = [cv.wp(p) for p in cap]
        # start the cap at the end of the left side, so the outline never crosses
        if (capw[0][0] - wp[-1][0]) ** 2 + (capw[0][1] - wp[-1][1]) ** 2 > \
           (capw[-1][0] - wp[-1][0]) ** 2 + (capw[-1][1] - wp[-1][1]) ** 2:
            capw = capw[::-1]
        _limb(cv, wp, list(tw), col, cap=capw)

    # far limbs in the darker tone first: depth without an outline
    leg(7, 8, pose.pitch_a, dark)
    arm(3, 4, pose.grip_a, dark)
    # the body
    tp, tw = _tube_pts([(p, w * u) for p, w in zip(sk.spine, SPINE_W)])
    _tube(cv, [cv.wp(p) for p in tp], tw, colour)
    # near limbs
    leg(9, 10, pose.pitch_b, colour)
    arm(5, 6, pose.grip_b, colour)
    # head, lit while the fighter is swinging
    _, kA = k_of(4)
    _, kB = k_of(6)
    _, kL = k_of(8)
    _, kR = k_of(10)
    glow = max(kA, kB, 0.45 * max(kL, kR))
    hurt = max(0.0, min(1.0, (abs(pose.spine) - 6.0) / 12.0))
    _head(cv, cv.wp(sk.head), sk.head_r * u, pose.facing, colour, dark, u,
          glow, hurt)


def _lighten(colour, f: float):
    return tuple(int(c + (255 - c) * f) for c in colour[:3])


def trails(cv: Canvas, track, t: float, dt: float = 0.075) -> None:
    """Smear frames: the fan the *forearm or shin* swept, in a light tint.

    The fan is hung off the elbow or the knee, never off the shoulder or the hip:
    a wedge all the way from the hip to the foot covers half the frame and reads
    as a pane of glass lying on the floor. From the knee down it reads as speed.
    """
    if t < dt + 0.02:
        return
    now = track.skel(t)
    then = track.skel(t - dt)
    u = cv.unit() * now.scale
    tint = _lighten(track.colour, 0.40)
    # a smear painted at 1.5x zoom covers 2.25x the area and reads as a pane of
    # glass: keep its opacity in step with how tight the shot is
    thin = min(1.0, 1.0 / max(1.0, cv.cam.zoom) ** 1.3)
    for sid, mid in ((4, None), (6, 5), (8, 7), (10, 9)):
        pivot = now.pts[mid] if mid is not None else now.starts[sid]
        b = now.pts[sid]
        a = then.pts[sid]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        k = min(1.0, max(0.0, (d - 8.0) / 22.0))
        if k < 0.30:
            continue
        # nothing to smear when the limb is standing on the floor
        if b[1] > GROUND - 14 or pivot[1] > GROUND - 14:
            continue
        P, A, B = cv.wp(pivot), cv.wp(a), cv.wp(b)
        cv.polygon([P, A, B], tint, alpha=int(64 * k * thin))
        cv.polygon([P, B, ((B[0] + P[0]) * 0.5, (B[1] + P[1]) * 0.5)], tint,
                   alpha=int(40 * k * thin))
        if k > 0.45:
            f = 0.28 * (k - 0.45) / 0.55
            vx, vy = B[0] - A[0], B[1] - A[1]
            L = math.hypot(vx, vy) or 1.0
            tip = (B[0] + vx * f, B[1] + vy * f)
            w = 4.2 * u * (0.4 + 0.6 * k)
            nx, ny = -vy / L, vx / L
            cv.polygon([(B[0] + nx * w, B[1] + ny * w), tip,
                        (B[0] - nx * w, B[1] - ny * w)],
                       tint, alpha=int(104 * k * thin))


# --------------------------------------------------------------------- effects
def star(cx, cy, r_out, r_in, n=7, rot=0.0):
    pts = []
    for i in range(n * 2):
        a = rot + i * math.pi / n
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def draw_impacts(cv: Canvas, impacts, t: float, overlay_flash: list,
                 bursts: bool = True) -> None:
    u = cv.unit()
    seen = set()
    for e in impacts:
        age = t - e["t"]
        if age < 0:
            continue
        if e["kind"] in ("clash", "final"):
            kkey = round(e["t"], 2)
            if kkey in seen:
                continue
            seen.add(kkey)
        size = e.get("size", 1.0)
        kind = e["kind"]
        if e.get("x") is None:
            continue
        final = kind == "final"
        cx, cy = cv.wp((e["x"], e["y"]))
        life = 0.55 if final else 0.38

        if age < 0.10:
            k = age / 0.10
            overlay_flash.append(int((58 if final else 46) * (1 - k) ** 2 * size))

        if bursts and age < (0.42 if final else 0.26):
            k = age / (0.42 if final else 0.26)
            grow = 1 - (1 - k) ** 2
            # a blade clash already has sparks and two steel edges in the same
            # few pixels: a full-size burst star swallows the swords, so keep it
            # tight enough that the X of the blades still reads
            base = (11 + 19 * size) if e.get("sparks") else (14 + 25 * size)
            r = base * u * (0.55 + 0.75 * grow) * (1 - 0.3 * k)
            cv.polygon(star(cx, cy, r, r * 0.40, 7 if not final else 9,
                            0.4 + e["t"] * 2.7), (255, 255, 255),
                       alpha=int(245 * (1 - k) ** 0.6), width=max(2.0, 4.4 * u),
                       outline=INK)

        # radial particles, fixed seed per impact so the render is reproducible
        if bursts and age < (0.60 if final else 0.42):
            plife = 0.60 if final else 0.42
            k = age / plife
            rng = np.random.default_rng(int(e["t"] * 1000) % 99991)
            n = 11 if final else 8
            for i in range(n):
                ang = rng.uniform(0, math.tau)
                spd = rng.uniform(0.5, 1.3) * (1.0 + 0.4 * size)
                dist = (14 + 120 * k * spd) * u * size
                px = cx + math.cos(ang) * dist
                py = cy + math.sin(ang) * dist + 26 * u * k * k
                rr = max(1.0, (3.4 - 2.6 * k) * u * (1.0 + 0.3 * size))
                cv.disc((px, py), rr, (250, 246, 238))

        # sparks: length decays with age. Not on a blade clash -- there the
        # real steel sparks are already on screen, and these straight rays read
        # as extra swords
        if bursts and age < 0.30 and not e.get("sparks"):
            k = age / 0.30
            rng = np.random.default_rng(int(e["t"] * 977) % 65537)
            base = 0.5 + e["t"] * 1.7
            n_sp = 6 + (3 if final else 0)
            for i in range(n_sp):
                a = base + i * math.tau / n_sp
                ln = (14 + 30 * size) * u * (1 - k) ** 1.4
                r0 = (10 + 12 * size) * u
                p0 = (cx + math.cos(a) * r0, cy + math.sin(a) * r0)
                p1 = (cx + math.cos(a) * (r0 + ln), cy + math.sin(a) * (r0 + ln))
                cv.line(p0, p1, max(1.2, 2.4 * u * (1 - k)), (255, 250, 236),
                        alpha=int(200 * (1 - k)))


def dust_particles(dusts, t: float, u: float, cx: float, cy: float):
    """Yield (ellipse box, alpha) for every live dust particle."""
    for t0 in dusts:
        age = t - t0
        if not (0.0 <= age < 0.75):
            continue
        k = age / 0.75
        rng = np.random.default_rng(int(t0 * 1000) % 7919)
        for i in range(14):
            side = -1 if i % 2 else 1
            spd = rng.uniform(0.45, 1.3)
            px = cx + side * (14 + 165 * k * spd) * u
            py = cy - (2 + 24 * k * rng.uniform(0.2, 1.0)) * u
            rr = (9 + 20 * k) * u * rng.uniform(0.6, 1.2)
            alpha = int(52 * (1 - k) ** 2.1)
            yield (px - rr, py - rr * 0.42, px + rr, py + rr * 0.42), alpha


def draw_dust(dusts, t: float, u: float, cx: float, cy: float, cv) -> None:
    particles = list(dust_particles(dusts, t, u, cx, cy))
    if not particles:
        return
    x0 = min(q[0][0] for q in particles)
    y0 = min(q[0][1] for q in particles)
    x1 = max(q[0][2] for q in particles)
    y1 = max(q[0][3] for q in particles)
    ov = Overlay(cv, (x0 - 2, y0 - 2, x1 + 2, y1 + 2))
    for box, alpha in particles:
        ov.ellipse(box, fill=(212, 202, 184, alpha))
    ov.flush()


# ------------------------------------------------------------------------- HUD
_hc_cache: dict = {}


def health_curve(scene, who: str, t: float) -> float:
    """Health at t: damage applied per impact, approached over 0.32 s.

    The curve is a first-order lag integrated at 1/120 s from the start of the
    clip, so a frame-by-frame render used to re-integrate from zero twice per
    frame. The integrator keeps its state between calls instead: the numbers are
    bit-identical (same accumulation, same order), it just stops doing the work
    twice.
    """
    key = "dmg_red" if who == "red" else "dmg_blue"
    st = _hc_cache.get(who)
    if st is None or t < st["tt"] - 1e-9:
        st = _hc_cache[who] = {"tt": 0.0, "sm": 100.0, "v": 100.0, "idx": 0,
                               "key": key, "who": who,
                               "hits": sorted(scene["impacts"], key=lambda e: e["t"])}
        if t <= 0.0:
            return 100.0
    step = 1.0 / 120.0
    hits = st["hits"]
    while st["tt"] < t:
        while st["idx"] < len(hits) and hits[st["idx"]]["t"] <= st["tt"]:
            st["v"] = max(0.0, st["v"] - hits[st["idx"]].get(key, 0.0))
            st["idx"] += 1
        k = 1.0 - math.exp(-step / 0.11)
        st["sm"] += (st["v"] - st["sm"]) * k
        st["tt"] += step
    return max(0.0, st["sm"])


def draw_text(cv: Canvas, text: str, xy, size: int, fill, alpha=255, anchor="mm",
              mono=False, spacing=0):
    d = ImageDraw.Draw(cv.img)
    f = font(size, mono)
    if spacing:
        # letterspaced title
        widths = [d.textlength(ch, font=f) for ch in text]
        total = sum(widths) + spacing * (len(text) - 1)
        x = xy[0] - total / 2
        for ch, w in zip(text, widths):
            d.text((x, xy[1]), ch, font=f, fill=fill + (alpha,) if len(fill) == 3 else fill,
                   anchor="lm")
            x += w + spacing
        return
    fill = fill if len(fill) == 4 else fill + (alpha,)
    d.text(xy, text, font=f, fill=fill, anchor=anchor)


HUD = False          # no bars, no timer, no round caption: cinema, not arcade


def draw_hud(cv: Canvas, scene, t: float) -> None:
    """The arcade overlay. Off by default now — the film has no interface."""
    if not HUD:
        return draw_titles(cv, scene, t)
    d = ImageDraw.Draw(cv.img)

    # cinematic bars
    d.rectangle([0, 0, DESIGN_W, 10], fill=(8, 8, 10))
    d.rectangle([0, DESIGN_H - 10, DESIGN_W, DESIGN_H], fill=(8, 8, 10))

    # health bars
    def bar(x0, x1, y, value, colour, flip=False):
        h = 26
        d.rounded_rectangle([x0, y, x1, y + h], radius=5, fill=(18, 18, 20, 210))
        d.rounded_rectangle([x0 + 3, y + 3, x1 - 3, y + h - 3], radius=4,
                            fill=(56, 52, 50, 220))
        w = (x1 - x0 - 6) * (value / 100.0)
        if w > 1:
            if flip:
                d.rounded_rectangle([x1 - 3 - w, y + 3, x1 - 3, y + h - 3], radius=4, fill=colour)
            else:
                d.rounded_rectangle([x0 + 3, y + 3, x0 + 3 + w, y + h - 3], radius=4, fill=colour)
        d.rounded_rectangle([x0, y, x1, y + h], radius=5, outline=(12, 12, 14, 255), width=3)

    draw_text(cv, "RED", (74, 34), 24, (250, 246, 240), anchor="lm")
    draw_text(cv, "BLUE", (1206, 34), 24, (250, 246, 240), anchor="rm")
    bar(64, 520, 52, health_curve(scene, "red", t), RED + (255,))
    bar(760, 1216, 52, health_curve(scene, "blue", t), BLUE + (255,), flip=True)

    # timer
    remain = max(0.0, DURATION - 2.4 - (t - 2.4))
    ss = int(round(remain))
    draw_text(cv, f"{ss // 60:01d}:{ss % 60:02d}", (DESIGN_W // 2, 64), 46,
              (252, 250, 244), mono=True)
    draw_titles(cv, scene, t)


def draw_titles(cv: Canvas, scene, t: float) -> None:
    """The cards: title, FIGHT!, DOWN!, K.O., the winner. Never the interface."""
    for txt in scene["texts"]:
        if not (txt["t0"] <= t <= txt["t1"]):
            continue
        if txt["style"] == "hud" and not HUD:
            continue
        style = txt["style"]
        fade = min(1.0, (t - txt["t0"]) / 0.18, (txt["t1"] - t) / 0.22)
        a = int(255 * max(0.0, fade))
        if style == "title":
            pop = 1.0 + 0.06 * max(0.0, 1.0 - (t - txt["t0"]) / 0.35)
            y = 168 if txt["t1"] < 10 else 148
            draw_text(cv, txt["text"], (DESIGN_W // 2 + 3, y + 3), int(78 * pop),
                      (12, 12, 14), alpha=int(a * 0.45), spacing=6)
            draw_text(cv, txt["text"], (DESIGN_W // 2, y), int(78 * pop),
                      (250, 246, 238), alpha=a, spacing=6)
        elif style == "sub":
            y = 226 if txt["t1"] < 10 else 206
            draw_text(cv, txt["text"], (DESIGN_W // 2, y), 30,
                      (238, 232, 220), alpha=a, spacing=4)
        elif style == "fight":
            pop = 1.0 + 0.5 * max(0.0, 1.0 - (t - txt["t0"]) / 0.5)
            draw_text(cv, txt["text"], (DESIGN_W // 2, 330), int(96 * pop),
                      (252, 244, 226), alpha=a, spacing=8)
        elif style == "ko":
            pop = 1.0 + 0.35 * max(0.0, 1.0 - (t - txt["t0"]) / 0.6)
            y = 205
            draw_text(cv, txt["text"], (DESIGN_W // 2 + 5, y + 5), int(150 * pop),
                      (12, 10, 12), alpha=int(a * 0.5), spacing=10)
            draw_text(cv, txt["text"], (DESIGN_W // 2, y), int(150 * pop),
                      (234, 64, 52), alpha=a, spacing=10)
        elif style == "small":
            draw_text(cv, txt["text"], (DESIGN_W // 2, 132), 34,
                      (248, 244, 236), alpha=a)
        elif style == "hud":
            draw_text(cv, txt["text"], (DESIGN_W // 2, DESIGN_H - 36), 20,
                      (236, 230, 218), alpha=int(a * 0.85), spacing=3)


# ---------------------------------------------------------------------- weapon
def draw_weapon(cv: Canvas, track, t: float, sk) -> None:
    """The sword in the near hand, and the arc of the swing it is in the middle of.

    The blade hangs off the *solved* wrist, so it cannot drift from the arm; the
    arc is the region between where the tip was 40 ms ago and where it is now,
    which is the same trick the limb trails use, scaled up to a two-foot sword.
    """
    w = getattr(track, "weapon", None)
    if not w:
        return
    sk = sk or track.skel(t)
    # a man on the floor has dropped his sword: an airborne blade hanging off a
    # wrist nobody can see reads as a floating white line
    if sk.head[1] > 470.0:
        return
    length = w.get("len", 92.0) * (track.pose_at(t).scale or 1.0)
    sid = w.get("sid", 6)
    ang = sk.tip_angle(sid)
    # the point's own path over the last eighth of a second: a slash is a line
    # drawn in the air, and this is that line
    tips = []
    for k in (4, 3, 2, 1, 0):
        tk = max(0.0, t - 0.030 * k)
        sx = track.skel(tk)
        tips.append(steelblade.tip_of(sx.pts[sid], sx.tip_angle(sid), length))
    path = sum(math.hypot(tips[i + 1][0] - tips[i][0], tips[i + 1][1] - tips[i][1])
               for i in range(len(tips) - 1))
    power = min(1.0, max(0.0, (path - 26.0) / 150.0))
    steelblade.slash_trail(cv, tips, power)
    steelblade.draw_blade(cv, sk.pts[sid], ang, length,
                          glow=min(1.0, power * 1.4))


# ----------------------------------------------------------------------- frame
def render_frame(t: float, scene, w: int = DESIGN_W, h: int = DESIGN_H) -> Image.Image:
    """One finished frame at design size, scaled down if a smaller size is asked.

    The HUD is authored in design coordinates, so drawing natively at 640p used
    to run the bars off the frame. Everything is now composed at 1280x720 and the
    finished frame is resampled, which makes any smaller size a true preview of
    the master instead of a second layout.
    """
    ta = scene["clock"].at(t)
    # one camera for the whole frame: plate, bodies, shadow, dust
    cam_state = camera(scene, t, ta)
    cv = Canvas(DESIGN_W, DESIGN_H,
                Cam(cam_state["x"], cam_state["y"], cam_state["zoom"],
                    cam_state["shake_x"], cam_state["shake_y"],
                    sqy=cam_state.get("sqy", 1.0)))
    # The animation clock: at every contact it stops for a few frames (the
    # hitstop) and then catches up at 2x, so nothing drifts over the film. The
    # whole painted world rides it — bodies, shadow, smear, dust, landscape and
    # camera shake — so the instant of contact is one held frame. Only the
    # impact flash and the HUD stay on the real clock: the world freezes, the
    # blow rings out.
    cut = cut_at(t, scene)
    if cut is None:
        draw_background(cv, cam_state, scene)
        # craters and blood already on the floor: drawn before the bodies so a
        # fighter stands *in* the arena rather than on top of the photograph
        vfx.draw_marks(cv, scene, ta)

    if cut is not None:
        # the close-up register: a cut, not a camera move, so no HUD shadows,
        # no dust and no star burst — just the body and the light on it
        draw_insert(cv, cut, scene)
        draw_hud(cv, scene, t)
        if (w, h) != (DESIGN_W, DESIGN_H):
            return cv.img.resize((w, h), Image.LANCZOS)
        return cv.img

    # a scene is a list of fighters: the duel the film has been built around is
    # two, but the blade film ends one against three and nothing below cares
    tracks = scene.get("tracks") or [scene["red"], scene["blue"]]
    for tr in tracks:
        tr._squash = scene["squash_at"](scene["impacts"], tr.name, ta)
        tr._push = scene["push_at"](scene["impacts"], tr.name, ta, tr.facing)

    # far fighter first: the one further from the centre of action
    heads = {tr.name: body(tr, ta, tr._squash, tr._push) for tr in tracks}
    order = sorted(tracks, key=lambda tr: -abs(heads[tr.name].head[0] - 640))

    # contact shadows in one translucent pass, inside the band they occupy
    boxes = []
    lifts = {}
    for tr in order:
        sk = heads[tr.name]
        feet_y = max(sk.pts[8][1], sk.pts[10][1])
        lifts[tr.name] = max(0.0, GROUND - feet_y) / 90.0
        boxes.append(shadow_box(cv, sk, lifts[tr.name]))
    ov = Overlay(cv, (min(b[0] for b in boxes), min(b[1] for b in boxes),
                      max(b[2] for b in boxes), max(b[3] for b in boxes)))
    if ov.layer is not None:
        for tr in order:
            shadow(ov, heads[tr.name], lifts[tr.name])
        ov.flush()

    for tr in order:
        trails(cv, tr, ta)
    for tr in order:
        draw_fighter(cv, tr, ta)
    cv.flush()

    # steel: the blade is drawn after the body, and the arc it cut in the air is
    # drawn under it, so the sword passes through its own trail
    for tr in order:
        draw_weapon(cv, tr, ta, heads[tr.name])

    draw_dust(scene["dust"], ta, cv.unit(), *cv.wp((DESIGN_W * 0.5, GROUND)), cv)
    vfx.draw_puffs(cv, scene.get("puffs", ()), ta)
    vfx.shockwaves(cv, scene["impacts"], ta)
    vfx.blood_spray(cv, scene["impacts"], ta)

    # the near layer: rock and brush in front of the lens, moving against the
    # camera — the depth cue that a static plate can never give
    draw_foreground(cv, cam_state, scene["set"])

    flash = []
    draw_impacts(cv, scene["impacts"], t, flash)
    # steel on steel: hot short sparks, drawn after the burst so they read on top
    for i, e in enumerate(scene["impacts"]):
        if e.get("sparks") and e.get("x") is not None:
            steelblade.sparks(cv, *cv.wp((e["x"], e["y"])), t - e["t"],
                              e.get("size", 1.0), seed=e["t"] * 10 + i)
    cv.flush()

    if flash:
        a = min(220, sum(flash))
        cv.img.paste(Image.blend(cv.img, Image.new("RGB", (DESIGN_W, DESIGN_H),
                                                   (255, 253, 246)), a / 255.0),
                     (0, 0))

    # one or two frames of pure black and white ink on the heaviest hits: the
    # picture stops being a photograph of a fight and becomes a drawing of one
    hit = vfx.impact_frame_index(scene, t)
    if hit is not None:
        seed, sub = hit
        vfx.impact_frame(cv, tracks, ta,
                         seed + 0.01 * sub, draw_fighter)
        if (w, h) != (DESIGN_W, DESIGN_H):
            return cv.img.resize((w, h), Image.LANCZOS)
        return cv.img

    draw_hud(cv, scene, t)

    # motion blur, from the camera's own velocity: a whip pan drags the frame
    # along the path it travelled, and a punch-in drags it outward. This is a
    # real shutter (shift and average), not a horizontal squash: the parts that
    # did not move stay sharp.
    prev = camera(scene, t - FRAME, scene["clock"].at(t - FRAME))
    if prev["shot"] is cam_state["shot"]:
        dx, dy = shutter(cam_state, (prev["x"], prev["y"]), cv.unit())
        mag = (dx * dx + dy * dy) ** 0.5
        if mag > 1.5:
            # at 24 fps a full exposure would smear a whip into mush: a third of
            # the frame's travel is what reads as speed instead of as a mistake
            amt = min(1.0, 0.55 + 0.35 * cam_state["whip"])
            scale = min(1.0, 34.0 / mag)
            cv.img = directional(cv.img, dx * scale * amt, dy * scale * amt,
                                 samples=8)

    # bloom: only while something hot is on screen, because it is not free
    hot = any(0.0 <= t - e["t"] < 0.34 for e in scene["impacts"])
    if hot:
        cv.img = vfx.bloom(cv.img, 0.55)

    # fades
    fade = 0.0
    if t < 0.7:
        fade = 1.0 - t / 0.7
    elif t > DURATION - 1.1:
        fade = (t - (DURATION - 1.1)) / 1.1
    if fade > 0.001:
        cv.img.paste(Image.blend(cv.img, Image.new("RGB", (DESIGN_W, DESIGN_H),
                                                   (6, 6, 8)), min(1.0, fade) ** 1.15),
                     (0, 0))
    if (w, h) != (DESIGN_W, DESIGN_H):
        return cv.img.resize((w, h), Image.LANCZOS)
    return cv.img


# ----------------------------------------------------------------------- audio
def _env(n, attack, decay):
    a = max(1, int(attack * SR))
    e = np.ones(n, np.float32)
    e[:a] = np.linspace(0, 1, a) ** 1.6
    d = max(1, int(decay * SR))
    if d < n:
        e[d:] *= np.exp(-(np.arange(n - d) / SR) * 7.0)
    return e


def _bandpass(x, lo, hi):
    """Cheap RBJ band-pass, used to shape noise bursts into body sounds."""
    import numpy as _np
    lo = max(20.0, min(lo, SR * 0.45))
    hi = max(lo * 1.6, min(hi, SR * 0.45))
    w0 = 2 * math.pi * math.sqrt(lo * hi) / SR
    q = max(0.5, math.sqrt(lo * hi) / max(hi - lo, 1.0))
    alpha = math.sin(w0) / (2 * q)
    b0, b2 = alpha, -alpha
    a0, a1, a2 = 1 + alpha, -2 * math.cos(w0), 1 - alpha
    y = _np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(len(x)):
        v = (b0 / a0) * x[i] + (b2 / a0) * x2 - (a1 / a0) * y1 - (a2 / a0) * y2
        x2, x1 = x1, x[i]
        y2, y1 = y1, v
        y[i] = v
    return y


def _swing(t):
    """Exponential 'meat' curve: a fast attack and a long, soft tail."""
    return np.exp(-t * 16.0) * (1.0 - np.exp(-t * 900.0))


def thud(size=1.0, kind="hit", length=0.55, seed=0):
    """A punch, built from the four parts a punch actually has.

    ``body``   the thump of mass behind the blow: a sine that drops in pitch
    ``smack``  the "pak" of skin and glove: a 40 ms band-passed burst, the part
               that makes it read as a fist and not as a door slamming
    ``flesh``  a longer, lower noise tail, the meat of the impact
    ``ring``   bone-on-bone for blocks and clashes only

    Each kind retunes those four: blocks are short and bright, body shots are
    dark and round, the finisher is lower and longer than everything else.
    """
    n = int(length * SR)
    t = np.arange(n) / SR
    # every blow gets its own noise: 29 identical hits would sound looped
    rng = np.random.default_rng(int(1000 + 137 * size + 7919 * seed + len(kind)))

    # ---- per-kind voicing
    low = 112.0 - 30.0 * min(size, 1.6)
    if kind == "block":
        low, smack_lo, smack_hi, tail_lo, tail_hi, hard, smack_g, body_g = (
            150.0, 700.0, 3200.0, 300.0, 1400.0, 1.15, 0.65, 0.55)
    elif kind == "clash":
        low, smack_lo, smack_hi, tail_lo, tail_hi, hard, smack_g, body_g = (
            165.0, 900.0, 4600.0, 400.0, 2200.0, 1.3, 0.8, 0.5)
    elif kind == "body":
        low, smack_lo, smack_hi, tail_lo, tail_hi, hard, smack_g, body_g = (
            82.0, 320.0, 1500.0, 140.0, 700.0, 0.6, 0.55, 1.25)
    elif kind == "final":
        low, smack_lo, smack_hi, tail_lo, tail_hi, hard, smack_g, body_g = (
            68.0, 500.0, 3600.0, 160.0, 900.0, 1.2, 2.1, 1.15)
    else:                                     # a clean landed punch
        low, smack_lo, smack_hi, tail_lo, tail_hi, hard, smack_g, body_g = (
            96.0, 700.0, 4200.0, 220.0, 1100.0, 1.15, 1.9, 0.72)

    # ---- 1. body: a pitch-dropping thump with a little sub underneath
    sweep = low * (1.0 + 1.35 * np.exp(-t * 42.0))
    phase = 2 * np.pi * np.cumsum(sweep) / SR
    body = np.sin(phase) * np.exp(-t * (12.0 if kind != "final" else 7.0))
    body += 0.30 * np.sin(phase * 0.5) * np.exp(-t * 8.5)
    body += 0.14 * np.sin(2.0 * phase) * np.exp(-t * 24.0)

    # ---- 2. smack: the short bright burst that says "fist"
    sm = _bandpass(rng.normal(0, 1, n).astype(np.float32), smack_lo, smack_hi)
    smack_env = (1.0 - np.exp(-t * 1400.0)) * np.exp(-t * (34.0 + 10.0 * hard))
    smack = sm * smack_env

    # ---- 3. flesh: a longer, softer tail under the smack
    fl = _bandpass(rng.normal(0, 1, n).astype(np.float32), tail_lo, tail_hi)
    flesh = fl * _swing(t)

    # ---- 4. ring, bone on bone
    ring = np.zeros(n, np.float32)
    if kind in ("block", "clash"):
        for f, g in ((1180.0, 0.18), (1730.0, 0.12), (2640.0, 0.07)):
            ring += g * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * \
                np.exp(-t * (26.0 if kind == "block" else 17.0))

    sig = (body * body_g * 1.15 + smack * smack_g * 1.9 + flesh * 0.95 + ring)
    sig *= _env(n, 0.0008, length * 0.5)
    # a hair of soft clipping makes it sound recorded rather than pure
    sig = np.tanh(sig * 1.4)
    peak = float(np.max(np.abs(sig))) or 1.0
    return (sig / peak * (0.55 + 0.22 * min(size, 1.8))).astype(np.float32)


def critical_hit(length=1.25, seed=71):
    """The hit the film stops for: a sub drop, a crack, and a bone ring.

    A normal punch is a thump and a smack. This is the same blow heard close up
    and in slow motion: the body of it drops an octave, the crack is the first
    contact, and the ring is what hangs in the air while the picture holds.
    """
    n = int(length * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    sweep = 26.0 + 48.0 * np.exp(-t * 2.2)
    sub = np.sin(2 * np.pi * np.cumsum(sweep) / SR) * np.exp(-t * 2.4)
    sub += 0.35 * np.sin(2 * np.pi * np.cumsum(sweep * 0.5) / SR) * np.exp(-t * 1.6)
    crack = _bandpass(rng.normal(0, 1, n).astype(np.float32), 900.0, 5400.0)
    crack *= np.exp(-t * 42.0)
    ring = np.zeros(n, np.float32)
    for f, g in ((176.0, 0.55), (309.0, 0.32), (587.0, 0.20), (1184.0, 0.10)):
        ring += g * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.28)) * np.exp(-t * 2.6)
    sig = sub * 0.95 + crack * 0.55 + ring * 0.38
    sig *= _env(n, 0.0012, length * 0.55)
    sig = np.tanh(sig * 1.5)
    return (sig / (np.max(np.abs(sig)) or 1.0) * 0.95).astype(np.float32)


def whoosh(dur=0.22, up=True):
    n = int(dur * SR)
    rng = np.random.default_rng(11)
    noise = rng.normal(0, 1, n).astype(np.float32)
    out = np.empty(n, np.float32)
    y = 0.0
    for i in range(n):
        k = 0.02 + 0.11 * (i / n if up else 1 - i / n)
        y += k * (noise[i] - y)
        out[i] = y
    w = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    return (out * w * 0.55).astype(np.float32)


def synth_audio(scene, duration=DURATION) -> np.ndarray:
    """Three-layer mix: musical bed, movement, and hits that duck the bed.

    The bed is rendered on its own so it can be side-chained: every impact pulls
    it down about 8 dB for a moment, which is what makes a punch audible instead
    of drowning in the drums.
    """
    n = int(duration * SR)
    bed = np.zeros((n, 2), np.float32)
    fx = np.zeros((n, 2), np.float32)
    hits = np.zeros((n, 2), np.float32)

    def add(buf, sig, t, gain=1.0, pan=0.0):
        if t < 0:
            return
        i0 = int(t * SR)
        if i0 >= n:
            return
        m = min(len(sig), n - i0)
        ang = (pan + 1.0) * math.pi / 4.0        # constant-power panning
        buf[i0:i0 + m, 0] += sig[:m] * gain * math.cos(ang)
        buf[i0:i0 + m, 1] += sig[:m] * gain * math.sin(ang)

    def note(freq, dur, gain, t, pan=0.0, kind="sine"):
        nn = int(dur * SR)
        tt = np.arange(nn) / SR
        if kind == "sine":
            s = np.sin(2 * np.pi * freq * tt) + 0.35 * np.sin(4 * np.pi * freq * tt)
        else:
            s = np.sign(np.sin(2 * np.pi * freq * tt)) * 0.5
        s = s * np.exp(-tt * 3.2) * _env(nn, 0.004, dur * 0.7)
        add(bed, s.astype(np.float32), t, gain, pan)

    # ---- 1. low cinematic pulse bed
    tt = np.arange(n) / SR
    swell = np.clip((tt - 0.4) / 2.0, 0, 1) * np.clip((duration - 1.0 - tt) / 3.0, 0, 1)
    drone = (np.sin(2 * np.pi * 41.2 * tt) * 0.5 + np.sin(2 * np.pi * 61.7 * tt) * 0.3)
    for ch in (0, 1):
        bed[:, ch] += (drone * swell * 0.11).astype(np.float32)

    # ---- 2. drums from the FIGHT! cue to the K.O.
    t0, t1 = 2.15, 24.9
    beat, i = t0, 0
    while beat < t1:
        add(bed, thud(0.7, kind="body", length=0.26), beat,
            0.34 if i % 2 == 0 else 0.20)
        sn = np.random.default_rng(20 + i).normal(0, 1, int(0.11 * SR)).astype(np.float32)
        sn *= np.exp(-np.arange(len(sn)) / SR * 38)
        add(bed, sn, beat + 0.25, 0.10)
        beat += 0.5
        i += 1
    h = t0
    while h < t1:
        hs = np.random.default_rng(40 + int(h * 100)).normal(0, 1, int(0.045 * SR)).astype(np.float32)
        hs *= np.exp(-np.arange(len(hs)) / SR * 120)
        add(bed, hs, h, 0.045, pan=0.35)
        h += 0.25

    # ---- 3. movement: a swish before every strike, plus the sweeps
    for e in scene["impacts"]:
        add(fx, whoosh(0.24, up=e["x"] > DESIGN_W / 2), e["t"] - 0.10, 0.26,
            pan=(e["x"] / DESIGN_W) * 2 - 1)
    for tt_ in (6.9, 15.14, 18.98, 23.84):
        add(fx, whoosh(0.3, up=tt_ < 12), tt_ - 0.12, 0.22,
            pan=-0.25 if tt_ < 12 else 0.25)

    # ---- 4. the hits themselves
    for e in scene["impacts"]:
        pan = (e["x"] / DESIGN_W) * 2 - 1
        kind = e["kind"]
        if kind == "block":
            add(hits, thud(0.7, kind="block", length=0.26, seed=int(e["t"] * 100)),
                e["t"], 0.95, pan)
        elif kind == "hit":
            body_shot = abs(e["t"] - 5.16) < 0.05 or abs(e["t"] - 23.28) < 0.05
            add(hits, thud(1.0, kind="body" if body_shot else "hit", length=0.42,
                           seed=int(e["t"] * 100)), e["t"], 1.2, pan)
        elif kind == "clash":
            add(hits, thud(1.2, kind="clash", length=0.42, seed=int(e["t"] * 100)),
                e["t"], 1.25, pan)
        elif kind == "final":
            add(hits, thud(1.8, kind="final", length=1.05, seed=97), e["t"], 1.5, pan)
            add(hits, thud(1.3, kind="clash", length=0.5, seed=13), e["t"] + 0.012,
                0.8, pan)
    for tt_ in scene["dust"]:
        add(hits, thud(0.3, kind="body", length=0.22, seed=int(tt_ * 100)), tt_, 0.30,
            pan=-0.2)
    # the three close-ups: a blow heard from inside the skull
    for i, (start, dur, side, expr, kind) in enumerate(cuts_of(scene)):
        add(hits, critical_hit(1.25 if kind == "xray" else 0.9, seed=71 + i), start,
            1.05 if kind == "xray" else 0.85, pan=(-0.4 if side == "red" else 0.4))

    # ---- 5. side-chain: the bed ducks under every hit
    duck = np.ones(n, np.float32)
    for e in scene["impacts"]:
        depth = 0.42 if e["kind"] in ("hit", "clash", "final") else 0.30
        i0 = int(max(0, e["t"] - 0.02) * SR)
        i1 = min(n, int((e["t"] + 0.20) * SR))
        if i0 >= i1:
            continue
        seg = np.arange(i1 - i0) / SR
        env = np.minimum(1.0, seg / 0.012) * np.exp(-np.maximum(0.0, seg - 0.02) * 11.0)
        duck[i0:i1] = np.minimum(duck[i0:i1], 1.0 - depth * env)
    # and the bed drops out entirely under a close-up: the picture has stopped,
    # so the music must too, or the slow motion does not read as slow
    for start, dur, side, expr, kind in cuts_of(scene):
        i0 = int(max(0, start - 0.02) * SR)
        i1 = min(n, int((start + dur * 0.9) * SR))
        if i0 >= i1:
            continue
        seg = np.arange(i1 - i0) / SR
        env = np.minimum(1.0, seg / 0.010) * np.exp(-np.maximum(0.0, seg - 0.05) * 5.0)
        duck[i0:i1] = np.minimum(duck[i0:i1], 1.0 - 0.70 * env)
    for ch in (0, 1):
        bed[:, ch] *= duck

    # ---- 6. rise to victory: C - E - G - C, major
    for i, (f, dt_) in enumerate(zip((261.63, 329.63, 392.00, 523.25),
                                     (0.0, 0.16, 0.32, 0.60))):
        note(f, 1.6, 0.30 if i < 3 else 0.36, 25.35 + dt_, pan=0.15 * (i - 1.5))
        note(f * 2, 1.0, 0.06, 25.35 + dt_, pan=-0.1, kind="sq")

    mix = bed + fx + hits
    fin, fout = int(0.5 * SR), int(1.3 * SR)
    mix[:fin] *= np.linspace(0, 1, fin)[:, None]
    mix[-fout:] *= np.linspace(1, 0, fout)[:, None]
    mix = np.tanh(mix * 1.9)
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix / peak * 0.94
    return np.clip(mix, -1.0, 1.0).astype(np.float32)


def write_wav(path, stereo):
    data = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(data.tobytes())


# ---------------------------------------------------------------------- render
def _x264(w: int, h: int, preset: str, crf: int, tune: str, threads: int, out: str):
    """The encoder every chunk drives with its own raw-RGB pipe."""
    import imageio_ffmpeg
    args = ["-c:v", "libx264", "-preset", preset, "-crf", str(crf)]
    if tune:
        args += ["-tune", tune]
    if threads:
        args += ["-threads", str(threads)]
    return subprocess.Popen(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{w}x{h}", "-framerate", str(FPS), "-i", "-", *args,
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", out, "-loglevel", "error"],
        stdin=subprocess.PIPE)


def _render_chunk(job):
    """Draw a contiguous run of frames and encode it in the same process.

    Frames never cross a pipe: the worker owns one segment and one encoder, so
    the parent does no per-frame copying and every core is busy with either
    pixels or x264 the whole time.
    """
    (n0, n1, w, h, preset, crf, tune, threads, set_name), path = job
    sc = scene(set_name)
    proc = _x264(w, h, preset, crf, tune, threads, path)
    for i in range(n0, n1):
        proc.stdin.write(render_frame(i / FPS, sc, w, h).tobytes())
    proc.stdin.close()
    proc.wait()
    return path


def _write_audio(wav_path: str, seconds: float, set_name: str) -> None:
    write_wav(wav_path, synth_audio(scene(set_name), seconds))


def render(out_path: str, w: int = DESIGN_W, h: int = DESIGN_H, workers: int = 2,
           audio: bool = True, start: float = 0.0, end: float = DURATION,
           preset: str = "veryfast", crf: int = 16,
           tune: str = "animation", set_name: str = "mountain") -> None:
    from multiprocessing import Pool, Process
    import imageio_ffmpeg

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    n0, n1 = int(round(start * FPS)), int(round(end * FPS))
    total = n1 - n0
    print(f"[render] {total} frames at {w}x{h} on the {set_name} set", flush=True)

    tmp = os.path.join(os.path.dirname(out_path) or ".", "tmp")
    os.makedirs(tmp, exist_ok=True)
    silent = os.path.join(tmp, "_silent.mp4")
    wav = os.path.join(tmp, "_audio.wav")

    # the soundtrack is pure numpy and takes ~2 s: run it in its own process
    # while the others draw frames, instead of after them
    ap = None
    if audio:
        ap = Process(target=_write_audio, args=(wav, total / FPS, set_name),
                     daemon=True)
        ap.start()

    # one segment per worker: render + encode together, then join the segments
    threads = 1 if workers > 1 else 0
    bounds = [n0 + round(total * k / workers) for k in range(workers + 1)]
    jobs = [((bounds[k], bounds[k + 1], w, h, preset, crf, tune, threads, set_name),
             os.path.join(tmp, f"_seg{k}.mp4")) for k in range(workers)]
    t0 = time.time()
    with Pool(workers) as pool:
        segs = [r.get() for r in [pool.apply_async(_render_chunk, (j,)) for j in jobs]]
        for k, p in enumerate(segs):
            print(f"  segment {k + 1}/{workers} done in {time.time() - t0:.1f}s", flush=True)

    if len(segs) > 1:
        listing = os.path.join(tmp, "_segs.txt")
        with open(listing, "w") as fh:
            for p in segs:
                fh.write(f"file '{os.path.abspath(p)}'\n")
        subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", listing,
                        "-c", "copy", "-movflags", "+faststart", silent,
                        "-loglevel", "error"], check=True)
    else:
        os.replace(segs[0], silent)

    if audio:
        ap.join()
        subprocess.run([ff, "-y", "-i", silent, "-i", wav, "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                        "-shortest", out_path, "-loglevel", "error"], check=True)
        os.remove(wav)
    else:
        os.replace(silent, out_path)
    for p in segs:
        if os.path.exists(p):
            os.remove(p)
    if os.path.exists(silent):
        os.remove(silent)
    print(f"[done] {out_path}", flush=True)


def storyboard(times, out_path: str, w: int = DESIGN_W, h: int = DESIGN_H,
               cols: int = 4, set_name: str = "mountain") -> None:
    sc = scene(set_name)
    frames = [render_frame(t, sc, w, h) for t in times]
    tw, th = w // 3, h // 3
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (tw * cols, th * rows), (16, 16, 18))
    d = ImageDraw.Draw(sheet)
    f = font(14)
    for i, (t, im) in enumerate(zip(times, frames)):
        x, y = (i % cols) * tw, (i // cols) * th
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
        # bottom-left: the top corners belong to the health bars and the timer
        d.text((x + 6, y + th - 18), f"{t:.2f}s", font=f, fill=(255, 240, 200))
    sheet.save(out_path, quality=92)
    print(f"[storyboard] {out_path} ({len(times)} moments)", flush=True)
