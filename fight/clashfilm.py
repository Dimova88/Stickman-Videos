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


#: The plate is painted 25 % larger than the frame. At zoom 1.0 the crop was
#: exactly the size of the plate, so the camera had *no* room to pan before the
#: clamp stopped it dead; the overscan buys that room back and hides the plate
#: edge under a whip pan or a Dutch tilt for ever.
BG_OVERSCAN = 1.25


def background(cx: float, cy: float, zoom: float, w: int, h: int, path: str):
    """The plate as the camera sees it: a crop around (cx, cy) at ``zoom``.

    Design space maps onto the plate 1:1 at zoom 1, so a crop is a straight
    scale of the design coordinates — divided by ``BG_OVERSCAN`` so the plate
    is a little larger than the frame and the pan never runs out of picture.
    """
    src = _plate(path)
    k = (src.width / DESIGN_W) / max(zoom, 1.0) / BG_OVERSCAN
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
    d = float(cam.get("dof", 0.0))
    if d > 0.004:
        # bokeh the cheap way: blur a sixth-size copy and blow it back up. A
        # Gaussian on the full frame costs 24 ms; this costs 2 and reads softer.
        # The blurred plate is then *mixed* back by depth rather than swapped in
        # at a threshold: a shot that opens up pulls focus smoothly instead of
        # snapping from sharp to butter between two frames.
        small = bg.resize((w // 6, h // 6), Image.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(0.5 + 3.2 * d)).resize(
            (w, h), Image.BICUBIC)
        bg = Image.blend(bg, small, min(1.0, d * 5.0))
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
    """Reserved: this film has no face inserts (see AGENT_INSTRUCTIONS.md).

    A drawn human close-up built out of primitives is the one thing that always
    reads as programmer art; the dramatic accent is the two-frame ink hit
    instead, which is just the real bodies, inverted.
    """
    return ()


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
    if _casing(cv):
        colour = OUTLINE
        cw = _case_w(cv)
        widths = [w + cw for w in widths]
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


#: the dark casing that keeps two bodies legible where they overlap. Three
#: pixels at 720p: enough to separate a red forearm from a blue one in a collar
#: grab, not enough to read as a cartoon sticker outline.
OUTLINE = (14, 12, 18)


def _casing(cv) -> bool:
    return bool(getattr(cv, "_casing", False))


def _case_w(cv) -> float:
    return 3.0 * (cv.w / 1280.0)


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
    if _casing(cv):
        colour = OUTLINE
        cw = _case_w(cv)
        widths = [w + cw for w in widths]
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
    """A clean head: a skull with a jaw, and nothing drawn on it.

    A face painted with primitives — a nose wedge, an almond eye, a brow, a
    mouth line — is the one thing that reads as programmer art at forty pixels
    across. So the head is a silhouette, and the only feature it ever gets is a
    pair of glowing slits, which appear when the fighter is in a high-energy
    state (a swing, a parry, a killing blow) and are gone the rest of the time.
    """
    fx = facing
    if _casing(cv):
        colour = OUTLINE
        r += _case_w(cv) * 0.5
    cv.circle(c, r, colour, width=0, fill=colour)
    # the jaw: still a silhouette, but it gives the ball a direction
    cv.circle((c[0] + fx * r * 0.17, c[1] + r * 0.34), r * 0.60, colour,
              width=0, fill=colour)

    if getattr(cv, "mono", False):
        # the ink frame is a high-energy state, so it gets the slit
        cv.line((c[0] - fx * r * 0.55, c[1] - r * 0.16),
                (c[0] + fx * r * 0.55, c[1] - r * 0.28),
                max(2.0, 0.22 * r), getattr(cv, "mono_ink", None) or INK,
                alpha=255, caps=True)
        return

    if glow <= 0.12:
        return
    # two angular slits, near and far, angled with the facing direction
    k = min(1.0, (glow - 0.12) / 0.7)
    for side, scale in ((-1.0, 0.78), (1.0, 1.0)):
        ex = c[0] + fx * r * (0.30 + 0.13 * side) - fx * r * 0.06
        ey = c[1] - r * (0.05 + 0.05 * side)
        w = r * 0.30 * scale * (0.72 + 0.28 * k)
        h = r * 0.050 * scale * (1.0 - 0.30 * k)          # narrows as it burns
        slant = fx * r * 0.17
        pts = [(ex - w * 0.5, ey + h * 0.5 + slant * 0.4),
               (ex - w * 0.15, ey - h * 0.5 - slant * 0.2),
               (ex + w * 0.5, ey - h * 0.5 - slant),
               (ex + w * 0.2, ey + h * 0.5)]
        if k > 0.30:
            cv.circle((ex, ey), w * 1.15, (255, 206, 138), width=0,
                      fill=(255, 206, 138), alpha=int(18 + 52 * k))
        cv.polygon(pts, (255, 246, 214), alpha=int(190 + 65 * k))
        cv.polygon([(p[0], p[1]) for p in pts[1:]] + [pts[0]],
                   (255, 226, 158), alpha=int(70 * k))


def _speed(now, then, sid: int, dt: float = 0.05):
    """Where a limb tip is heading and how fast, in design units per second."""
    a = then.pts[sid]
    b = now.pts[sid]
    return (b[0] - a[0], b[1] - a[1]), math.hypot(b[0] - a[0], b[1] - a[1]) / dt


#: whip lag costs three extra pose solves per joint chain, so the finished pose
#: is memoised per frame: the renderer, the camera, the props and the audits all
#: ask for the same body at the same instant, and it must be the same body.
_WHIP_MEMO: dict = {}
_WHIP_MEMO_MAX = 4096


def _raw_pose(track, t: float, squash: float = 0.0, push: float = 0.0):
    """The authored pose at ``t``: no inertia, no lag. The input to the whip."""
    from . import footwork
    from .impact import compress
    p, x = track.sample(t)
    p = footwork.apply(track, t, p)
    if squash > 0.002:
        p = compress(p, squash)
    return to_pose(p, x + push, track.ground_y(), facing=track.facing_at(t),
                   scale=FIG_SCALE * (1.0 + 0.08 * track.ground_z()),
                   widen=STANCE)


def pose_of(track, t: float, squash: float = 0.0, push: float = 0.0):
    """The drawable pose: choreography, footwork, the blow, then the IK solve.

    Footwork is applied *before* ``to_pose`` because it only edits the pose dict
    — the foot offsets and lifts the step cycle computes — so the leg IK still
    does the solve it was tuned against.

    On top of that comes the **whip lag** (``engine/biomechanics.py``): every
    joint but the pelvis is drawn one to three frames behind, by an amount that
    scales with how fast the body is actually travelling. A fighter standing
    still is drawn exactly as authored; a fighter lunging is drawn as a chain
    with mass, and the last link — the fist, the blade — arrives late and
    slightly long. Three extra solves a frame, memoised, which is cheaper than
    arguing with a rig that moves as one piece.
    """
    now = _raw_pose(track, t, squash, push)
    if not WHIP_ON:
        return now
    key = (id(track), getattr(track, "_rev", 0), round(t, 3))
    hit = _WHIP_MEMO.get(key)
    if hit is not None:
        return hit
    import engine.biomechanics as _bio
    dt = 1.0 / 24.0
    prev = _raw_pose(track, max(0.0, t - dt), squash, push)
    # what counts as "moving" is the *fastest joint*, not the pelvis: a punch
    # thrown from a planted stance has a pelvis that has not travelled a pixel
    # and a fist that crosses forty, and gating on the pelvis switched the whip
    # off on exactly the frames it exists for
    from .core import solve as _solve
    sk_now, sk_prev = _solve(now), _solve(prev)
    speed = max(math.hypot(sk_now.pts[sid][0] - sk_prev.pts[sid][0],
                           sk_now.pts[sid][1] - sk_prev.pts[sid][1])
                for sid in (4, 6, 2))
    k = _bio.blend_strength(speed)
    k *= _bio.contact_taper(t, getattr(track, "_hit_times", None))
    if k <= 0.0:
        out = now
    else:
        older = {}
        for lag in (1, 2, 3):
            older[lag] = _raw_pose(track, max(0.0, t - lag * dt), squash, push).angles
        out = now.copy(angles=tuple(_bio.whip_angles(now.angles, older, k)))
    if len(_WHIP_MEMO) > _WHIP_MEMO_MAX:
        _WHIP_MEMO.clear()
    _WHIP_MEMO[key] = out
    return out


#: the whip lag is on by default; ``--no-whip`` on the harness turns it off for
#: an A/B of a single frame
WHIP_ON = True


def body(track, t: float, squash: float = 0.0, push: float = 0.0):
    """The skeleton of one fighter at animation time ``t``.

    ``squash`` folds the pose around the blow that just landed (see
    ``impact.compress``) and ``push`` shoves it back off its feet; both come
    from the same envelope, so the shadow and the smear follow the body.
    """
    return solve(pose_of(track, t, squash, push))


def draw_fighter(cv: Canvas, track, t: float, _casing_pass: bool = False) -> None:
    """The body: bowed spine, tapered limbs, feet on the floor, hands, face.

    The skeleton still comes from the same IK solve the choreography was written
    against — the anatomy only changes how that skeleton is painted, plus the
    speed-driven deformation (stretch along the swing, joints trailing behind).
    """
    if not _casing_pass and OUTLINE_ON:
        # the casing: the whole silhouette once, fat and dark, *under* the
        # colour. Without it a red forearm crossing a blue one in a collar grab
        # is one magenta arm, which is exactly the "scrum" the film was showing.
        prev = getattr(cv, "_casing", False)
        cv._casing = True
        draw_fighter(cv, track, t, _casing_pass=True)
        cv._casing = prev
    squash = getattr(track, "_squash", 0.0)
    push = getattr(track, "_push", 0.0)
    pose = pose_of(track, t, squash, push)
    sk = solve(pose)
    u = cv.unit() * pose.scale

    # depth dimming: a rival waiting his turn is a body in shadow, so the duel
    # reads first. It is a mix towards the casing colour, not an opacity: a
    # half-transparent stickman over a painted mountain is mud.
    dim = 1.0 if _casing_pass else getattr(track, "_dim", 1.0)
    colour, dark = _shade(track.colour, dim), _shade(track.dark, dim)
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
            # Put the sole on the floor line *without changing the length of the
            # shin*: slide the ankle down its own bone towards the floor instead
            # of teleporting it to a fixed height. The old version moved the
            # ankle to `sole - drop` wherever that was, so a crouching fighter's
            # shin was drawn longer than the shin is — the "rubber leg".
            knee = pts[-2]
            shin = math.hypot(ank[0] - knee[0], ank[1] - knee[1]) or 1.0
            want = (ank[0] + pose.facing * 1.6, sole - drop)
            vy, vx = want[1] - knee[1], want[0] - knee[0]
            d = math.hypot(vx, vy) or 1.0
            ank = (knee[0] + vx / d * shin, knee[1] + vy / d * shin)
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


#: below this separation the engaged pair share the fighting plane, so their
#: blades meet in the same depth; above it the depth lanes come back and the
#: two silhouettes are separated by size and dimming instead
CLASH_PLANE = 120.0


def _lane_with(scene, track, t: float, engaged) -> float:
    """The lane a fighter is drawn in.

    The engaged pair share a *plane*, not a coordinate: they keep the hero's own
    lane and close the offset between them, so the duel is still drawn with one
    body nearer the lens — and their blades still meet in the same depth. A rival
    waiting his turn keeps his own lane.
    """
    hero = scene.get("hero") or scene["tracks"][0]
    base = float(getattr(hero, "z", 0.0))
    if engaged is not None and track.name in ("red", engaged):
        if _track_resolution(scene, t) <= CLASH_PLANE:
            return base
        other = 1.0 if track is hero else -1.0
        return base + other * 0.16
    return getattr(track, "z", 0.0)


def _track_resolution(scene, t: float) -> float:
    from .rig import active_opponent as _rig_active
    """How deep the two bodies are stacked over the last tenth of a second.

    A grapple is meant to be *close*, but two bodies at the same depth for
    twenty frames is one body with eight limbs. The lanes are only collapsed
    while the pair is actually crossing, so the depth that separates them comes
    back the moment the exchange widens.
    """
    hero = scene.get("hero") or scene["tracks"][0]
    best = 99.0
    for k in range(7):
        tt = t - 0.10 + k * (0.10 / 6.0)
        engaged = _rig_active(scene, tt)
        if engaged is None:
            continue
        other = next((tr for tr in scene["tracks"] if tr.name == engaged), None)
        if other is None:
            continue
        best = min(best, abs(other.sample(tt)[1] - hero.sample(tt)[1]))
    return best


#: draw order: the painter's algorithm, back to front
OUTLINE_ON = True
#: how much of its colour a rival *waiting* in the back loses, so the duel owns
#: the eye. 1.0 would be a full-lit fighter; 0.66 is a body in shadow.
WAITING_DIM = 0.78


def _shade(colour, k: float, towards=OUTLINE) -> tuple:
    """Mix a colour towards the dark: depth dimming without a lighting model."""
    if k >= 0.999:
        return colour
    return tuple(int(c * k + t * (1.0 - k)) for c, t in zip(colour[:3], towards))


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
    tint = _lighten(_shade(track.colour, getattr(track, "_dim", 1.0)), 0.40)
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
def burst_spikes(cv: Canvas, cx: float, cy: float, u: float, size: float,
                 k: float, seed: float, n: int = 24) -> None:
    """Needles flying out of the contact point: 24 irregular tapered spikes.

    Not a star polygon: a star has a fixed, symmetric outline and reads as a
    sticker. These are needles of different lengths, each one tapering to a
    point, so the shape reads as *debris thrown off a hit* and never repeats.
    """
    rng = np.random.default_rng(int(seed * 977) % 65521)
    inner = (4.0 + 5.0 * size) * u
    reach = (18.0 + 52.0 * size) * u
    for i in range(n):
        a = (i / n) * math.tau + rng.uniform(-0.10, 0.10)
        ln = reach * rng.uniform(0.45, 1.0) * (0.45 + 0.55 * (1.0 - k) ** 0.8)
        w = (0.45 + 1.15 * size) * u * rng.uniform(0.45, 1.15)
        ca, sa = math.cos(a), math.sin(a)
        nx, ny = -sa, ca
        r0 = inner * rng.uniform(0.7, 1.3)
        p0 = (cx + ca * r0 + nx * w, cy + sa * r0 + ny * w)
        p1 = (cx + ca * (r0 + ln), cy + sa * (r0 + ln))
        p2 = (cx + ca * r0 - nx * w, cy + sa * r0 - ny * w)
        warm = rng.uniform(0.0, 1.0) ** 2
        col = (255, int(255 - 26 * warm), int(250 - 120 * warm))
        cv.polygon([p0, p1, p2], col, alpha=int(250 * (1.0 - k) ** 0.7))


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
            # steel on steel throws a hot point, not a white page: the flash
            # there is a third as strong, so the two blades cross *in* the light
            gain = 0.34 if e.get("sparks") else 1.0
            overlay_flash.append(int((58 if final else 46) * gain * (1 - k) ** 2 * size))

        if bursts and age < (0.42 if final else 0.26):
            k = age / (0.42 if final else 0.26)
            grow = 1 - (1 - k) ** 2
            # a hot bloom at the contact point, as concentric soft discs — no
            # outline anywhere, so it never reads as a drawn shape
            halo = (26.0 + 44.0 * size) * u * (0.45 + 0.55 * grow) * (1.0 - 0.4 * k)
            box = (cx - halo * 1.6, cy - halo * 1.6, cx + halo * 1.6, cy + halo * 1.6)
            ov = Overlay(cv, box)
            for f, a in ((1.55, 30), (1.05, 46), (0.58, 96)):
                rr = max(1.0, halo * f)
                ov.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), (255, 243, 212, a))
            ov.flush()
            burst_spikes(cv, cx, cy, u, size, k, e["t"] + 0.3,
                         n=15 if e.get("sparks") else 20)
            core = (2.6 + 6.0 * size) * u * (1.0 - 0.5 * k) * (0.7 + 0.3 * grow)
            cv.disc((cx, cy), max(1.0, core), (255, 254, 248))

        # debris streaks: fast, thin, and they fall — the thing that separates a
        # hit from a decoration
        if bursts and age < (0.60 if final else 0.42):
            plife = 0.60 if final else 0.42
            k = age / plife
            rng = np.random.default_rng(int(e["t"] * 1000) % 99991)
            n = 12 if final else 9
            for i in range(n):
                ang = rng.uniform(0, math.tau)
                spd = rng.uniform(0.5, 1.3) * (1.0 + 0.4 * size)
                dist = (12 + 130 * k * spd) * u * size
                px = cx + math.cos(ang) * dist
                py = cy + math.sin(ang) * dist + 30 * u * k * k
                tail = (10.0 + 26.0 * spd) * u * (1.0 - k) ** 1.3
                tx, ty = math.cos(ang), math.sin(ang)
                # tapered, and no caps: a round cap on a flying streak is a
                # white bead at the tip, which reads as a dot-burst sticker
                vfx._brush(cv, (px - tx * tail * 0.5, py - ty * tail * 0.5),
                       (px + tx * tail * 0.5, py + ty * tail * 0.5),
                       max(1.4, (2.6 - 1.8 * k) * u), 0.35,
                       (252, 240, 214), alpha=int(230 * (1 - k) ** 1.1))

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
                        alpha=int(200 * (1 - k)), caps=False)


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
    # a man on the floor has dropped his sword: a blade still welded to a wrist
    # that is now lying on the ground reads as a white line floating over the
    # corpse. Past the height where the head has gone below the shoulders the
    # weapon is gone.
    if sk.head[1] > 470.0:
        return
    # a conjured weapon is *held by the power*, not by the hand: when the power
    # lets go the shaft of light goes with it, and the man is left with a fist
    if w.get("t_end") is not None and t > float(w["t_end"]):
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
    # the smear: four frames of the blade's *angle*, reconstructed around the
    # hilt of this frame (see steelblade.local_crescent). It is a crescent at
    # any speed, which is what lets it survive a dash.
    angs = []
    speed = 0.0
    for k in (3, 2, 1, 0):
        tk = max(0.0, t - 0.024 * k)
        sx = track.skel(tk)
        angs.append(sx.tip_angle(sid))
        if k == 1:
            speed = math.hypot(sx.pts[sid][0] - sk.pts[sid][0],
                               sx.pts[sid][1] - sk.pts[sid][1]) / 0.024
    steelblade.local_crescent(cv, sk.pts[sid], angs, length, power)
    steelblade.thrust_cone(cv, sk.pts[sid], angs[-1], length, speed, power)
    if w.get("kind") == "energy_spear":
        # a weapon that was *made*: no steel, a shaft of light with a hot tip
        import engine.superpowers as _sp
        _sp.energy_lance(cv, sk.pts[sid], ang, length,
                         glow=1.0, colour=(150, 240, 255))
        return
    steelblade.draw_blade(cv, sk.pts[sid], ang, length,
                          glow=min(1.0, power * 1.4))



