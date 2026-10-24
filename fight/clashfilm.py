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
from PIL import Image, ImageDraw, ImageFont

from .clash import (BLUE, BLUE_DARK, DESIGN_H, DESIGN_W, DURATION, FPS, GROUND,
                    INK, RED, RED_DARK, build)
from .insert import cut_at, draw_insert
from .core import SEG, SEGMENT_ORDER, solve
from .draw import Canvas, Cam

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "assets")
SET_FILES = {"mountain": "mountain_background.png",
             "desert": "desert_background.png"}
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


def _build_backgrounds(w: int, h: int, zmin: float, zmax: float, path: str):
    """One pre-scaled landscape plate per zoom level, vignette baked in.

    Each plate is the output size plus the pan margin, so a finished frame is an
    integer crop from one or two of them and nothing is resampled per frame.
    """
    from PIL import Image as _I
    k = w / DESIGN_W
    src = Image.open(path).convert("RGB")
    if src.size != (BG_W, BG_H):
        src = src.resize((BG_W, BG_H), _I.LANCZOS)
    src = src.resize((int(round(BG_SCALED[0] * k)), int(round(BG_SCALED[1] * k))),
                     _I.LANCZOS)
    # the plate is the padded landscape; the pan margin is whatever is left
    pw, ph = src.size
    padx = max(1, (pw - w) // 2)
    pady = max(1, (ph - h) // 2)

    vig = vignette()
    if vig.size != (w, h):
        vig = vig.resize((w, h), _I.BILINEAR)
    vig_rgb, vig_mask = vig.convert("RGB"), vig.split()[3]

    plates = []
    for i in range(ZOOM_LEVELS):
        z = zmin + (zmax - zmin) * (i / (ZOOM_LEVELS - 1))
        sw, sh = pw / z, ph / z
        cx, cy = src.width * 0.5, src.height * 0.5
        plate = src.resize((pw, ph), _I.BILINEAR,
                           box=(cx - sw / 2, cy - sh / 2, cx + sw / 2, cy + sh / 2))
        # the vignette is baked in at the nominal framing, so most frames get it
        # for free; the camera can drag it by at most the pan margin (20x11 px),
        # which on a gradient this soft moves the alpha by ~2/255
        plate.paste(vig_rgb, (padx, pady), vig_mask)
        plates.append(plate)
    return plates, padx, pady


def background(zoom: float, w: int, h: int, zmin: float, zmax: float, path: str):
    """The two plates straddling `zoom`, plus the blend weight between them."""
    key = (w, h, zmin, zmax, path)
    if _bg_cache.get("key") != key:
        _bg_cache["plates"], _bg_cache["padx"], _bg_cache["pady"] = \
            _build_backgrounds(w, h, zmin, zmax, path)
        _bg_cache["key"] = key
    plates = _bg_cache["plates"]
    f = (zoom - zmin) / max(zmax - zmin, 1e-6) * (ZOOM_LEVELS - 1)
    f = min(max(f, 0.0), ZOOM_LEVELS - 1.0)
    k = int(f)
    k2 = min(k + 1, ZOOM_LEVELS - 1)
    return plates[k], plates[k2], f - k


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
def camera_at(keys, t: float):
    """Returns (dx, dy, zoom) for the landscape crop."""
    if t <= keys[0][0]:
        return keys[0][1:]
    if t >= keys[-1][0]:
        return keys[-1][1:]
    for i in range(len(keys) - 1):
        t0, x0, y0, z0 = keys[i]
        t1, x1, y1, z1 = keys[i + 1]
        if t0 <= t <= t1:
            u = (t - t0) / max(t1 - t0, 1e-9)
            u = u * u * (3 - 2 * u)
            return (x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, z0 + (z1 - z0) * u)
    return keys[-1][1:]


def shake_at(impacts, t: float):
    """Exponential shake for 0.32 s after an impact; the final hit hits harder."""
    sx = sy = 0.0
    for e in impacts:
        age = t - e["t"]
        if not (0.0 <= age < 0.32):
            continue
        k = (1.0 - age / 0.32) ** 2
        amp = (14.0 if e["kind"] == "final" else
               9.0 if e["kind"] == "clash" else
               6.0 if e["kind"] == "hit" else 3.2) * e.get("size", 1.0)
        sx += math.sin(age * 71.0 + e["t"] * 13.0) * amp * k
        sy += math.cos(age * 57.0 + e["t"] * 7.0) * amp * 0.7 * k
    return sx, sy


# --------------------------------------------------------------------- drawing
def draw_background(cv: Canvas, t: float, scene) -> None:
    dx, dy, zoom = camera_at(scene["camera"], t)
    sx, sy = shake_at(scene["impacts"], t)
    zs = [k[3] for k in scene["camera"]]
    p1, p2, a = background(zoom, cv.w, cv.h, min(zs), max(zs), scene["bg_path"])
    padx, pady = _bg_cache["padx"], _bg_cache["pady"]
    k = cv.w / DESIGN_W
    ox = int(round(min(2 * padx, max(0.0, padx + (dx + sx) * k))))
    oy = int(round(min(2 * pady, max(0.0, pady + (dy + sy) * k))))
    bg = p1.crop((ox, oy, ox + cv.w, oy + cv.h))
    if a > 0.002:
        bg = Image.blend(bg, p2.crop((ox, oy, ox + cv.w, oy + cv.h)), a)
    # a crop is already an independent image, so it becomes the frame outright
    # instead of being copied into a fresh canvas (+1 ms/frame)
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


def scene(set_name: str = "mountain"):
    """The choreography is deterministic: build it once per process and set."""
    if set_name not in _scene_cache:
        sc = build(set_name)
        sc["bg_path"] = os.path.join(ASSETS, SET_FILES.get(set_name, "mountain_background.png"))
        _scene_cache[set_name] = sc
    return _scene_cache[set_name]


def shadow_box(cv: Canvas, sk, lift: float):
    """Where the contact shadow of one fighter sits, in screen pixels."""
    fx = (sk.pts[8][0] + sk.pts[10][0]) * 0.5
    c = cv.wp((fx, GROUND - 2))
    rx = (78.0 + 26.0 * lift) * cv.unit() * sk.scale
    ry = rx * (0.17 - 0.04 * min(lift, 1.0))
    return (c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry)


def shadow(ov: "Overlay", sk, lift: float) -> None:
    """A flat contact shadow: wide and faint under an airborne fighter."""
    alpha = int(max(16, 76 - 40 * lift))
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
FOOT_LEN, FOOT_HEEL, FOOT_T = 27.0, 9.0, 11.5
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


def _foot(cv: Canvas, ankle, tilt: float, colour, u: float, facing: int = 1,
          alpha: int = 255) -> None:
    """A wedge with a heel and a toe, hinged at the ankle.

    Built in a local frame where +x is the way the fighter faces, then mirrored
    (never rotated by pi — that turns the foot upside down). ``tilt`` lifts the
    toe: 0 is flat on the floor, positive points the toe down, which is what a
    kick does at full extension.
    """
    L, hb, t = FOOT_LEN * u, FOOT_HEEL * u, FOOT_T * u
    rot = tilt * facing
    ca, sa = math.cos(rot), math.sin(rot)
    # flat sole, heel at the back, instep high over the ankle, toe down the front
    loc = [(-hb, 0.0), (-hb, -t * 0.72), (-hb * 0.40, -t * 1.00),
           (L * 0.42, -t * 0.74), (L * 0.88, -t * 0.34), (L, -t * 0.06),
           (L * 0.90, 0.0), (L * 0.10, 0.0)]
    pts = []
    for x, y in loc:
        x *= facing
        pts.append((ankle[0] + x * ca - y * sa, ankle[1] + x * sa + y * ca))
    cv.polygon(pts, colour, alpha=alpha)
    cv.circle((ankle[0], ankle[1] - t * 0.22), t * 0.34, colour, width=0,
              fill=colour, alpha=alpha)


def _hand(cv: Canvas, wrist, ang: float, grip: float, colour, dark, u: float,
          alpha: int = 255) -> None:
    """A fist when the hand is closed, an open hand with fingers when it is not."""
    ca, sa = math.cos(ang), math.sin(ang)
    grip = max(0.0, min(1.0, grip))
    if grip > 0.5:
        r = FIST_R * u * (0.94 + 0.10 * grip)
        cx, cy = wrist[0] + ca * r * 0.30, wrist[1] + sa * r * 0.30
        bump = [(cx + x * ca - y * sa, cy + x * sa + y * ca)
                for x, y in ((r * 1.06, 0.0), (r * 0.46, r * 0.80),
                             (-r * 0.62, r * 0.74), (-r * 1.02, 0.0),
                             (-r * 0.62, -r * 0.74), (r * 0.46, -r * 0.80))]
        cv.polygon(bump, colour, alpha=alpha)
        cv.circle((cx, cy), r * 0.72, colour, width=0, fill=colour, alpha=alpha)
        # the knuckle line: a crease facing the way the fist is thrown
        cv.line((cx + r * 0.52 * ca - r * 0.42 * sa, cy + r * 0.52 * sa + r * 0.42 * ca),
                (cx + r * 0.30 * ca + r * 0.52 * sa, cy + r * 0.30 * sa - r * 0.52 * ca),
                2.4 * u, dark, alpha=int(alpha * 0.75), caps=False)
    else:
        open_k = 1.0 - grip / 0.5
        palm = PALM_R * u
        cv.circle(wrist, palm, colour, width=0, fill=colour, alpha=alpha)
        for i, spread in enumerate((-0.30, -0.04, 0.22, 0.52)):
            a2 = ang + spread * (0.4 + 0.6 * open_k)
            ln = FINGER_L * u * (0.80 if i == 3 else 1.0) * open_k
            tip = (wrist[0] + math.cos(a2) * (palm * 0.9 + ln),
                   wrist[1] + math.sin(a2) * (palm * 0.9 + ln))
            root = (wrist[0] + math.cos(a2) * palm * 0.6,
                    wrist[1] + math.sin(a2) * palm * 0.6)
            _capsule(cv, root, tip, 2.9 * u, 2.0 * u, colour, alpha)


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

    ex = c[0] + fx * r * 0.30
    ey = c[1] - r * 0.04
    front = (ex + fx * r * 0.40, ey + r * 0.07)      # toward the nose, low
    back = (ex - fx * r * 0.36, ey - r * 0.14)       # outer corner, high
    topm = (ex + fx * r * 0.04, ey - r * 0.22)
    botm = (ex + fx * r * 0.02, ey + r * 0.14)
    cv.polygon([front, topm, back, botm], dark)
    # the iris burns inside the socket: this is the "glowing eye", and it is
    # what carries the expression when the head is only forty pixels across
    ix, iy = ex + fx * r * 0.16, ey - r * 0.01
    ir = r * (0.145 + 0.035 * min(1.0, glow))
    if glow > 0.02:
        cv.circle((ix, iy), ir * 3.0, (255, 198, 120),
                  width=0, fill=(255, 198, 120), alpha=int(44 + 120 * glow))
    cv.circle((ix, iy), ir, (255, 226, 158), width=0, fill=(255, 226, 158))
    cv.circle((ix + fx * ir * 0.16, iy - ir * 0.20), ir * 0.46, (255, 252, 240),
              width=0, fill=(255, 252, 240))
    # the brow: a wedge over the socket, thick outside and riding down toward
    # the nose. Slant = anger, and it steepens when he is swinging.
    droop = 0.08 + 0.14 * hurt
    lift = 0.10
    tb = (back[0], back[1] - r * (0.12 + lift + 0.06 * min(1.0, glow)))
    tf = (front[0] + fx * r * 0.02, front[1] - r * (0.15 + lift - droop))
    cv.polygon([back, tb, tf, front], dark)
    # a short mouth line, thinner than the socket, pulled down when hurt
    mx, my = c[0] + fx * r * 0.50, c[1] + r * 0.44
    cv.line((mx - fx * r * 0.15, my - r * 0.02),
            (mx + fx * r * 0.13, my - r * 0.02 - r * 0.04 * hurt),
            2.6 * u, dark, alpha=170, caps=False)


def _speed(now, then, sid: int, dt: float = 0.05):
    """Where a limb tip is heading and how fast, in design units per second."""
    a = then.pts[sid]
    b = now.pts[sid]
    return (b[0] - a[0], b[1] - a[1]), math.hypot(b[0] - a[0], b[1] - a[1]) / dt


def draw_fighter(cv: Canvas, track, t: float) -> None:
    """The body: bowed spine, tapered limbs, feet on the floor, hands, face.

    The skeleton still comes from the same IK solve the choreography was written
    against — the anatomy only changes how that skeleton is painted, plus the
    speed-driven deformation (stretch along the swing, joints trailing behind).
    """
    pose = track.pose_at(t)
    sk = solve(pose)
    u = cv.unit() * pose.scale
    colour, dark = track.colour, track.dark
    g = GROUND

    then = track.skel(max(0.0, t - 0.05)) if t > 0.06 else sk

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
        pts = [(p[0], p[1]) for p, _w in joints]
        pts = _bend(pts, vel[0] / sp, vel[1] / sp, 2.6 * u * k)
        widths = [w * u for _p, w in joints]
        tp, tw = _tube_pts([(p, w / u) for p, w in zip(pts, widths)])
        _tube(cv, [cv.wp(p) for p in tp], [w * u for w in tw], col)
        _hand(cv, cv.wp(tp[-1]), sk.tip_angle(sid_lo), grip, col, dark, u)

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
        tp, tw = _tube_pts(list(zip(pts, widths)))
        _tube(cv, [cv.wp(p) for p in tp], tw, col)
        ank = tp[-1]
        planted = (pose.lift_a if sid_lo == 8 else pose.lift_b) <= 0.6
        fwd = 0.0 if pose.facing > 0 else math.pi
        if planted:
            tilt = 0.0
        else:
            # a foot in the air points along the shin only when the shin is
            # already driving forward (a kick); a foot that is merely off the
            # floor hangs flat instead of pointing at the ground behind
            sh = sk.tip_angle(sid_lo)
            if math.sin(sh) < -0.15:
                tilt = 1.48          # knee raised: the foot hangs off the ankle
            else:
                align = max(0.0, math.cos(sh - fwd))
                rel = (sh - fwd + math.pi) % (2 * math.pi) - math.pi
                rel = max(-0.35, min(1.30, rel))
                tilt = rel * (0.18 + 0.82 * align) + pitch
        _foot(cv, cv.wp(ank), tilt, col, u, pose.facing)

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
    """Smear frames: the fan a limb swept, in a light tint of the body colour.

    A wedge behind the fist is invisible on a straight punch, because the punch
    travels along the arm — there the *stretch* inside draw_fighter carries the
    speed. What a kick, a hook or a sweep needs is the arc it crossed: the fan
    from the shoulder or the hip between where the limb was and where it is,
    plus a short streak past the tip.
    """
    if t < dt + 0.02:
        return
    now = track.skel(t)
    then = track.skel(t - dt)
    u = cv.unit() * now.scale
    tint = _lighten(track.colour, 0.40)
    for sid in (4, 6, 8, 10):
        pivot = now.starts[sid]
        b = now.pts[sid]
        a = then.pts[sid]
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        k = min(1.0, max(0.0, (d - 8.0) / 22.0))
        if k < 0.30:
            continue
        P, A, B = cv.wp(pivot), cv.wp(a), cv.wp(b)
        cv.polygon([P, A, B], tint, alpha=int(78 * k))
        # the leading edge, fainter, so the streak has a soft end
        cv.polygon([P, B, ((B[0] + P[0]) * 0.5, (B[1] + P[1]) * 0.5)], tint,
                   alpha=int(46 * k))
        # a short streak past the tip, thrown further by the faster limbs
        if k > 0.45:
            f = 0.30 * (k - 0.45) / 0.55
            vx, vy = B[0] - A[0], B[1] - A[1]
            L = math.hypot(vx, vy) or 1.0
            tip = (B[0] + vx * f, B[1] + vy * f)
            w = 4.6 * u * (0.4 + 0.6 * k)
            nx, ny = -vy / L, vx / L
            cv.polygon([(B[0] + nx * w, B[1] + ny * w), tip,
                        (B[0] - nx * w, B[1] - ny * w)],
                       tint, alpha=int(112 * k))


# --------------------------------------------------------------------- effects
def star(cx, cy, r_out, r_in, n=7, rot=0.0):
    pts = []
    for i in range(n * 2):
        a = rot + i * math.pi / n
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r))
    return pts


