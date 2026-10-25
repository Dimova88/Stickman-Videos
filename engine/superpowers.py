"""Superpowers: the fight stops being a sword fight and becomes a *myth*.

Every effect in here is **procedural geometry**, not an asset: fractal lightning
from midpoint displacement, residual images of the body's own poses, a beam
built from a sine wave travelling along its own axis, rocks torn out of the
floor, and a white-hot core. That is deliberate — the film has to stay 100 %
original and it has to stay *cheap*: a superpower that needs a texture sheet is a
superpower that cannot be regenerated at a different resolution.

The rule that keeps it watchable: **the power is drawn from the body**, not
pasted near it. Lightning leaves the shoulder it was issued from, the afterimages
are previous poses of that same fighter, the beam starts at the hand that threw
it, and the rocks levitate around the feet that are standing on them.
"""
from __future__ import annotations

import math
import random

# ---------------------------------------------------------------- lightning
def fractal_lightning(p1, p2, generations: int = 4, max_offset: float = 26.0,
                      seed: int = 0, branch: float = 0.26):
    """Midpoint-displacement bolts between two points.

    Returns a list of polylines, the first being the main arc and the rest its
    forks. Deterministic for a given seed, so the arc that leaves the shoulder on
    frame 400 is the same arc on a re-render.
    """
    rng = random.Random(seed)
    bolts = [[tuple(p1), tuple(p2)]]
    for gen in range(generations):
        out = []
        offset = max_offset / (1.85 ** gen)
        for bolt in bolts:
            path = [bolt[0]]
            for i in range(len(bolt) - 1):
                ax, ay = bolt[i]
                bx, by = bolt[i + 1]
                dx, dy = bx - ax, by - ay
                length = math.hypot(dx, dy) + 1e-6
                nx, ny = -dy / length, dx / length
                disp = rng.uniform(-offset, offset)
                mid = ((ax + bx) * 0.5 + nx * disp, (ay + by) * 0.5 + ny * disp)
                path.extend([mid, (bx, by)])
                if gen < 2 and rng.random() < branch:
                    ang = math.atan2(dy, dx) + rng.uniform(-0.7, 0.7)
                    arm = length * rng.uniform(0.35, 0.7)
                    out.append([mid, (mid[0] + math.cos(ang) * arm,
                                      mid[1] + math.sin(ang) * arm)])
            out.insert(0, path)
        bolts = out
    return bolts


def draw_lightning(cv, p1, p2, seed: int, power: float = 1.0,
                   colour=(150, 226, 255), core=(255, 255, 255)) -> None:
    """A bolt with a hot core and a wide cold halo."""
    u = cv.unit()
    if power <= 0.02:
        return
    bolts = fractal_lightning(p1, p2, generations=4,
                              max_offset=30.0 * power, seed=seed)
    for i, bolt in enumerate(bolts):
        pts = [cv.wp(p) for p in bolt]
        main = i == 0
        cv.polyline(pts, max(2.0, (5.0 if main else 2.4) * u * power),
                    colour, alpha=int(120 * power))
        cv.polyline(pts, max(1.0, (2.0 if main else 1.2) * u * power),
                    core, alpha=int(210 * power))


# -------------------------------------------------------------------- aura
def aura_ring(cv, centre, radius: float, t: float, power: float = 1.0,
              colour=(96, 220, 255)) -> None:
    """The pulsing shell around a body that has awakened.

    A ring, not a cloud: it has to sit *on* the silhouette, so the figure inside
    it stays readable. Three harmonics give a breathing edge without any noise
    texture.
    """
    u = cv.unit()
    cx, cy = centre
    pts = []
    n = 42
    for i in range(n):
        a = i / n * math.tau
        wob = (math.sin(a * 3.0 + t * 7.0) * 0.045
               + math.sin(a * 5.0 - t * 4.3) * 0.028
               + math.sin(a * 2.0 + t * 2.1) * 0.05)
        r = radius * (1.0 + wob) * power
        pts.append(cv.wp((cx + math.cos(a) * r * 0.62, cy + math.sin(a) * r)))
    cv.polyline(pts + [pts[0]], max(2.0, 3.2 * u), colour, alpha=int(120 * power))
    cv.polyline(pts + [pts[0]], max(1.0, 1.4 * u), (240, 252, 255),
                alpha=int(70 * power))


