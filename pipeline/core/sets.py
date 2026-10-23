"""Set design: reusable, parallax-aware environments.

Every builder takes (painter, t, ...) and paints in world space at a given
depth so the camera produces real parallax.  Palettes are per-scene so the same
geometry can be a warm temple or a frozen ruin.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .easing import clamp, ease, lerp, smoothstep, value_noise
from . import fx


@dataclass
class Palette:
    sky_top: tuple = (0.012, 0.016, 0.035)
    sky_bottom: tuple = (0.10, 0.07, 0.14)
    haze: tuple = (0.28, 0.22, 0.34)
    far: tuple = (0.055, 0.06, 0.10)
    mid: tuple = (0.028, 0.032, 0.055)
    near: tuple = (0.008, 0.009, 0.014)
    accent: tuple = (1.0, 0.62, 0.24)
    accent2: tuple = (0.45, 0.78, 1.0)
    moon: tuple = (0.95, 0.95, 1.0)


def sky(p, pal: Palette, top=None, bottom=None, z_top=-0.02):
    """Full-frame vertical gradient (drawn in screen space)."""
    top = top or pal.sky_top
    bottom = bottom or pal.sky_bottom
    p.poly([(-400, -400), (p.w + 400, -400), (p.w + 400, p.h + 400), (-400, p.h + 400)],
           None, gradient=(top, bottom))


def stars(p, t, count=170, seed=41, depth=0.25, color=(0.85, 0.9, 1.0), brightness=1.0):
    r = np.random.default_rng(seed)
    for i in range(count):
        x = r.uniform(-2600, 2600)
        y = r.uniform(-1500, -260)
        sz = r.uniform(0.6, 1.9)
        tw = 0.55 + 0.45 * math.sin(t * r.uniform(0.5, 2.4) + r.uniform(0, 6.28))
        p.circle((x, y), sz, color, alpha=clamp(0.55 * tw * brightness), depth=depth, additive=True,
                 glow=0.35 * tw * brightness, glow_color=color)


def moon(p, pos=(560.0, -430.0), r=118.0, t=0.0, pal: Palette | None = None, depth=0.3, halo=1.0):
    pal = pal or Palette()
    p.circle(pos, r * 3.4, pal.moon, alpha=0.0, depth=depth, glow=0.45 * halo, glow_color=pal.moon)
    p.circle(pos, r, pal.moon, alpha=0.93, depth=depth, additive=False,
             glow=0.30 * halo, glow_color=pal.moon)
    # cold shadow inside the disc for a photographic feel
    p.circle((pos[0] + r * 0.22, pos[1] + r * 0.12), r * 0.98, (0.72, 0.76, 0.86), alpha=0.10, depth=depth)


def clouds(p, t, pal: Palette, depth=0.32, count=7, y0=-560.0, seed=43, color=None,
           speed=10.0, alpha=0.5):
    r = np.random.default_rng(seed)
    col = color or (pal.haze[0] * 0.9, pal.haze[1] * 0.85, pal.haze[2] * 1.0)
    for i in range(count):
        y = y0 + i * 70 + r.uniform(-40, 40)
        x = -2800 + ((r.uniform(0, 5600) + t * speed * r.uniform(0.6, 1.6)) % 6200)
        w = r.uniform(600, 1800)
        for k in range(7):
            p.blob((x + r.uniform(-w / 2, w / 2), y + r.uniform(-40, 40)),
                   r.uniform(90, 260), col, alpha=alpha * r.uniform(0.25, 0.6), depth=depth, soft=0.9)


def mountains(p, t, pal: Palette, depth=0.4, seed=47, color=None, base_y=90.0, amp=260.0,
              freq=0.0022, jag=0.45, layers=1, alpha=1.0):
    col = color or pal.far
    r = np.random.default_rng(seed)
    offs = r.uniform(0, 1000, 4)
    for L in range(layers):
        pts = []
        y0 = base_y - L * 55
        for i in range(0, 61):
            x = -3000 + i * 100
            h = 0.0
            for o in range(4):
                h += amp * (0.55 ** (o + 1)) * value_noise(x * freq * (2 ** o) + offs[o] + L * 13, seed + o)
            h = abs(h)
            pts.append((x, y0 - h))
        pts += [(3000, 2000), (-3000, 2000)]
        p.polygon_world(pts, col, alpha=alpha, depth=depth + L * 0.01)


def mountains_ridge(p, t, color, depth=0.4, seed=47, base_y=90.0, amp=260.0, freq=0.0022,
                    width=3200.0, bottom=2000.0, rim=None, rim_w=2.0, rim_a=0.35, rim_glow=0.25):
    r = np.random.default_rng(seed)
    offs = r.uniform(0, 1000, 4)
    pts = []
    n = 80
    for i in range(n + 1):
        x = -width + (2 * width) * i / n
        h = 0.0
        for o in range(4):
            h += amp * (0.5 ** (o + 1)) * value_noise(x * freq * (2 ** o) + offs[o], seed + o)
        pts.append((x, base_y - abs(h)))
    ridge = pts[:]
    pts += [(width, bottom), (-width, bottom)]
    p.polygon_world(pts, color, alpha=1.0, depth=depth)
    if rim is not None:
        p.line(ridge, rim_w, rim, alpha=rim_a, depth=depth - 0.001, glow=rim_glow, glow_color=rim)


def fog_band(p, t, y, thickness=180.0, color=(0.25, 0.28, 0.4), alpha=0.22, depth=0.45, seed=53,
             width=6000.0, speed=18.0):
    r = np.random.default_rng(seed)
    for i in range(9):
        x = -width + ((r.uniform(0, 2 * width) + t * speed * r.uniform(0.5, 1.5)) % (2 * width))
        p.blob((x, y + r.uniform(-thickness / 2, thickness / 2)), r.uniform(thickness * 1.4, thickness * 3.2),
               color, alpha=alpha * r.uniform(0.3, 0.8), depth=depth, soft=0.75)


def ground(p, pal: Palette, y=210.0, color=None, depth=1.0, refl=None, wet=False,
           detail=1.0, light_x=0.0, light_col=None):
    """Horizon ground plane with fog, perspective slabs and a light pool."""
    col = np.asarray(color or pal.near, np.float32)
    haze = np.asarray(pal.haze, np.float32)
    lit = col * 0.9 + haze * 0.16
    deep = col * 0.5
    p.polygon_world([(-6000, y), (6000, y), (6000, 6000), (-6000, 6000)], None, depth=depth,
                    gradient=(tuple(lit), tuple(deep)))
    # light pool under the main light source
    if light_col is not None:
        p.blob((light_x, y + 70), 300, light_col, alpha=0.10, depth=depth - 0.01, soft=1.6,
               additive=True)
    # perspective slab lines (receding)
    if detail > 0:
        for i in range(7):
            yy = y + (i ** 1.7) * 22 * detail
            p.line([(-6000, yy), (6000, yy)], 0.8 + i * 0.5,
                   tuple(np.asarray(pal.haze) * 0.55), alpha=0.16 + 0.03 * i, depth=depth,
                   glow=0.0)
        for i in range(-9, 10):
            x = i * 260
            p.line([(x * 0.25, y), (x * 2.4, 4000)], 0.9, tuple(np.asarray(pal.haze) * 0.5),
                   alpha=0.10, depth=depth)
    # mist hugging the ground so the plane melts into the background
    for i in range(7):
        p.blob((-2400 + i * 800, y + 24 + (i % 3) * 14), 460, tuple(haze * 0.95), alpha=0.20,
               depth=depth - 0.02, soft=0.85)
    for i in range(4):
        p.blob((-1800 + i * 1200, y + 6), 900, tuple(haze * 0.75), alpha=0.16,
               depth=depth - 0.03, soft=0.7)
    # rim of light on the horizon
    p.line([(-6000, y), (6000, y)], 2.0, tuple(np.asarray(pal.accent) * 0.7), alpha=0.35,
           depth=depth, glow=0.3, glow_color=pal.accent)


def wet_reflection(p, sources: Sequence[tuple[float, float, float, tuple]], y=210.0, depth=1.0,
                   height=520.0, t=0.0, seed=59):
    """Banded vertical reflections of glowing things above the waterline."""
    r = np.random.default_rng(seed)
    for (x, sy, w, col) in sources:
        for i in range(16):
            k = i / 16
            yy = y + k * height * r.uniform(0.4, 1.0)
            wob = math.sin(t * 1.6 + i * 0.9) * 12 * k + r.normal(0, 3)
            ww = w * (0.7 + 1.4 * k) * r.uniform(0.7, 1.25)
            a = (1 - k) ** 1.8 * 0.28 * r.uniform(0.5, 1.0)
            p.line([(x + wob - ww / 2, yy), (x + wob + ww / 2, yy)], 2.4 + 5 * k, col,
                   alpha=a, depth=depth, additive=True, taper=0.3)


def pillars(p, t, pal: Palette, depth=1.0, count=7, spacing=430.0, x0=-1290.0, top=-780.0,
            bottom=300.0, w=64.0, color=None, lit=None, light_x=0.0):
    col = color or pal.near
    for i in range(count):
        x = x0 + i * spacing
        ww = w * (1.0 + 0.06 * (i % 2))
        p.polygon_world([(x - ww / 2, top), (x + ww / 2, top), (x + ww / 2, bottom), (x - ww / 2, bottom)],
                        col, depth=depth)
        # capital + base
        p.polygon_world([(x - ww * 0.75, top), (x + ww * 0.75, top), (x + ww * 0.75, top + 34),
                         (x - ww * 0.75, top + 34)], tuple(np.array(col) * 1.35), depth=depth)
        p.polygon_world([(x - ww * 0.8, bottom - 30), (x + ww * 0.8, bottom - 30), (x + ww * 0.8, bottom),
                         (x - ww * 0.8, bottom)], tuple(np.array(col) * 1.2), depth=depth)
        # rim from the light side
        if lit is not None:
            side = 1 if x > light_x else -1
            p.line([(x + side * ww / 2, top), (x + side * ww / 2, bottom)], 2.6, lit, alpha=0.5,
                   depth=depth, glow=0.35, glow_color=lit)


def lantern(p, x, y, r=26.0, t=0.0, color=(1.0, 0.55, 0.22), depth=0.85, sway=0.0, seed=0, glow=1.4,
            cord=90.0):
    ph = seed * 1.7
    sx = math.sin(t * 1.1 + ph) * sway
    cx, cy = x + sx, y + abs(sx) * 0.25
    if cord > 0:
        p.line([(x, y - cord - r), (cx, cy - r)], 1.6, (0.05, 0.05, 0.06), alpha=0.9, depth=depth)
    flick = 0.88 + 0.12 * math.sin(t * 9 + ph) * math.sin(t * 3.3 + ph * 2)
    p.circle((cx, cy), r * 1.0, color, alpha=0.9 * flick, depth=depth)
    p.circle((cx, cy), r * 1.55, color, alpha=0.0, depth=depth, glow=glow * flick, glow_color=color)
    p.circle((cx, cy), r * 0.55, (1.0, 0.92, 0.75), alpha=0.55 * flick, depth=depth, additive=True)
    # top/bottom caps
    p.line([(cx - r * 0.45, cy - r * 0.95), (cx + r * 0.45, cy - r * 0.95)], 4.0, (0.06, 0.04, 0.03),
           depth=depth)
    p.line([(cx - r * 0.4, cy + r * 0.92), (cx + r * 0.4, cy + r * 0.92)], 3.0, (0.06, 0.04, 0.03),
           depth=depth)


def torii(p, t, pal: Palette, x=0.0, y=240.0, scale=1.0, depth=1.05, color=(0.07, 0.03, 0.03),
          light=None, open_glow=0.0, glow_color=None):
    """A massive gate. `open_glow` 0..1 fills the doorway with light."""
    s = scale
    h = 620 * s
    wid = 300 * s
    pw = 46 * s

    if open_glow > 0:
        gc = glow_color or pal.accent
        # the doorway: layered soft light from the threshold upward
        for i in range(6):
            k = i / 5
            p.blob((x, y - h * (0.05 + 0.75 * k)), wid * (0.60 - 0.32 * k), gc,
                   alpha=0.11 * open_glow * (1 - 0.5 * k), depth=depth - 0.01, additive=True,
                   soft=1.75)
        p.blob((x, y - 10), wid * 0.62, gc, alpha=0.26 * open_glow, depth=depth - 0.015,
               additive=True, soft=2.1)
        # vertical shafts fanning up out of the doorway
        for i in range(11):
            a = -math.pi / 2 + (i - 5) * 0.105
            ln = 2200 * s
            p.line([(x + math.cos(a) * 40, y - h * 0.15), (x + math.cos(a) * ln, y - h * 0.15 + math.sin(a) * ln)],
                   46 * s, gc, alpha=0.030 * open_glow, depth=depth - 0.02, additive=True, taper=2.2)
    # legs (slightly tapered, leaning in)
    for sgn in (-1, 1):
        top_x = x + sgn * wid * 0.62
        bot_x = x + sgn * wid * 0.86
        p.polygon_world([(top_x - pw / 2, y - h), (top_x + pw / 2, y - h),
                         (bot_x + pw * 0.62, y + 20), (bot_x - pw * 0.62, y + 20)], color, depth=depth)
        if light is not None:
            side = 1 if sgn > 0 else -1
            p.line([(top_x + side * pw / 2, y - h), (bot_x + side * pw * 0.6, y + 20)], 3.0, light,
                   alpha=0.45, depth=depth, glow=0.5, glow_color=light)
    # lintels
    p.polygon_world([(x - wid * 1.12, y - h - 34), (x + wid * 1.12, y - h - 34),
                     (x + wid * 1.12, y - h + 10), (x - wid * 1.12, y - h + 10)], color, depth=depth)
    p.polygon_world([(x - wid * 0.95, y - h + 46), (x + wid * 0.95, y - h + 46),
                     (x + wid * 0.95, y - h + 74), (x - wid * 0.95, y - h + 74)], color, depth=depth)
    p.polygon_world([(x - wid * 0.06, y - h + 12), (x + wid * 0.06, y - h + 12),
                     (x + wid * 0.06, y - h + 46), (x - wid * 0.06, y - h + 46)], color, depth=depth)
    if light is not None:
        p.line([(x - wid * 1.12, y - h - 34), (x + wid * 1.12, y - h - 34)], 3.2, light, alpha=0.6,
               depth=depth, glow=0.7, glow_color=light)


def stairs(p, t, y=250.0, depth=1.0, steps=9, w0=760.0, rise=34.0, run=64.0, color=(0.035, 0.035, 0.05),
           light=None, alpha=1.0):
    """Perspective stone stairs leading up to the gate."""
    for i in range(steps):
        yy = y + i * rise
        ww = w0 + i * run * 1.6
        p.polygon_world([(-ww, yy), (ww, yy), (ww, yy + rise), (-ww, yy + rise)], color, depth=depth, alpha=alpha)
        if light is not None:
            p.line([(-ww, yy), (ww, yy)], 2.0, light, alpha=0.35, depth=depth, glow=0.3, glow_color=light)
        else:
            p.line([(-ww, yy), (ww, yy)], 1.4, tuple(np.array(color) * 2.6), alpha=0.5, depth=depth)


def temple_wall(p, t, pal: Palette, depth=0.92, y=250.0, windows=5, spacing=380.0, color=None,
                glow=(1.0, 0.6, 0.25), lit_amount=0.0):
    col = color or pal.near
    p.polygon_world([(-3000, -800), (3000, -800), (3000, y), (-3000, y)], col, depth=depth)
    for i in range(windows):
        x = (i - (windows - 1) / 2) * spacing
        w, h = 96, 150
        p.polygon_world([(x - w / 2, y - 330), (x + w / 2, y - 330), (x + w / 2, y - 330 + h),
                         (x - w / 2, y - 330 + h)], tuple(np.array(col) * 1.6), depth=depth)
        if lit_amount > 0:
            flick = 0.8 + 0.2 * math.sin(t * 4.0 + i * 1.7)
            p.polygon_world([(x - w / 2 + 6, y - 324), (x + w / 2 - 6, y - 324),
                             (x + w / 2 - 6, y - 330 + h - 6), (x - w / 2 + 6, y - 330 + h - 6)],
                            glow, alpha=0.55 * lit_amount * flick, depth=depth, additive=True, blur=8)


def bamboo(p, t, depth=1.15, count=26, x0=-1600.0, x1=1600.0, seed=61, color=(0.02, 0.03, 0.03),
           sway=1.0, top=-900.0, bottom=600.0):
    r = np.random.default_rng(seed)
    for i in range(count):
        x = r.uniform(x0, x1)
        w = r.uniform(7, 18)
        ph = r.uniform(0, 6.28)
        bend = math.sin(t * 0.9 + ph) * 26 * sway
        p.line([(x, bottom), (x + bend * 0.4, (bottom + top) / 2), (x + bend, top)],
               w, color, alpha=0.95, depth=depth)
        for k in range(5):
            yy = lerp(bottom, top, (k + 1) / 6)
            side = 1 if k % 2 else -1
            p.line([(x + bend * (k / 6), yy), (x + bend * (k / 6) + side * r.uniform(70, 190), yy - r.uniform(10, 60))],
                   r.uniform(1.5, 3.5), color, alpha=0.8, depth=depth, taper=0.2)


def skyline(p, t, color, depth=0.55, seed=67, y=250.0, width=3400.0, count=26, hmin=90, hmax=340):
    r = np.random.default_rng(seed)
    xs = np.linspace(-width, width, count)
    for i, x in enumerate(xs):
        w = width / count * r.uniform(0.7, 1.15)
        h = r.uniform(hmin, hmax)
        p.polygon_world([(x - w / 2, y), (x - w / 2, y - h), (x + w / 2, y - h), (x + w / 2, y)], color,
                        depth=depth)
        if r.random() > 0.55:
            p.polygon_world([(x - w * 0.12, y - h), (x + w * 0.12, y - h), (x + w * 0.05, y - h - 60),
                             (x - w * 0.05, y - h - 60)], color, depth=depth)
        # a few lit windows
        for k in range(int(r.integers(0, 5))):
            wx = x + r.uniform(-w * 0.35, w * 0.35)
            wy = y - r.uniform(20, h - 20)
            p.polygon_world([(wx, wy), (wx + 7, wy), (wx + 7, wy + 10), (wx, wy + 10)],
                            (1.0, 0.72, 0.35), alpha=r.uniform(0.15, 0.5), depth=depth, additive=True)


def falling_leaves(p, t, count=20, color=(1.0, 0.55, 0.65), seed=71, depth=0.9,
                   area=(-1400, 1400, -800, 800), speed=(40, 110)):
    r = np.random.default_rng(seed)
    for i in range(count):
        x0 = r.uniform(area[0], area[1])
        sp = r.uniform(*speed)
        ph = r.uniform(0, 6.28)
        y = area[2] + ((r.uniform(0, area[3] - area[2]) + sp * t) % (area[3] - area[2]))
        x = x0 + 70 * math.sin(t * 0.8 + ph) + 30 * math.sin(t * 2.1 + ph)
        rot = t * r.uniform(1, 3) + ph
        L = r.uniform(6, 13)
        dx, dy = math.cos(rot) * L, math.sin(rot) * L * 0.5
        p.line([(x - dx, y - dy), (x + dx, y + dy)], r.uniform(2.4, 4.2), color,
               alpha=r.uniform(0.35, 0.8), depth=depth)


def vignette_world(p, t, color=(0.0, 0.0, 0.0), alpha=0.5):
    """Soft dark corners painted into the scene (extra depth on tight shots)."""
    for side in (-1, 1):
        for k in range(3):
            p.blob((side * (900 + k * 300), 620 - k * 120), 520 + k * 200, color, alpha=alpha * 0.22,
                   depth=2.0, soft=0.8)
