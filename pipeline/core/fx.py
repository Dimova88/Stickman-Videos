"""Effects library: particles, impacts, energy, weather.

All effects are deterministic functions of time so any frame can be rendered
in isolation (needed for parallel rendering and for re-renders after edits).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .easing import clamp, ease, lerp, rng, smoothstep, value_noise


# ------------------------------------------------------------------ particles
@dataclass
class Particles:
    """A deterministic particle burst.

    Every particle is described by a seed; position/velocity are analytic so
    seeking to any t is O(n) with no simulation state.
    """

    x: float
    y: float
    t0: float = 0.0
    count: int = 40
    speed: tuple[float, float] = (160.0, 620.0)
    angle: tuple[float, float] = (0.0, 2 * math.pi)
    spread: float = 0.35
    gravity: float = 900.0
    drag: float = 2.2
    life: tuple[float, float] = (0.35, 1.1)
    size: tuple[float, float] = (1.6, 4.4)
    color: tuple = (1.0, 0.78, 0.4)
    color_end: tuple | None = (1.0, 0.25, 0.05)
    glow: float = 1.5
    streak: float = 1.0          # draw velocity-aligned streaks
    depth: float = 1.0
    seed: int = 1
    additive: bool = True
    count_at: callable | None = None

    def _rs(self, i: int):
        r = np.random.default_rng((self.seed * 7919 + i * 104729) & 0x7FFFFFFF)
        return r

    def draw(self, p: "Painter", t: float, st=None):
        age = t - self.t0
        if age < 0:
            return
        st = st or p.st
        for i in range(self.count):
            r = self._rs(i)
            life = lerp(self.life[0], self.life[1], r.random())
            if age > life:
                continue
            u = age / life
            ang = lerp(self.angle[0], self.angle[1], r.random()) + (r.random() - 0.5) * self.spread
            sp = lerp(self.speed[0], self.speed[1], r.random() ** 1.6)
            vx, vy = math.cos(ang) * sp, math.sin(ang) * sp
            k = self.drag
            # analytic drag integration
            if k > 1e-4:
                f = (1 - math.exp(-k * age)) / k
            else:
                f = age
            px = self.x + vx * f
            py = self.y + vy * f + 0.5 * self.gravity * age * age
            vxf = vx * math.exp(-k * age)
            vyf = vy * math.exp(-k * age) + self.gravity * age
            alpha = (1 - u) ** 1.4
            col = np.asarray(self.color, np.float32)
            if self.color_end is not None:
                col = col * (1 - u) + np.asarray(self.color_end, np.float32) * u
            rad = lerp(self.size[0], self.size[1], r.random()) * (1 - 0.55 * u)
            if self.streak > 0:
                tail = 0.012 * self.streak * (1.0 + 2.0 * (1 - u))
                p.line([(px - vxf * tail, py - vyf * tail), (px, py)], rad * 1.5,
                       tuple(col), alpha=alpha, depth=self.depth, additive=self.additive,
                       taper=0.25, glow=self.glow * alpha)
            else:
                p.circle((px, py), rad, tuple(col), alpha=alpha, depth=self.depth,
                         additive=self.additive, glow=self.glow * alpha, glow_color=tuple(col))


@dataclass
class Embers:
    """Ambient floating motes — cheap atmosphere for nearly every shot."""

    x0: float = -1100.0
    x1: float = 1100.0
    y0: float = -600.0
    y1: float = 620.0
    count: int = 90
    speed: float = 26.0
    drift: float = 40.0
    size: tuple = (1.0, 3.0)
    color: tuple = (1.0, 0.55, 0.2)
    glow: float = 1.0
    depth: float = 0.55
    seed: int = 5
    t0: float = 0.0

    def draw(self, p: "Painter", t: float, st=None):
        age = t - self.t0
        if age < 0:
            return
        r = np.random.default_rng(self.seed)
        xs = r.uniform(0, 1, self.count)
        ys = r.uniform(0, 1, self.count)
        ss = r.uniform(0.4, 1.8, self.count)
        ph = r.uniform(0, math.tau, self.count)
        for i in range(self.count):
            x = lerp(self.x0, self.x1, xs[i]) + self.drift * math.sin(age * 0.7 + ph[i])
            span = self.y1 - self.y0
            y = self.y0 + ((ys[i] * span - self.speed * ss[i] * age) % span)
            a = 0.55 + 0.45 * math.sin(age * 3.0 + ph[i] * 3)
            sz = lerp(self.size[0], self.size[1], ss[i] / 1.8)
            p.circle((x, y), sz, self.color, alpha=clamp(a * 0.8), depth=self.depth, additive=True,
                     glow=self.glow * a, glow_color=self.color)


# -------------------------------------------------------------------- impacts
def impact_flash(p, center, t, t0, size=90.0, dur=0.30, color=(1, 0.95, 0.85), spikes=11,
                 depth=1.0, seed=3, core_size=0.30):
    """Starburst + hot core + spikes. The frame-defining 'hit'."""
    age = t - t0
    if age < 0 or age > dur:
        return
    u = age / dur
    r = np.random.default_rng(seed)
    fade = (1 - u) ** 1.3

    # hot core: small, near-white, very brief
    core_r = size * core_size * (0.7 + 0.6 * math.exp(-14 * u)) * (1 - 0.7 * u)
    p.circle(center, core_r, (1, 1, 1), alpha=fade, depth=depth, additive=True)
    p.circle(center, core_r * 1.0, color, alpha=0.0, depth=depth, glow=1.15 * fade, glow_color=color)

    # spikes (manga starburst)
    for i in range(spikes):
        a = r.uniform(0, math.tau)
        ln = size * r.uniform(0.55, 1.7) * ease("expo_out", min(u * 2.2, 1))
        w = size * r.uniform(0.025, 0.07) * fade
        inner = core_r * 0.6
        p.line([(center[0] + math.cos(a) * inner, center[1] + math.sin(a) * inner),
                (center[0] + math.cos(a) * ln, center[1] + math.sin(a) * ln)],
               w * 2, (1, 1, 1), alpha=fade * 0.9, depth=depth, taper=0.05, additive=True)
        p.line([(center[0] + math.cos(a) * inner, center[1] + math.sin(a) * inner),
                (center[0] + math.cos(a) * ln, center[1] + math.sin(a) * ln)],
               w * 2, color, alpha=0.0, depth=depth, taper=0.05, glow=0.5 * fade, glow_color=color)

    # thin expanding halo
    ring_r = size * (0.25 + 1.5 * ease("expo_out", u))
    p.circle(center, ring_r, color, alpha=fade * 0.5, depth=depth, additive=True,
             ring=max(1.0, size * 0.035 * fade))


def shockwave(p, center, t, t0, r0=10.0, r1=520.0, dur=0.55, color=(0.85, 0.93, 1.0),
              width=8.0, depth=1.0, squash=0.55):
    age = t - t0
    if age < 0 or age > dur:
        return
    u = age / dur
    rr = lerp(r0, r1, ease("expo_out", u))
    a = (1 - u) ** 1.7
    p.circle(center, rr, (1, 1, 1), alpha=a * 0.9, depth=depth, additive=True,
             ring=width * (1 - 0.55 * u), glow=a * 0.55, glow_color=color)
    p.circle(center, rr * 0.72, color, alpha=a * 0.30, depth=depth, additive=True,
             ring=width * 0.55)
    p.circle(center, rr * 1.08, color, alpha=a * 0.12, depth=depth, additive=True,
             ring=width * 1.3)


def ground_dust(p, x, y, t, t0, width=520.0, color=(0.55, 0.55, 0.62), count=22, depth=0.95,
                dur=1.2, seed=11):
    age = t - t0
    if age < 0 or age > dur:
        return
    u = age / dur
    r = np.random.default_rng(seed)
    for i in range(count):
        side = -1 if i % 2 else 1
        sp = r.uniform(0.35, 1.0) * width
        off = r.uniform(0, 0.25) * width
        px = x + side * (off + sp * ease("expo_out", u) * 0.5)
        py = y - r.uniform(0, 26) * ease("expo_out", u) - 30 * u * r.uniform(0.3, 1)
        rad = r.uniform(30, 90) * (0.35 + u * 2.0)
        a = (1 - u) ** 1.5 * r.uniform(0.20, 0.45)
        p.blob((px, py), rad, color, alpha=a, depth=depth, soft=1.1)


def speed_lines(p, t, t0, dur=0.22, count=70, inner=0.30, outer=1.1,
                color=(1, 1, 1), alpha=0.55, seed=7):
    """Manga radial speed lines (used on impact frames and big hits)."""
    age = t - t0
    if age < 0 or age > dur:
        return
    u = age / dur
    r = np.random.default_rng(seed)
    w, h = p.w, p.h
    cx, cy = w / 2, h / 2
    diag = math.hypot(w, h)
    a = alpha * (1 - u) ** 1.2 * (0.6 + 0.4 * math.sin(u * math.pi))
    for i in range(count):
        ang = r.uniform(0, math.tau)
        r0 = diag * r.uniform(inner, inner + 0.18)
        r1 = diag * r.uniform(outer * 0.62, outer)
        wd = r.uniform(2.0, 9.0) * (1 + u * 2.5)
        p.line([(cx + math.cos(ang) * r0, cy + math.sin(ang) * r0),
                (cx + math.cos(ang) * r1, cy + math.sin(ang) * r1)],
               wd, color, alpha=a, taper=0.15, additive=True)


def dash_lines(p, t, t0, dur=0.5, y0=-40, y1=40, count=26, color=(1, 1, 1), alpha=0.35, seed=13):
    age = t - t0
    if age < 0 or age > dur:
        return
    u = age / dur
    r = np.random.default_rng(seed)
    for i in range(count):
        y = r.uniform(y0, y1)
        ln = r.uniform(120, 640)
        x = r.uniform(-1200, 1200) - u * 900
        p.line([(x, y), (x + ln, y)], r.uniform(1.2, 3.4), color, alpha=alpha * (1 - u),
               additive=True)


def lightning(p, t, t0, pts, dur=0.18, color=(0.75, 0.9, 1.0), branches=5, seed=21, width=5.0):
    age = t - t0
    if age < 0 or age > dur:
        return
    r = np.random.default_rng(seed)
    flick = 0.55 + 0.45 * math.sin(age * 90)
    jag = _jagged(pts, r, 8)
    p.line(jag, width, color, alpha=0.95 * flick, glow=2.4 * flick, glow_color=color, taper=0.4)
    for b in range(branches):
        i = r.integers(1, max(2, len(jag) - 2))
        a = r.uniform(0.5, 1.6) * (1 if r.random() > 0.5 else -1)
        st = jag[i]
        L = r.uniform(40, 190)
        end = (st[0] + math.cos(a) * L, st[1] + math.sin(a) * L)
        p.line(_jagged([st, end], r, 4), width * 0.45, color, alpha=0.7 * flick,
               glow=1.2 * flick, glow_color=color, taper=0.2)


def _jagged(pts, r, sub):
    out = []
    for i in range(len(pts) - 1):
        a = np.asarray(pts[i], float)
        b = np.asarray(pts[i + 1], float)
        out.append(tuple(a))
        for k in range(1, sub):
            f = k / sub
            mid = a + (b - a) * f
            perp = np.array([-(b - a)[1], (b - a)[0]])
            n = np.linalg.norm(perp) or 1
            out.append(tuple(mid + perp / n * r.normal(0, 1) * np.linalg.norm(b - a) * 0.06))
    out.append(tuple(pts[-1]))
    return out


def slash_arc(p, center, radius, a0, a1, t, t0, dur=0.22, color=(0.85, 0.95, 1.0), width=26.0,
              depth=1.0):
    age = t - t0
    if age < 0 or age > dur:
        return
    u = age / dur
    end = lerp(a0, a1, ease("expo_out", min(u * 1.4, 1)))
    fade = 1 - u
    p.arc(center, radius, a0, end, width * (1 - 0.3 * u), color, alpha=0.85 * fade, depth=depth,
          glow=1.6 * fade, glow_color=color)
    p.arc(center, radius * 0.97, a0, end, width * 0.35, (1, 1, 1), alpha=0.9 * fade, depth=depth,
          glow=1.0 * fade, glow_color=color)


def energy_orb(p, center, radius, t, color=(0.5, 0.8, 1.0), pulse=1.0, depth=1.0, core=(1, 1, 1)):
    pl = 0.85 + 0.15 * math.sin(t * 22.0) * pulse
    p.circle(center, radius * 1.55, color, alpha=0.0, depth=depth, glow=1.8 * pulse, glow_color=color)
    p.circle(center, radius, color, alpha=0.55, depth=depth, additive=True, glow=1.2 * pulse,
             glow_color=color)
    p.circle(center, radius * 0.55 * pl, core, alpha=0.95, depth=depth, additive=True, glow=1.6,
             glow_color=color)


def aura_column(p, x, y0, y1, t, color=(0.4, 0.7, 1.0), width=90.0, seed=5, depth=0.9):
    r = np.random.default_rng(seed)
    for i in range(9):
        off = r.uniform(-1, 1)
        ph = r.uniform(0, 6.28)
        flick = 0.5 + 0.5 * math.sin(t * r.uniform(5, 13) + ph)
        w = width * r.uniform(0.15, 0.5)
        xx = x + off * width * 0.6
        p.line([(xx, y0), (xx + off * 14, lerp(y0, y1, r.uniform(0.5, 1.0)))], w,
               color, alpha=0.18 * flick, depth=depth, additive=True, glow=0.9 * flick,
               glow_color=color, taper=0.15)


def petal_drift(p, t, count=26, color=(1.0, 0.62, 0.78), seed=31, depth=0.7, area=(-1300, 1300, -700, 700)):
    r = np.random.default_rng(seed)
    for i in range(count):
        sx = r.uniform(area[0], area[2] if False else area[1])
        sy = r.uniform(area[2], area[3])
        sp = r.uniform(30, 90)
        ph = r.uniform(0, 6.28)
        x = sx + 60 * math.sin(t * 0.9 + ph) + t * 40
        y = sy + sp * t
        y = ((y + 700) % 1400) - 700
        a = 0.5 + 0.5 * math.sin(t * 3 + ph)
        p.circle((x, y), r.uniform(2.0, 4.2), color, alpha=0.35 + 0.4 * a, depth=depth, additive=False)


def god_rays(p, t, origin=(0.0, -420.0), count=9, spread=1.5, length=2400, color=(1.0, 0.82, 0.55),
             alpha=0.10, seed=17, depth=0.3, flicker=0.35):
    """Light shafts from a source; the anime 'holy backlight'."""
    r = np.random.default_rng(seed)
    base_ang = math.atan2(1.0, 0.0)
    for i in range(count):
        a0 = lerp(-spread, spread, i / max(count - 1, 1)) + r.normal(0, 0.04) + math.pi / 2
        wdt = r.uniform(0.035, 0.13)
        fl = 1.0 - flicker * (0.5 + 0.5 * math.sin(t * r.uniform(0.6, 2.2) + r.uniform(0, 6.28)))
        pts = []
        for k in (-1, 1):
            ang = a0 + wdt * k
            pts.append((origin[0] + math.cos(ang) * length, origin[1] + math.sin(ang) * length))
        tri = [origin, pts[0], pts[1]]
        p.polygon_world(tri, color, alpha=alpha * fl, depth=depth, additive=True, blur=6.0)


def lens_flare(p, t, t0, pos, dur=0.8, scale=1.0, color=(1.0, 0.85, 0.6), streaks=True):
    age = t - t0
    if age < 0 or age > dur:
        return
    u = age / dur
    a = math.sin(math.pi * min(u * 1.0, 1.0)) ** 0.7
    p.circle(pos, 120 * scale, color, alpha=0.0, glow=1.1 * a, glow_color=color)
    p.circle(pos, 26 * scale, (1, 1, 1), alpha=0.9 * a, additive=True)
    p.circle(pos, 26 * scale, color, alpha=0.0, glow=1.6 * a, glow_color=color)
    w, h = p.w, p.h
    cx, cy = w / 2, h / 2
    dx, dy = pos[0] - cx, pos[1] - cy
    for i, (k, sz, al) in enumerate(((-0.45, 0.5, 0.22), (-0.8, 0.28, 0.16), (0.55, 0.34, 0.12), (0.9, 0.6, 0.08))):
        p.circle((cx + dx * k, cy + dy * k), 70 * scale * sz * 2, color, alpha=al * a,
                 additive=True, ring=3.0 * scale, glow=0.0)
    if streaks:
        sx = np.linspace(-1, 1, 60)
        p.line([(pos[0] - w * 0.42, pos[1]), (pos[0] + w * 0.42, pos[1])],
               3.2 * scale, color, alpha=0.5 * a, additive=True, taper=0.1, glow=0.9 * a,
               glow_color=color)


def wind_streaks(p, t, count=40, speed=900.0, color=(0.85, 0.9, 1.0), alpha=0.16, seed=23,
                 depth=0.6, area=(-1500, 1500, -800, 800), dir=(1.0, 0.0)):
    r = np.random.default_rng(seed)
    span = area[1] - area[0]
    for i in range(count):
        y = r.uniform(area[2], area[3])
        sp = speed * r.uniform(0.6, 1.7)
        x = area[0] + ((r.uniform(0, span) + sp * t) % span)
        ln = r.uniform(90, 520)
        p.line([(x, y), (x + ln * dir[0], y + ln * dir[1])], r.uniform(1.0, 2.6), color,
               alpha=alpha * r.uniform(0.4, 1.0), depth=depth, taper=0.2, additive=True)


def rain(p, t, count=260, speed=1500.0, slant=0.24, color=(0.6, 0.7, 0.85), alpha=0.28, seed=29,
         depth=1.1, area=(-1400, 1400, -900, 900)):
    r = np.random.default_rng(seed)
    span = area[3] - area[2]
    for i in range(count):
        x0 = r.uniform(area[0], area[1])
        sp = speed * r.uniform(0.8, 1.3)
        y = area[2] + ((r.uniform(0, span) + sp * t) % span)
        ln = r.uniform(28, 70)
        p.line([(x0, y), (x0 - ln * slant, y + ln)], r.uniform(0.8, 1.8), color,
               alpha=alpha * r.uniform(0.4, 1.0), depth=depth, additive=True)


def dust_motes(p, t, count=40, color=(0.9, 0.85, 0.75), seed=37, depth=0.8):
    r = np.random.default_rng(seed)
    for i in range(count):
        x = r.uniform(-1200, 1200)
        y = r.uniform(-700, 700) + math.sin(t * r.uniform(0.2, 0.6) + r.uniform(0, 6)) * 40
        a = 0.10 + 0.22 * (0.5 + 0.5 * math.sin(t * r.uniform(0.7, 2.0) + r.uniform(0, 6)))
        p.circle((x, y), r.uniform(0.8, 2.4), color, alpha=a, depth=depth, additive=True,
                 glow=0.4 * a, glow_color=color)


def slash_cross(p, center, t, t0, size=420.0, dur=0.35, color=(0.9, 0.95, 1.0), rot=0.5):
    """Two crossed blade slashes — the anime 'X' finish."""
    age = t - t0
    if age < 0 or age > dur:
        return
    u = age / dur
    a = 1 - u
    for k in (rot, -rot, 0.0):
        p.line([(center[0] - math.cos(k) * size, center[1] - math.sin(k) * size),
                (center[0] + math.cos(k) * size, center[1] + math.sin(k) * size)],
               size * 0.055 * a, (1, 1, 1), alpha=0.85 * a, taper=0.05, additive=True)
        p.line([(center[0] - math.cos(k) * size, center[1] - math.sin(k) * size),
                (center[0] + math.cos(k) * size, center[1] + math.sin(k) * size)],
               size * 0.055 * a, color, alpha=0.0, taper=0.05, glow=1.0 * a, glow_color=color)