# ------------------------------------------------------------------- beam
def beam_geometry(origin, target, frame_idx: int, radius: float = 34.0,
                  segments: int = 24) -> dict:
    """The plasma column between a hand and the thing it is erasing.

    The core is a straight hot bar; the shell is a travelling sine wave, which is
    what makes a static polygon read as *flowing* energy.
    """
    ox, oy = origin
    tx, ty = target
    dx, dy = tx - ox, ty - oy
    dist = math.hypot(dx, dy) + 1e-5
    nx, ny = -dy / dist, dx / dist
    upper, lower = [], []
    for i in range(segments + 1):
        u = i / segments
        px, py = ox + dx * u, oy + dy * u
        wave = math.sin(u * 16.0 - frame_idx * 1.5) * radius * 0.20
        w = radius * (0.62 + 0.38 * math.sin(u * math.pi)) + wave
        upper.append((px + nx * w, py + ny * w))
        lower.append((px - nx * w, py - ny * w))
    return {
        "shell": upper + list(reversed(lower)),
        "core": radius * 0.45,
        "origin": (ox, oy),
        "target": (tx, ty),
        "impact_radius": radius * 2.2 + math.cos(frame_idx * 2.0) * 8.0,
    }


def draw_beam(cv, origin, target, frame_idx: int, power: float = 1.0,
              radius: float = 30.0, colour=(120, 226, 255)) -> None:
    u = cv.unit()
    if power <= 0.02:
        return
    # the ray does not stop at the man: it keeps going, so what the audience
    # sees is a *beam* with a body stuck in the near third of it, not a white
    # bulge pressed against a chest
    ox, oy = float(origin[0]), float(origin[1])
    dx, dy = target[0] - ox, target[1] - oy
    dist = math.hypot(dx, dy) + 1e-5
    far = (ox + dx / dist * (dist + radius * 3.4),
           oy + dy / dist * (dist + radius * 3.4))
    g = beam_geometry(origin, far, frame_idx, radius=radius * power)
    shell = [cv.wp(p) for p in g["shell"]]
    cv.polygon(shell, colour, alpha=int(52 * power))
    cv.polyline(shell + [shell[0]], max(1.5, 2.0 * u), (214, 246, 255),
                alpha=int(120 * power))
    # the core: a straight bar of white, thin enough to stay a bar
    p0, p1 = cv.wp(g["origin"]), cv.wp(g["target"])
    cv.line(p0, p1, max(6.0, g["core"] * u * 1.1), (200, 244, 255), alpha=120)
    cv.line(p0, p1, max(3.0, g["core"] * u * 0.55), (255, 255, 255), alpha=240)
    cv.circle(p0, max(4.0, 13.0 * u * power), (255, 255, 255), fill=(255, 255, 255))
    # the dome where it lands, sized to the body it is burning, not to the beam
    ix = cv.wp((dx * 0.72 + ox, dy * 0.72 + oy))
    cv.circle(ix, max(6.0, g["impact_radius"] * u * 0.62), (200, 244, 255),
              fill=(228, 250, 255), alpha=110)