def draw_impacts(cv: Canvas, impacts, t: float, overlay_flash: list) -> None:
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

        if age < (0.42 if final else 0.26):
            k = age / (0.42 if final else 0.26)
            grow = 1 - (1 - k) ** 2
            r = (16 + 30 * size) * u * (0.55 + 0.75 * grow) * (1 - 0.3 * k)
            cv.polygon(star(cx, cy, r, r * 0.40, 7 if not final else 9,
                            0.4 + e["t"] * 2.7), (255, 255, 255),
                       alpha=int(245 * (1 - k) ** 0.6), width=max(2.0, 4.4 * u),
                       outline=INK)

        # radial particles, fixed seed per impact so the render is reproducible
        if age < (0.60 if final else 0.42):
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

        # sparks: length decays with age
        if age < 0.30:
            k = age / 0.30
            rng = np.random.default_rng(int(e["t"] * 977) % 65537)
            base = 0.5 + e["t"] * 1.7
            n_sp = 6 + (3 if final else 0)
            for i in range(n_sp):
                a = base + i * math.tau / n_sp
                ln = (20 + 46 * size) * u * (1 - k) ** 1.4
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


def draw_hud(cv: Canvas, scene, t: float) -> None:
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

    # markers
    for txt in scene["texts"]:
        if not (txt["t0"] <= t <= txt["t1"]):
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


