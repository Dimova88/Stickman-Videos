"""Mountains Clash, 30 s test — renderer.

One frame = background crop (with camera drift and impact shake) -> vignette ->
fighters (rear limbs darker, ink outline, contact shadow) -> motion trails ->
impact effects -> dust -> HUD (health bars, timer, titles, cinematic bars) ->
fades. Frames are piped to FFmpeg as raw RGB, never written to disk as stills,
and the synthesised WAV is muxed on afterwards.
"""
from __future__ import annotations

import math
import os
import subprocess
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .clash import (BLUE, BLUE_DARK, DESIGN_H, DESIGN_W, DURATION, FPS, GROUND,
                    INK, RED, RED_DARK, build)
from .core import SEG, SEGMENT_ORDER, solve
from .draw import Canvas, Cam

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "assets")
BG_PATH = os.path.join(ASSETS, "mountain_background.png")
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
_bg_cache: dict = {}


def background() -> Image.Image:
    if "img" not in _bg_cache:
        im = Image.open(BG_PATH).convert("RGB")
        if im.size != (BG_W, BG_H):
            im = im.resize((BG_W, BG_H), Image.LANCZOS)
        _bg_cache["img"] = im.resize(BG_SCALED, Image.LANCZOS)
    return _bg_cache["img"]


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
    # the crop window: 40 px of horizontal travel, 22 px vertical, from the shake
    ox = int(round(min(40.0, max(0.0, 20.0 + dx + sx))))
    oy = int(round(min(22.0, max(0.0, 11.0 + dy + sy))))
    bg = background().crop((ox, oy, ox + DESIGN_W, oy + DESIGN_H))
    if abs(zoom - 1.0) > 1e-4:
        zw = int(DESIGN_W * zoom)
        zh = int(DESIGN_H * zoom)
        bg = bg.resize((zw, zh), Image.BILINEAR)
        left = (zw - DESIGN_W) // 2
        top = (zh - DESIGN_H) // 2
        bg = bg.crop((left, top, left + DESIGN_W, top + DESIGN_H))
    cv.img.paste(bg, (0, 0))
    cv.img.paste(vignette(), (0, 0), vignette())


def overlay(cv: Canvas):
    layer = Image.new("RGBA", (cv.w, cv.h), (0, 0, 0, 0))
    return layer, ImageDraw.Draw(layer)


def composite(cv: Canvas, layer: Image.Image) -> None:
    """One alpha composite for a whole batch of translucent shapes."""
    cv.flush()
    cv.img = Image.alpha_composite(cv.img.convert("RGBA"), layer).convert("RGB")
    cv.d = ImageDraw.Draw(cv.img)


_scene_cache = {}


def scene():
    """The choreography is deterministic: build it once per process."""
    if "s" not in _scene_cache:
        _scene_cache["s"] = build()
    return _scene_cache["s"]


def shadow(d: ImageDraw.ImageDraw, cv: Canvas, sk, lift: float) -> None:
    """A flat contact shadow: wide and faint under an airborne fighter."""
    fx = (sk.pts[8][0] + sk.pts[10][0]) * 0.5
    c = cv.wp((fx, GROUND - 2))
    rx = (78.0 + 26.0 * lift) * cv.unit() * sk.scale
    ry = rx * (0.17 - 0.04 * min(lift, 1.0))
    alpha = int(max(16, 76 - 40 * lift))
    d.ellipse([c[0] - rx, c[1] - ry, c[0] + rx, c[1] + ry], fill=(20, 16, 14, alpha))


# the renderer sets this to the current frame's shadow overlay
SHADOW_LAYER: list = [None]

# limb draw order: rear leg, lead leg, spine, rear arm, lead arm, then the head
DRAW_ORDER = (7, 9, 8, 10, 1, 3, 4, 5, 6)