# -------------------------------------------------------------------- powers
def _power_on(p: dict, t: float) -> bool:
    """Is this power event on screen at ``t``?

    Named ``_power_on`` and not ``_active`` because ``render_frame`` imports
    ``rig.active_opponent`` as ``_active``: two different questions with one name
    is how the whole power layer silently drew nothing for an afternoon.
    """
    kind = p["kind"]
    if kind == "awakening":
        return t >= p["t"]
    if kind == "flash_step":
        return p["t"] <= t <= p["t"] + 0.36
    if kind == "beam":
        return p["t0"] <= t <= p["t1"]
    return False


def _power_amount(p: dict, t: float) -> float:
    """How *much* of it: powers ramp in, hold, and cut out."""
    kind = p["kind"]
    if kind == "awakening":
        ramp = max(1e-3, float(p.get("ramp", 2.0)))
        u = min(1.0, max(0.0, (t - p["t"]) / ramp))
        return (u * u * (3 - 2 * u)) * (0.86 + 0.14 * math.sin(t * 11.0))
    if kind == "beam":
        span = max(1e-3, p["t1"] - p["t0"])
        u = (t - p["t0"]) / span
        return float(p.get("power", 1.0)) * min(1.0, math.sin(max(0.0, min(1.0, u)) * math.pi) * 1.6)
    if kind == "flash_step":
        age = (t - p["t"]) / 0.36
        return max(0.0, 1.0 - age)
    return 0.0