# ----------------------------------------------------------------------- frame
def render_frame(t: float, scene, w: int = DESIGN_W, h: int = DESIGN_H) -> Image.Image:
    """One finished frame at design size, scaled down if a smaller size is asked.

    The HUD is authored in design coordinates, so drawing natively at 640p used
    to run the bars off the frame. Everything is now composed at 1280x720 and the
    finished frame is resampled, which makes any smaller size a true preview of
    the master instead of a second layout.
    """
    cam = Cam(640.0, 360.0, 1.0)
    cv = Canvas(DESIGN_W, DESIGN_H, cam)
    cut = cut_at(t)
    if cut is None:
        draw_background(cv, t, scene)

    if cut is not None:
        # the close-up register: a cut, not a camera move, so no HUD shadows,
        # no dust and no star burst — just the body and the light on it
        draw_insert(cv, cut, scene)
        draw_hud(cv, scene, t)
        if (w, h) != (DESIGN_W, DESIGN_H):
            return cv.img.resize((w, h), Image.LANCZOS)
        return cv.img

    # far fighter first: the one further from the centre of action
    heads = {tr.name: tr.skel(t) for tr in (scene["red"], scene["blue"])}
    order = sorted((scene["red"], scene["blue"]),
                   key=lambda tr: -abs(heads[tr.name].head[0] - 640))

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
    for tr in order:
        shadow(ov, heads[tr.name], lifts[tr.name])
    ov.flush()

    for tr in order:
        trails(cv, tr, t)
    for tr in order:
        draw_fighter(cv, tr, t)
    cv.flush()

    draw_dust(scene["dust"], t, cv.unit(), *cv.wp((DESIGN_W * 0.5, GROUND)), cv)

    flash = []
    draw_impacts(cv, scene["impacts"], t, flash)
    cv.flush()

    if flash:
        a = min(220, sum(flash))
        cv.img.paste(Image.blend(cv.img, Image.new("RGB", (DESIGN_W, DESIGN_H),
                                                   (255, 253, 246)), a / 255.0),
                     (0, 0))

    draw_hud(cv, scene, t)

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