def draw_fighter(cv: Canvas, track, t: float) -> None:
    """Flat silhouette: no outline, solid round-capped limbs, solid head."""
    pose = track.pose_at(t)
    sk = solve(pose)
    u = cv.unit() * pose.scale
    colour = track.colour

    for sid in DRAW_ORDER:
        _id, _parent, _length, thick, kind = SEG[sid]
        if kind == "circle":
            continue
        p0, p1 = cv.wp(sk.starts[sid]), cv.wp(sk.pts[sid])
        cv.line(p0, p1, thick * u * 1.15, colour)

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

        if age < life:
            k = age / life
            # expanding ring
            ring = 0.50 if kind == "clash" else 0.62 if kind == "block" else 0.80
            rr = (12 + 74 * size * ring) * u * (0.35 + 1.15 * (1 - (1 - k) ** 2))
            cv.circle((cx, cy), rr, e.get("colour", (240, 236, 228)),
                      width=max(1.6, (4.5 if final else 3.2) * u * (1 - k)),
                      alpha=int(210 * (1 - k) ** 1.3))

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
                a = int(230 * (1 - k) ** 1.6)
                cv.disc((px, py), rr, (250, 246, 238))
                if a > 40:
                    cv.circle((px, py), rr, INK, width=max(1.0, 1.2 * u), alpha=a)

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


def draw_dust(d: ImageDraw.ImageDraw, cv: Canvas, dusts, t: float) -> None:
    u = cv.unit()
    for t0 in dusts:
        age = t - t0
        if not (0.0 <= age < 0.75):
            continue
        k = age / 0.75
        rng = np.random.default_rng(int(t0 * 1000) % 7919)
        cx, cy = cv.wp((DESIGN_W * 0.5, GROUND))
        for i in range(14):
            side = -1 if i % 2 else 1
            spd = rng.uniform(0.45, 1.3)
            px = cx + side * (14 + 165 * k * spd) * u
            py = cy - (2 + 24 * k * rng.uniform(0.2, 1.0)) * u
            rr = (9 + 20 * k) * u * rng.uniform(0.6, 1.2)
            alpha = int(52 * (1 - k) ** 2.1)
            d.ellipse([px - rr, py - rr * 0.42, px + rr, py + rr * 0.42],
                      fill=(212, 202, 184, alpha))


# ------------------------------------------------------------------------- HUD
def health_curve(scene, who: str, t: float) -> float:
    """Health at t: damage applied per impact, approached over 0.32 s."""
    key = "dmg_red" if who == "red" else "dmg_blue"
    v = 100.0
    sm = 100.0
    step = 1.0 / 120.0
    tt = 0.0
    idx = 0
    hits = sorted(scene["impacts"], key=lambda e: e["t"])
    while tt < t:
        while idx < len(hits) and hits[idx]["t"] <= tt:
            v = max(0.0, v - hits[idx].get(key, 0.0))
            idx += 1
        k = 1.0 - math.exp(-step / 0.11)
        sm += (v - sm) * k
        tt += step
    return max(0.0, sm)


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
    cam = Cam(640.0, 360.0, 1.0)
    cv = Canvas(w, h, cam)
    draw_background(cv, t, scene)

    # far fighter first: the one further from the centre of action
    order = sorted((scene["red"], scene["blue"]),
                   key=lambda tr: -abs(tr.skel(t).head[0] - 640))

    # contact shadows in one translucent pass under everything
    shadow_layer, shadow_d = overlay(cv)
    SHADOW_LAYER[0] = shadow_d
    for tr in order:
        pose = tr.pose_at(t)
        sk = solve(pose)
        feet_y = max(sk.pts[8][1], sk.pts[10][1])
        shadow(shadow_d, cv, sk, max(0.0, GROUND - feet_y) / 90.0)
    composite(cv, shadow_layer)

    for tr in order:
        trails(cv, tr, t)
    for tr in order:
        draw_fighter(cv, tr, t)
    cv.flush()

    dust_layer, dust_d = overlay(cv)
    draw_dust(dust_d, cv, scene["dust"], t)
    composite(cv, dust_layer)

    flash = []
    draw_impacts(cv, scene["impacts"], t, flash)
    cv.flush()

    if flash:
        a = min(220, sum(flash))
        cv.img.paste(Image.blend(cv.img, Image.new("RGB", (w, h), (255, 253, 246)),
                                 a / 255.0), (0, 0))

    draw_hud(cv, scene, t)

    # fades
    fade = 0.0
    if t < 0.7:
        fade = 1.0 - t / 0.7
    elif t > DURATION - 1.1:
        fade = (t - (DURATION - 1.1)) / 1.1
    if fade > 0.001:
        cv.img.paste(Image.blend(cv.img, Image.new("RGB", (w, h), (6, 6, 8)),
                                 min(1.0, fade) ** 1.15), (0, 0))
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