def energy_lance(cv, hilt, angle: float, length: float, glow: float = 1.0,
                 colour=(150, 240, 255)) -> None:
    """A weapon made of light: no handle, no edge — a shaft with a bright tip."""
    u = cv.unit()
    ca, sa = math.cos(angle), math.sin(angle)
    tip = (hilt[0] + ca * length, hilt[1] + sa * length)
    back = (hilt[0] - ca * length * 0.16, hilt[1] - sa * length * 0.16)
    p0, p1, pb = cv.wp(hilt), cv.wp(tip), cv.wp(back)
    w = max(2.0, 5.0 * u * (0.7 + 0.5 * glow))
    # halo, then the shaft, then the hot line down the middle of it: three
    # passes is what makes a line read as *made of light* instead of as a stick
    cv.line(p0, p1, w * 5.0, colour, alpha=34)
    cv.line(p0, p1, w * 2.6, colour, alpha=88)
    cv.line(p0, p1, w * 1.5, (216, 250, 255), alpha=190)
    cv.line(p0, p1, max(2.0, w * 0.55), (255, 255, 255), alpha=245)
    cv.line(pb, p0, max(2.0, w * 0.9), (120, 208, 240), alpha=200)
    # the point: a barb of light and two sparks coming off it
    cv.circle(p1, max(2.0, w * 1.6), (150, 240, 255), alpha=150)
    cv.circle(p1, max(1.0, w * 0.8), (255, 255, 255), fill=(255, 255, 255))
    for i in range(2):
        a = angle + math.pi * (0.55 + 0.5 * i) + 0.2 * math.sin(glow * 6.0 + i)
        sp = (tip[0] + math.cos(a) * length * 0.10,
              tip[1] + math.sin(a) * length * 0.10)
        cv.line(cv.wp(sp), p1, max(1.0, w * 0.35), (235, 252, 255), alpha=120)


# --------------------------------------------------------------- afterimages
def afterimages(track, t: float, pose_fn, count: int = 5, spacing: float = 1 / 24.0):
    """The last few poses of one fighter, to be drawn as neon residue.

    A flash-step is not a teleport effect, it is a *continuity* effect: the eye
    needs to see the path the body took in the frames it was not supposed to be
    visible in. So this is not a blur — it is five distinct silhouettes of that
    same fighter, a frame apart, each fainter than the last.
    """
    out = []
    for i in range(1, count + 1):
        tt = t - spacing * i
        if tt < 0:
            break
        out.append((tt, 0.34 * (1.0 - (i - 1) / max(1, count)), pose_fn(track, tt)))
    return out


# ------------------------------------------------------------ levitating rocks
def levitating_rocks(centre_x: float, ground_y: float, frame_idx: int,
                     count: int = 9, power: float = 1.0, seed: int = 7):
    """Stones torn out of the floor, hanging in the field around a fighter.

    Each rock has its own phase so they do not pulse in unison — a lifted ring of
    stones that bob together looks like a UI element, not like weight being
    taken off the ground.
    """
    rng = random.Random(seed)
    out = []
    for i in range(count):
        phase = rng.uniform(0, math.tau)
        base = ((i % 5) - 2.0) * 34.0 + rng.uniform(-10, 10)
        lift = 34.0 + 24.0 * i + math.sin(frame_idx * 0.22 + phase) * 9.0
        out.append({
            "x": centre_x + base * (0.8 + 0.4 * power),
            "y": ground_y - lift * power - 8.0,
            "angle": frame_idx * 0.05 * (1 if i % 2 else -1) + phase,
            "size": 4.0 + (i % 4) * 2.6,
            "alpha": 0.55 + 0.45 * min(1.0, lift / 120.0),
        })
    return out


def draw_levitating_rocks(cv, rocks, colour=(74, 66, 62), edge=(26, 22, 24)) -> None:
    u = cv.unit()
    for r in rocks:
        s = r["size"] * u
        ca, sa = math.cos(r["angle"]), math.sin(r["angle"])
        pts = []
        for k in range(5):
            a = r["angle"] + k * math.tau / 5.0
            rr = s * (0.78 + 0.30 * math.sin(k * 2.3 + r["angle"]))
            pts.append(cv.wp((r["x"] + math.cos(a) * rr, r["y"] + math.sin(a) * rr)))
        cv.polygon(pts, colour, alpha=int(235 * r["alpha"]))
        cv.polyline(pts + [pts[0]], max(1.0, 1.2 * u), edge, alpha=150)