def _afterimage(cv: Canvas, track, t: float, colour, alpha: float) -> None:
    """One residual silhouette: the man's own skeleton, drawn as light.

    Not a motion blur and not a copy of the sprite: five distinct past poses,
    each fainter than the last, is what tells the eye the body *went* somewhere
    in the frames it was not supposed to be drawn in.
    """
    if alpha <= 0.02:
        return
    u = cv.unit()
    sk = body(track, t)
    a = int(90 * min(1.0, alpha))
    # one polyline per chain, no caps: a joint that is drawn as a disc turns a
    # ghost into a string of beads
    for chain in ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10)):
        pts = [cv.wp(sk.starts[chain[0]])]
        pts += [cv.wp(sk.pts[sid]) for sid in chain]
        cv.polyline(pts, max(3.0, 10.0 * u), colour, alpha=a)
    cv.circle(cv.wp(sk.head), max(4.0, sk.head_r * u), colour,
              width=max(2.0, 2.5 * u), alpha=a)


def _draw_beam(cv: Canvas, scene, p: dict, t: float, cam: dict) -> None:
    """The beam leaves the hand that threw it and lands on the man in front."""
    import engine.superpowers as _sp
    amt = _power_amount(p, t)
    if amt <= 0.03:
        return
    who = scene.get(p["who"])
    on = scene.get(p.get("on", ""))
    if who is None:
        return
    sk = body(who, t)
    # the *forward* palm: the beam comes out of the hand that is leading
    hands = [sk.pts[4], sk.pts[6]]
    hx = sum(h[0] for h in hands) * 0.5
    hy = sum(h[1] for h in hands) * 0.5
    if on is not None:
        tgt_sk = body(on, t)
        tx, ty = tgt_sk.head[0], tgt_sk.head[1] + 40.0
    else:
        tx, ty = hx + 400.0, hy
    _sp.draw_beam(cv, (hx, hy), (tx, ty), int(round(t * 24)), power=min(1.0, amt),
                  radius=26.0)
    # the pressure wave on the floor under the beam
    u = cv.unit()
    for i in range(3):
        rr = (14.0 + 18.0 * i) * amt
        gy = who.ground_y() - 2.0
        cv.line(cv.wp((hx - rr, gy)), cv.wp((hx + rr, gy)), max(1.0, 2.0 * u),
                (226, 246, 255), alpha=int(70 * amt / (1 + i)))


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
    draw_background(cv, cam_state, scene)
    # craters and blood already on the floor: drawn before the bodies so a
    # fighter stands *in* the arena rather than on top of the photograph
    vfx.draw_marks(cv, scene, ta)

    # a scene is a list of fighters: the duel the film has been built around is
    # two, but the blade film ends one against three and nothing below cares
    tracks = scene.get("tracks") or [scene["red"], scene["blue"]]
    for tr in tracks:
        tr._squash = scene["squash_at"](scene["impacts"], tr.name, ta)
        # recoil is measured along the way the body is *drawn*, not the way it
        # was built: after a turn the two are opposite, and the flinch would
        # shove a fighter towards the man who just hit him
        tr._push = scene["push_at"](scene["impacts"], tr.name, ta,
                                    1 if tr.facing_at(ta) >= 0 else -1)

    # ---- the painter's algorithm -------------------------------------------
    # Back to front by lane, and the engaged pair share the fighting plane so
    # their blades meet in the same depth. A body waiting in the back lane is
    # also dimmed, which is the other half of separating four silhouettes.
    # ---- what is in each hand *now* ---------------------------------------
    # an object is not welded to a wrist: the prop field says who is holding
    # what, and a man whose blade is spinning into the dirt is drawn empty-
    # handed, because that is the pose he is actually in
    field = scene.get("props")
    if field is not None:
        for tr in tracks:
            held = field.held_by(ta, tr.name)
            if held is None:
                tr.weapon = None
            else:
                tr.weapon = {"len": held["length"], "sid": 6,
                             "kind": held["kind"], "t_end": held.get("t_end")}
    # the whip lag needs to know when this body is *in* a blow, so the inertia is
    # switched off on the frame the chain arrives
    for tr in tracks:
        tr._hit_times = tuple(e["t"] for e in scene["impacts"]
                              if e.get("by") == tr.name or e.get("on") == tr.name)
    from .rig import is_engaged, active_opponent as _rig_active
    from .rig import active_opponent as _active
    _engaged = _active(scene, ta)
    for tr in tracks:
        tr.z_now = _lane_with(scene, tr, ta, _engaged)
        tr._dim = 1.0 if is_engaged(scene, tr, ta) else WAITING_DIM
    heads = {tr.name: body(tr, ta, tr._squash, tr._push) for tr in tracks}
    order = sorted(tracks, key=lambda tr: (tr.z_now,
                                           -abs(heads[tr.name].head[0] - 640)))

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

    import engine.superpowers as _sp
    import engine.weapons_and_props as _props
    import engine.destruction_physics as _dest
    powers = scene.get("powers") or ()

    def _power_at(kind, when=ta):
        return [p for p in powers if p["kind"] == kind and _power_on(p, when)]

    # the awakened aura and the stones it is lifting: drawn *under* the bodies,
    # so the figure inside the energy stays a readable silhouette
    for p in _power_at("awakening"):
        tr = scene.get(p["who"])
        if tr is None:
            continue
        amt = _power_amount(p, ta)
        if amt <= 0.02:
            continue
        pelvis = pose_of(tr, ta)
        _sp.aura_ring(cv, (pelvis.x, pelvis.y - 26.0), 118.0, ta, power=amt)
        rocks = _sp.levitating_rocks(pelvis.x, tr.ground_y(), int(round(ta * 24)),
                                     count=8, power=amt, seed=7)
        _sp.draw_levitating_rocks(cv, rocks)
    # the residual images of a flash-step: five past poses of the same man
    for p in _power_at("flash_step"):
        tr = scene.get(p["who"])
        if tr is None:
            continue
        age = ta - p["t"]
        fade_amt = max(0.0, 1.0 - age / 0.34)
        if fade_amt <= 0.02:
            continue
        for i, (tt, alpha, _pose) in enumerate(
                _sp.afterimages(tr, p["t"] - 0.001, pose_of,
                                count=p.get("count", 5),
                                spacing=p.get("spacing", 0.02))):
            _afterimage(cv, tr, tt, (120, 236, 255), alpha * fade_amt)

    for tr in order:
        trails(cv, tr, ta)
    for tr in order:
        draw_fighter(cv, tr, ta)
    cv.flush()

    # the leftover machinery of the fight: a blade in the dirt, the pieces of a
    # broken one, and the floor it all came out of
    if field is not None:
        _props.draw_loose(cv, field, ta)
    if scene.get("debris") is not None:
        _dest.draw_debris(cv, scene["debris"], ta)

    # lightning arcs from the awakened body, and the beam itself
    for p in _power_at("awakening"):
        tr = scene.get(p["who"])
        amt = _power_amount(p, ta) if tr is not None else 0.0
        if amt <= 0.25:
            continue
        sk = body(tr, ta)
        for k, sid in enumerate((3, 5)):
            if ((int(ta * 24) + k * 7) % 9) > 3:
                continue
            _sp.draw_lightning(cv, sk.pts[sid], sk.pts[sid + 1],
                               seed=int(ta * 24) * 13 + k, power=amt * 0.9)
    for p in _power_at("beam"):
        _draw_beam(cv, scene, p, ta, cam_state)
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
        focus = next((e.get("anchor") and (e["x"], e["y"]) or (e["x"], e["y"])
                      for e in scene["impacts"] if abs(e["t"] - seed) < 0.03
                      and e.get("x") is not None), None)
        vfx.impact_frame(cv, tracks, ta, seed + 0.01 * sub, draw_fighter,
                         sub=sub, focus=focus)
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
        # the blur is *ramped in* over the first few pixels of travel and mixed
        # by weight rather than switched on at a threshold: a shutter that pops
        # from sharp to smeared between two frames is the single most obvious
        # tell that a camera is being faked
        if mag > 0.6:
            amt = min(1.0, 0.45 + 0.30 * cam_state["whip"])
            scale = min(1.0, 22.0 / mag)
            ramp = min(1.0, (mag - 0.6) / 3.0)
            cv.img = directional(cv.img, dx * scale * amt, dy * scale * amt,
                                 samples=8, weight=ramp)

    # bloom: only while something hot is on screen, because it is not free
    hot = any(0.0 <= t - e["t"] < 0.22 and not e.get("sparks")
              for e in scene["impacts"])
    if hot:
        cv.img = vfx.bloom(cv.img, 0.42)

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
def synth_audio(scene, duration=DURATION) -> np.ndarray:
    """The soundtrack. Built in ``fight/sound.py``: foley, taiko score and mix.

    The audio is derived from the scene's own events — impacts, foot plants from
    the solved rig, the ink frames, the K.O. card — so a fight that changes
    changes its sound with it, and nothing has to be re-timed by hand.
    """
    from . import sound
    return sound.score(scene, duration)


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


def _write_audio(wav_path: str, seconds: float, set_name: str,
                 start: float = 0.0) -> None:
    """The score for the whole film, then the part this render actually covers.

    A partial render (``--start 17 --end 23``) used to get the first six seconds
    of the soundtrack, which is why a slice sounded like a different fight.
    """
    sc = scene(set_name)
    full = synth_audio(sc, start + seconds)
    i0 = int(start * SR)
    write_wav(wav_path, full[i0:i0 + int(seconds * SR)])


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
        ap = Process(target=_write_audio,
                     args=(wav, total / FPS, set_name, start), daemon=True)
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