def thud(size=1.0, metallic=False, length=0.42):
    n = int(length * SR)
    t = np.arange(n) / SR
    f0 = 120 - 50 * min(size, 1.6)
    body = np.sin(2 * np.pi * f0 * t) * np.exp(-t * (13 - 4 * min(size, 1.5)))
    sub = np.sin(2 * np.pi * (f0 * 0.5) * t) * np.exp(-t * 7) * 0.8
    rng = np.random.default_rng(5)
    noise = rng.normal(0, 1, n).astype(np.float32)
    # one-pole low-pass
    out = np.empty(n, np.float32)
    y = 0.0
    for i in range(n):
        y += 0.28 * (noise[i] - y)
        out[i] = y
    crack = out * np.exp(-t * 42) * 0.9
    sig = body * 0.85 + sub * 0.5 + crack * 0.55
    if metallic:
        ring = (np.sin(2 * np.pi * 1250 * t) + 0.6 * np.sin(2 * np.pi * 1860 * t))
        sig += ring * np.exp(-t * 26) * 0.22
    return (sig * _env(n, 0.002, length * 0.55)).astype(np.float32)


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
    n = int(duration * SR)
    mix = np.zeros((n, 2), np.float32)

    def add(sig, t, gain=1.0, pan=0.0):
        if t < 0:
            return
        i0 = int(t * SR)
        if i0 >= n:
            return
        m = min(len(sig), n - i0)
        # constant-power panning
        ang = (pan + 1.0) * math.pi / 4.0
        mix[i0:i0 + m, 0] += sig[:m] * gain * math.cos(ang)
        mix[i0:i0 + m, 1] += sig[:m] * gain * math.sin(ang)

    def note(freq, dur, gain, t, pan=0.0, kind="sine"):
        nn = int(dur * SR)
        tt = np.arange(nn) / SR
        if kind == "sine":
            s = np.sin(2 * np.pi * freq * tt) + 0.35 * np.sin(4 * np.pi * freq * tt)
        else:
            s = np.sign(np.sin(2 * np.pi * freq * tt)) * 0.5
        s = s * np.exp(-tt * 3.2) * _env(nn, 0.004, dur * 0.7)
        add(s.astype(np.float32), t, gain, pan)

    # ---- low cinematic pulse bed
    bed_n = n
    tt = np.arange(bed_n) / SR
    swell = np.clip((tt - 0.4) / 2.0, 0, 1) * np.clip((duration - 1.0 - tt) / 3.0, 0, 1)
    drone = (np.sin(2 * np.pi * 41.2 * tt) * 0.5 + np.sin(2 * np.pi * 61.7 * tt) * 0.3)
    mix[:, 0] += (drone * swell * 0.13).astype(np.float32)
    mix[:, 1] += (drone * swell * 0.13).astype(np.float32)

    # ---- drums from the "FIGHT!" cue to the K.O.
    t0, t1 = 2.15, 24.9
    beat = t0
    i = 0
    while beat < t1:
        add(thud(0.7, length=0.26), beat, 0.42 if i % 2 == 0 else 0.26)
        # snare on the off beats
        sn = np.random.default_rng(20 + i).normal(0, 1, int(0.11 * SR)).astype(np.float32)
        sn *= np.exp(-np.arange(len(sn)) / SR * 38)
        add(sn, beat + 0.25, 0.14)
        beat += 0.5
        i += 1
    # hats on the sixteenths
    h = t0
    while h < t1:
        hs = np.random.default_rng(40 + int(h * 100)).normal(0, 1, int(0.045 * SR)).astype(np.float32)
        hs *= np.exp(-np.arange(len(hs)) / SR * 120)
        add(hs, h, 0.06, pan=0.35)
        h += 0.25

    # ---- whooshes on every strike lead-in (the swipe before the impact)
    for e in scene["impacts"]:
        add(whoosh(0.24, up=e["x"] > DESIGN_W / 2), e["t"] - 0.10, 0.30,
            pan=(e["x"] / DESIGN_W) * 2 - 1)
    extra = 0.0
    while extra < duration and len(scene["impacts"]) + 4 < 32:
        extra += 1.0
    # a few movement swishes that are not impacts
    for tt_ in (6.9, 15.14, 18.98, 23.84):
        add(whoosh(0.3, up=tt_ < 12), tt_ - 0.12, 0.24, pan=-0.25 if tt_ < 12 else 0.25)

    # ---- impacts
    for e in scene["impacts"]:
        pan = (e["x"] / DESIGN_W) * 2 - 1
        kind = e["kind"]
        if kind == "block":
            add(thud(0.6, metallic=True, length=0.30), e["t"], 0.62, pan)
        elif kind == "hit":
            add(thud(1.0, length=0.40), e["t"], 0.95, pan)
        elif kind == "clash":
            add(thud(1.2, metallic=True, length=0.5), e["t"], 1.0, pan)
        elif kind == "final":
            add(thud(1.8, length=0.95), e["t"], 1.25, pan)
            add(thud(1.6, metallic=True, length=0.8), e["t"] + 0.015, 0.7, pan)

    # ---- dust thumps
    for tt_ in scene["dust"]:
        add(thud(0.35, length=0.24), tt_, 0.30, pan=-0.2)

    # ---- rise to victory: C - E - G - C, major
    for i, (f, dt_) in enumerate(zip((261.63, 329.63, 392.00, 523.25), (0.0, 0.16, 0.32, 0.60))):
        note(f, 1.6, 0.34 if i < 3 else 0.42, 25.35 + dt_, pan=0.15 * (i - 1.5))
        note(f * 2, 1.0, 0.07, 25.35 + dt_, pan=-0.1, kind="sq")

    # ---- fades and peak control
    fin = int(0.5 * SR)
    mix[:fin] *= np.linspace(0, 1, fin)[:, None]
    fout = int(1.3 * SR)
    mix[-fout:] *= np.linspace(1, 0, fout)[:, None]
    mix = np.tanh(mix * 1.6)
    peak = float(np.max(np.abs(mix))) or 1.0
    mix = mix / peak * 0.94
    # gentle make-up so the quiet final section is audible
    mix[25 * SR:] *= 1.35
    return np.clip(mix, -1.0, 1.0).astype(np.float32)


