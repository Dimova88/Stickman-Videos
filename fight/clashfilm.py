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


# how a body is assembled: each chain is a smooth tube, not a row of segments
CHAINS = (
    # (points, root width, tip width) — rear leg, lead leg, spine, rear arm, lead arm
    ((0, 7, 8), 12.5, 9.5),
    ((0, 9, 10), 12.5, 9.5),
    ((0, 1), 13.5, 12.0),
    ((1, 3, 4), 10.0, 7.5),
    ((1, 5, 6), 10.0, 7.5),
)


def _capsule(cv: Canvas, a, b, w0: float, w1: float, colour) -> None:
    """A tapered bone with rounded ends, and no cap wider than the bone.

    Limbs are drawn as a union of these plus a disc at each joint sized to the
    bone there, so the silhouette bends smoothly and no circle shows up on the
    elbow, the knee or the shoulder.
    """
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    r0, r1 = w0 * 0.5, w1 * 0.5
    cv.polygon([(a[0] + nx * r0, a[1] + ny * r0),
                (b[0] + nx * r1, b[1] + ny * r1),
                (b[0] - nx * r1, b[1] - ny * r1),
                (a[0] - nx * r0, a[1] - ny * r0)], colour)
    cv.circle(a, r0, colour, width=0, fill=colour)
    cv.circle(b, r1, colour, width=0, fill=colour)


def _chain(cv: Canvas, pts, w0: float, w1: float, colour) -> None:
    n = len(pts) - 1
    for i in range(n):
        f0, f1 = i / n, (i + 1) / n
        _capsule(cv, pts[i], pts[i + 1], w0 + (w1 - w0) * f0, w0 + (w1 - w0) * f1,
                 colour)


def draw_fighter(cv: Canvas, track, t: float) -> None:
    """Flat silhouette: smooth tapered limbs, no joints, solid head."""
    pose = track.pose_at(t)
    sk = solve(pose)
    u = cv.unit() * pose.scale
    colour = track.colour

    hip = sk.starts[1]                       # the pelvis is where segment 1 begins
    for ids, w0, w1 in CHAINS:
        rest = ids[1:] if ids[0] == 0 else ids
        first = hip if ids[0] == 0 else sk.pts[ids[0]]
        pts = [first] + [sk.pts[i] for i in rest]
        _chain(cv, [cv.wp(p) for p in pts], w0 * u, w1 * u, colour)

    c = cv.wp(sk.head)
    r = sk.head_r * u
    cv.circle(c, r, colour, width=0, fill=colour)


def trails(cv: Canvas, track, t: float, dt: float = 0.075) -> None:
    """Speed lines: compare each limb with where it was 0.075 s ago."""
    if t < dt + 0.02:
        return
    now = track.skel(t)
    then = track.skel(t - dt)
    u = cv.unit() * now.scale
    for sid in (4, 6, 8, 10):
        a, b = then.pts[sid], now.pts[sid]
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        if d < 12.0:
            continue
        k = min(1.0, (d - 12.0) / 30.0)
        nx, ny = -dy / d, dx / d
        p1 = cv.wp(b)
        for i, off in enumerate((-0.55, 0.0, 0.62)):
            fade = 1.0 - abs(off) * 0.55
            ln = (d * (0.85 + 0.25 * (1 - abs(off)))) * u
            o = off * 9.0 * u
            p0 = (p1[0] - dx * u * (0.85 + 0.25 * (1 - abs(off))) + nx * o,
                  p1[1] - dy * u * (0.85 + 0.25 * (1 - abs(off))) + ny * o)
            cv.line(p0, (p1[0] + nx * o, p1[1] + ny * o),
                    max(1.2, (3.4 - abs(off) * 1.6) * u),
                    track.colour, alpha=int(120 * k * fade), caps=False)


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
    draw_background(cv, t, scene)

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
