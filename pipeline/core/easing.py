"""Timing / interpolation toolkit.

Everything in the film is keyed on time (seconds) and evaluated with explicit
easing curves, the way an animator thinks about spacing.  Two rules:
  * never move linearly if you can help it,
  * every hit gets anticipation + a snap + a settle.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

import numpy as np


# ---------------------------------------------------------------- scalar math
def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def inv_lerp(a: float, b: float, v: float) -> float:
    if abs(b - a) < 1e-9:
        return 0.0
    return (v - a) / (b - a)


def smoothstep(t: float) -> float:
    t = clamp(t)
    return t * t * (3 - 2 * t)


def smootherstep(t: float) -> float:
    t = clamp(t)
    return t * t * t * (t * (t * 6 - 15) + 10)


def ease_in(t: float, p: float = 2.0) -> float:
    return clamp(t) ** p


def ease_out(t: float, p: float = 2.0) -> float:
    return 1 - (1 - clamp(t)) ** p


def ease_out_expo(t: float) -> float:
    t = clamp(t)
    return 1.0 if t >= 1 else 1 - 2 ** (-10 * t)


def ease_in_expo(t: float) -> float:
    t = clamp(t)
    return 0.0 if t <= 0 else 2 ** (10 * (t - 1))


def ease_in_out(t: float) -> float:
    t = clamp(t)
    return 3 * t * t - 2 * t * t * t


def ease_out_back(t: float, s: float = 1.9) -> float:
    t = clamp(t) - 1
    return t * t * ((s + 1) * t + s) + 1


def ease_out_elastic(t: float, amp: float = 1.0, period: float = 0.36) -> float:
    t = clamp(t)
    if t in (0.0, 1.0):
        return t
    s = period / (2 * math.pi) * math.asin(1 / max(amp, 1e-6))
    return amp * 2 ** (-10 * t) * math.sin((t - s) * (2 * math.pi) / period) + 1


def cubic_bezier(x1: float, y1: float, x2: float, y2: float) -> Callable[[float], float]:
    """CSS-style cubic-bezier easing."""

    def f(t: float) -> float:
        t = clamp(t)
        # Newton solve for the parameter, robust enough for animation curves.
        u = t
        for _ in range(6):
            mt = 1 - u
            bx = 3 * mt * mt * u * x1 + 3 * mt * u * u * x2 + u ** 3
            dx = 3 * mt * mt * x1 + 6 * mt * u * (x2 - x1) + 3 * u * u * (1 - x2)
            if abs(dx) < 1e-6:
                break
            u -= (bx - t) / dx
            u = clamp(u)
        mt = 1 - u
        return 3 * mt * mt * u * y1 + 3 * mt * u * u * y2 + u ** 3

    return f


# Common anime-feel curves, named once and reused everywhere.
SNAP = cubic_bezier(0.16, 1.0, 0.3, 1.0)        # fast out, long settle
WHIP = cubic_bezier(0.7, 0.0, 0.84, 0.0)        # accelerate hard, stop dead
IMPACT = cubic_bezier(0.05, 0.9, 0.1, 1.0)      # instant hit, resolve
HOLD = cubic_bezier(0.0, 0.0, 1.0, 1.0)         # constant (for steppy animation)
SOFT = cubic_bezier(0.4, 0.0, 0.2, 1.0)         # gentle in/out

EASINGS: dict[str, Callable[[float], float]] = {
    "linear": lambda t: clamp(t),
    "in": ease_in,
    "out": ease_out,
    "inout": ease_in_out,
    "smooth": smoothstep,
    "smoother": smootherstep,
    "snap": SNAP,
    "whip": WHIP,
    "impact": IMPACT,
    "hold": HOLD,
    "soft": SOFT,
    "expo_out": ease_out_expo,
    "expo_in": ease_in_expo,
    "back": ease_out_back,
    "elastic": ease_out_elastic,
}


def ease(name: str | Callable[[float], float], t: float) -> float:
    if callable(name):
        return name(clamp(t))
    return EASINGS.get(name, smoothstep)(t)


# ------------------------------------------------------------------- keyframes
@dataclass
class Key:
    t: float
    v: float | Sequence[float]
    ease: str | Callable[[float], float] = "smooth"


@dataclass
class Track:
    """A scalar (or vector) channel over time with per-segment easing.

    Repeated calls are cheap: keys are sorted once and the last segment index is
    cached, so evaluating thousands of frames stays in the fast path.
    """

    keys: list[Key] = field(default_factory=list)
    _idx: int = -1

    def add(self, t: float, v, ease_name="smooth") -> "Track":
        self.keys.append(Key(t, v, ease_name))
        self.keys.sort(key=lambda k: k.t)
        self._idx = -1
        return self

    def at(self, t: float):
        ks = self.keys
        if not ks:
            raise ValueError("empty track")
        if len(ks) == 1 or t <= ks[0].t:
            return ks[0].v
        if t >= ks[-1].t:
            return ks[-1].v
        i = self._idx
        if not (0 <= i < len(ks) - 1 and ks[i].t <= t <= ks[i + 1].t):
            lo, hi = 0, len(ks) - 1
            while lo < hi - 1:
                mid = (lo + hi) // 2
                if ks[mid].t <= t:
                    lo = mid
                else:
                    hi = mid
            i = lo
            self._idx = i
        a, b = ks[i], ks[i + 1]
        u = ease(b.ease, inv_lerp(a.t, b.t, t))
        if isinstance(a.v, (int, float)) and isinstance(b.v, (int, float)):
            return lerp(float(a.v), float(b.v), u)
        return tuple(lerp(float(x), float(y), u) for x, y in zip(a.v, b.v))  # type: ignore[arg-type]


# ----------------------------------------------------------------- noise / fx
def value_noise(t: float, seed: int = 0, octaves: int = 3) -> float:
    """Smooth 1-D noise in [-1, 1] — handheld camera, flicker, breathing."""
    total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
    for o in range(octaves):
        x = (t * freq + seed * 17.13 + o * 31.7)
        i = math.floor(x)
        f = x - i
        f = f * f * (3 - 2 * f)

        def h(n: int) -> float:
            n = (n * 374761393 + seed * 668265263) & 0xFFFFFFFF
            n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
            return ((n ^ (n >> 16)) & 0xFFFF) / 32767.5 - 1.0

        total += lerp(h(i), h(i + 1), f) * amp
        norm += amp
        amp *= 0.5
        freq *= 2.0
    return total / norm


def fbm(t: float, seed: int = 0, octaves: int = 4) -> float:
    return value_noise(t, seed, octaves)


@dataclass
class Shake:
    """Camera shake as a decaying sum of sine layers — reads as 'impact'."""
    amp: float = 24.0
    decay: float = 9.0
    freq: float = 34.0
    rot_amp: float = 0.012
    seed: int = 1
    _t0: float = 0.0

    def trigger(self, t0: float) -> "Shake":
        self._t0 = t0
        return self

    def at(self, t: float) -> tuple[float, float, float]:
        dt = t - self._t0
        if dt < 0:
            return 0.0, 0.0, 0.0
        env = math.exp(-self.decay * dt)
        if env < 1e-3:
            return 0.0, 0.0, 0.0
        n1 = value_noise(t * self.freq, self.seed)
        n2 = value_noise(t * self.freq * 1.13, self.seed + 7)
        n3 = value_noise(t * self.freq * 0.7, self.seed + 13)
        return self.amp * env * n1, self.amp * env * n2, self.rot_amp * env * n3


def pingpong(x: float) -> float:
    x = x % 2.0
    return 1 - abs(1 - x)


def rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)