def write_wav(path, stereo):
    data = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(data.tobytes())


# ---------------------------------------------------------------------- render
def _frame_bytes(args):
    idx, t, w, h = args
    img = render_frame(t, scene(), w, h)
    return idx, img.tobytes()


def render(out_path: str, w: int = DESIGN_W, h: int = DESIGN_H, workers: int = 2,
           audio: bool = True, start: float = 0.0, end: float = DURATION) -> None:
    import imageio_ffmpeg
    from multiprocessing import Pool

    ff = imageio_ffmpeg.get_ffmpeg_exe()
    n0, n1 = int(round(start * FPS)), int(round(end * FPS))
    total = n1 - n0
    print(f"[render] {total} frames at {w}x{h}", flush=True)

    tmp = os.path.join(os.path.dirname(out_path) or ".", "tmp")
    os.makedirs(tmp, exist_ok=True)
    silent = os.path.join(tmp, "_silent.mp4")

    # frames go straight into FFmpeg as raw RGB: no PNG dump, no disk churn
    proc = subprocess.Popen(
        [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
         "-framerate", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow",
         "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", silent,
         "-loglevel", "error"],
        stdin=subprocess.PIPE)
    jobs = [(i, i / FPS, w, h) for i in range(n0, n1)]
    got = 0
    with Pool(workers) as pool:
        for _idx, buf in pool.imap(_frame_bytes, jobs, chunksize=3):
            proc.stdin.write(buf)
            got += 1
            if got % 60 == 0 or got == total:
                print(f"  {got}/{total}", flush=True)
    proc.stdin.close()
    proc.wait()

    if audio:
        wav = os.path.join(tmp, "_audio.wav")
        write_wav(wav, synth_audio(scene(), (n1 - n0) / FPS))
        subprocess.run([ff, "-y", "-i", silent, "-i", wav, "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                        "-shortest", out_path, "-loglevel", "error"], check=True)
        os.remove(wav)
    else:
        os.replace(silent, out_path)
    if os.path.exists(silent):
        os.remove(silent)
    print(f"[done] {out_path}", flush=True)


def storyboard(times, out_path: str, w: int = DESIGN_W, h: int = DESIGN_H,
               cols: int = 4) -> None:
    sc = scene()
    frames = [render_frame(t, sc, w, h) for t in times]
    tw, th = w // 3, h // 3
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (tw * cols, th * rows), (16, 16, 18))
    d = ImageDraw.Draw(sheet)
    f = font(14)
    for i, (t, im) in enumerate(zip(times, frames)):
        x, y = (i % cols) * tw, (i // cols) * th
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
        d.text((x + 6, y + 4), f"{t:.2f}s", font=f, fill=(255, 240, 200))
    sheet.save(out_path, quality=92)
    print(f"[storyboard] {out_path} ({len(times)} moments)", flush=True)
