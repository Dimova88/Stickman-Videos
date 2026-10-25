"""Steel: the katana, the arc it cuts in the air, and the sparks it throws.

A blade is not a stick with a handle. Four things make it read as steel at this
size, and all four are geometry:

* **a curved spine and a straight edge** — the kissaki (tip) is offset from the
  line of the forearm, so the sword is *held*, not extruded from the wrist;
* **a bright edge and a dark spine** — the light catches one side only, which is
  what tells the eye it is metal rather than a blue limb;
* **a tsuba and a wrapped grip** — a 6 px bar and four dark bands, which is all
  it takes to say "sword" instead of "pole";
* **the arc.** A slash leaves a crescent in the air: the region between where
  the tip was and where it is now, brightest at the edge of the cut, fading over
  0.12 s. That crescent is the single most recognisable mark of the whole genre,
  and it is two polygons and a stroke.

Nothing here is a sprite: the blade follows the hand that holds it, so it is
always in the right place no matter what the choreography does.
"""
from __future__ import annotations

import math

import numpy as np

STEEL = (226, 232, 240)
EDGE = (255, 255, 255)
SPINE = (120, 132, 148)
HILT = (34, 30, 30)
GOLD = (196, 160, 92)


def half_of(length: float) -> float:
    """Half the blade's width, in design units, for a given blade length."""
    return max(1.0, length * 0.022)


def blade_geometry(wrist, ang: float, length: float):
    """The blade in *design* space, as a closed outline plus the tip.

    Everything here is design units — the camera transform is applied once, at
    the end, by ``Canvas.wp``. Mixing the two is what put the first version's
    blades in the wrong place: the widths were in screen pixels and the points
    in design units, so a sword was drawn at the scale of the font.
    """
    ca, sa = math.cos(ang), math.sin(ang)
    nx, ny = -sa, ca                      # across the blade
    curve = length * 0.035                # the kanji curve: spine bows off the edge

    def at(f, off):
        return (wrist[0] + ca * length * f + nx * off,
                wrist[1] + sa * length * f + ny * off)

    # one 23rd of its length wide at the machi, easing to the yokote, then a
    # short kissaki: a long needle to the point reads as a spear, not a sword
    half = half_of(length)
    edge = [at(0.02, -half * 0.72), at(0.55, -half * 0.98),
            at(0.90, -half * 0.92 + curve * 0.36)]
    spine = [at(0.02, half * 0.72), at(0.55, half * 0.92),
             at(0.90, half * 0.86 + curve * 0.36)]
    tip = at(1.0, curve * 0.55)
    return edge, spine, tip


def draw_blade(cv, wrist, ang: float, length: float, glow: float = 0.0,
               colour=STEEL, handle: bool = False) -> None:
    """One katana, from the back of the hand to the tip.

    ``handle`` fills the grip instead of leaving three floating bands: in a
    fight the fist covers it, but a blade exported on its own needs it.
    """
    u = cv.unit()
    edge, spine, tip = blade_geometry(wrist, ang, length)
    w, ca, sa = cv.wp(wrist), math.cos(ang), math.sin(ang)
    nx, ny = -sa, ca

    def S(*pts):
        return [cv.wp(p) for p in pts]

    if handle:
        g0 = cv.wp((wrist[0] - ca * length * 0.13,
                    wrist[1] - sa * length * 0.13))
        g1 = cv.wp((wrist[0] + ca * length * 0.02,
                    wrist[1] + sa * length * 0.02))
        gw = max(2.0, half_of(length) * 0.72 * u)
        cv.polygon([(g0[0] + nx * gw, g0[1] + ny * gw),
                    (g1[0] + nx * gw, g1[1] + ny * gw),
                    (g1[0] - nx * gw, g1[1] - ny * gw),
                    (g0[0] - nx * gw, g0[1] - ny * gw)], HILT)

    # the body: the outline down the edge, the tip, and back up the spine
    cv.polygon(S(*edge) + [cv.wp(tip)] + S(*reversed(spine)), colour)
    # the bright edge on the cutting side, the dark spine on the other
    cv.polyline(S(*edge) + [cv.wp(tip)], max(1.2, 1.5 * u), EDGE, alpha=225)
    cv.polyline(S(*spine) + [cv.wp(tip)], max(1.0, 1.2 * u), SPINE, alpha=190)
    # tsuba: a bar across the blade at the hand
    g = 4.6
    cv.line((w[0] + nx * g * u - ca * 2.0 * u, w[1] + ny * g * u - sa * 2.0 * u),
            (w[0] - nx * g * u - ca * 2.0 * u, w[1] - ny * g * u - sa * 2.0 * u),
            max(1.8, 2.6 * u), GOLD)
    # the grip: three short bands behind the guard, dark enough to sink into the
    # fist rather than stripe it
    for i in range(3):
        f0 = -0.045 - i * 0.042
        p = cv.wp((wrist[0] + ca * length * f0, wrist[1] + sa * length * f0))
        cv.line((p[0] + nx * 3.2 * u, p[1] + ny * 3.2 * u),
                (p[0] - nx * 3.2 * u, p[1] - ny * 3.2 * u),
                max(1.2, 1.8 * u), HILT, alpha=185)
    if glow > 0.02:
        cv.polyline(S(*edge) + [cv.wp(tip)], max(2.0, 4.4 * u), EDGE,
                    alpha=int(60 * glow))


def tip_of(wrist, ang: float, length: float):
    return (wrist[0] + math.cos(ang) * length,
            wrist[1] + math.sin(ang) * length)


def slash_arc(cv, samples, length: float, power: float = 1.0,
              flat: bool = False) -> None:
    """The crescent a swung blade leaves, built from the tip's own path.

    ``samples`` is a list of ``(wrist, angle)`` from the oldest to now. The band
    is the ribbon between the tip path and a circle just inside it, which is why
    it always *joins* the blade instead of hanging next to it — a crescent made
    by sweeping an assumed arc does not, and reads as a floating white bar.
    """
    if power <= 0.30 or len(samples) < 3:
        return
    u = cv.unit()
    # Only the last part of the swing is *visible* air; the rest of a 120° snap
    # happened between exposures. Clamp the ribbon to 50° of arc, interpolating
    # the cut sample, so a fast cut reads as a sharp crescent and never as a
    # painted fan across half the sky.
    span = 0.85
    end_a = samples[-1][1]
    keep = [samples[-1]]
    for j in range(len(samples) - 2, -1, -1):
        w, a = samples[j]
        d = (end_a - a + math.pi) % math.tau - math.pi
        if abs(d) <= span:
            keep.append(samples[j])
        else:
            k = span / abs(d)
            keep.append((w, end_a - math.copysign(span, d)))
            break
    samples = list(reversed(keep))
    n = len(samples) - 1
    outer = [cv.wp(tip_of(w, a, length)) for w, a in samples]
    # the band is fat at the leading edge and thins to a whisker at the tail,
    # which is the shape of every great slash in the genre
    inner = [cv.wp(tip_of(w, a, length * (0.995 - 0.26 * math.sin(
                 math.pi * i / max(1, n)))))
             for i, (w, a) in enumerate(samples)]
    # the brightest part of a slash is the leading edge, so the band fades from
    # the tip inward instead of being one flat sheet of white
    def a(v: float) -> int:
        # ``flat`` is the asset export: the same shape at full opacity, so the
        # PNG can be tinted and faded by whatever uses it next
        return 255 if flat else int(v * power)

    # a very fast swing sweeps so far in one exposure that the ribbon would
    # become a sheet of white: fade it as the sweep grows, so the arc reads as
    # air rather than as a painted fan
    sweep = abs((samples[-1][1] - samples[0][1] + math.pi) % math.tau - math.pi)
    fade = min(1.0, 1.1 / max(0.35, sweep))
    # a filled crescent with one bright outer edge. The inner edge gets no
    # stroke: a hollow outline in the sky reads as a floating wire, not as air
    # that a blade just moved through
    cv.polygon(outer + list(reversed(inner)), (255, 255, 255),
               alpha=a(126 * fade))
    cv.polyline(outer, max(1.5, 2.4 * u), (255, 255, 255), alpha=a(215 * fade))


def local_crescent(cv, hilt, angles, length: float, power: float = 1.0,
                   subdivisions: int = 12, colour=(255, 255, 255)) -> None:
    """The crescent a swing leaves, built in *local* polar space.

    The bug this replaces: the smear used to be the band between where the tip
    was and where it is now, in world coordinates. That is correct only while
    the fighter stands still — the moment he dashes, the same band becomes a
    parallelogram spanning the whole arena, which is the "sheet of white paper".
    Gating it off during a dash was worse: the dash is exactly when a slash
    should smear.

    So the polygon is anchored to the hilt **now** and only the *angle history*
    is interpolated: both edges are arcs of the same circle, so the shape is a
    crescent whatever the body does, and a 250 px lunge cannot widen it by a
    single pixel.
    """
    if len(angles) < 2 or power <= 0.05:
        return
    th_end = angles[-1]
    d = (th_end - angles[0] + math.pi) % math.tau - math.pi
    if abs(d) < 0.16:                     # a thrust, not a sweep
        return
    d = max(-0.95, min(0.95, d))          # the visible air, not the whole snap
    th0 = th_end - d
    hx, hy = hilt
    outer, inner = [], []
    for i in range(subdivisions + 1):
        u = i / subdivisions
        a = th0 + d * u
        taper = 0.72 + 0.28 * math.sin(u * math.pi * 0.5)
        r_out = length * taper
        # a crescent is a *band*: it starts as a whisker at the tail and widens
        # toward the blade. Sizing the inner radius as a fraction of the blade
        # (rather than a fraction of the band) is what turned it into a fan.
        band = length * (0.035 + 0.115 * u)
        r_in = max(0.0, r_out - band)
        outer.append(cv.wp((hx + math.cos(a) * r_out, hy + math.sin(a) * r_out)))
        inner.append(cv.wp((hx + math.cos(a) * r_in, hy + math.sin(a) * r_in)))
    # the smear is air, not paper: it is nearly nothing at the tail and only
    # reaches full strength at the blade. One flat alpha over the whole band is
    # what made a compact swing read as a white lampshade above the head.
    n = len(outer) - 1
    for k in range(3):
        i0, i1 = int(k * n / 3), int((k + 1) * n / 3)
        seg = outer[i0:i1 + 1] + list(reversed(inner[i0:i1 + 1]))
        a = int((12 + 46 * (k + 1) / 3) * power)
        cv.polygon(seg, colour, alpha=a)
    # the leading edge is the steel itself: bright, and it ends at the hilt
    cv.line(outer[-1], cv.wp(hilt), max(1.2, 2.0 * cv.unit()), colour,
            alpha=int(200 * power))


def thrust_cone(cv, hilt, angle: float, length: float, speed: float,
                power: float = 1.0) -> None:
    """A straight thrust leaves no arc, so it leaves a needle of compressed air."""
    if speed < 700.0 or power <= 0.05:
        return
    hx, hy = hilt
    ux, uy = math.cos(angle), math.sin(angle)
    nx, ny = -uy, ux
    reach = length + min(46.0, speed * 0.03)
    tip = cv.wp((hx + ux * reach, hy + uy * reach))
    l = cv.wp((hx - ux * 18.0 + nx * 10.0, hy - uy * 18.0 + ny * 10.0))
    r = cv.wp((hx - ux * 18.0 - nx * 10.0, hy - uy * 18.0 - ny * 10.0))
    cv.polygon([tip, l, r], (255, 255, 255),
               alpha=int(60 + 90 * min(1.0, power)))


def slash_trail(cv, tips, power: float = 1.0, width: float = 13.0) -> None:
    """The streak the point of a blade leaves in the air.

    A ribbon between two tip *paths* turns into a kite as soon as the fighter
    also steps, so the trail is a tapered brush along the single path the tip
    actually travelled: thick and bright at the blade, a whisker at the tail,
    always ending exactly where the point of the sword is now. It is drawn as
    one polygon with square ends — strokes with round caps at this width read as
    a string of beads hanging in the sky.
    """
    if power <= 0.15 or len(tips) < 3:
        return
    u = cv.unit()
    pts = [cv.wp(p) for p in tips]
    n = len(pts) - 1
    left, right = [], []
    for i, p in enumerate(pts):
        f = i / n                              # 0 at the tail, 1 at the blade
        w = max(0.35, width * u * 0.5 * f * f)
        q = pts[min(n, i + 1)]
        r = pts[max(0, i - 1)]
        dx, dy = q[0] - r[0], q[1] - r[1]
        d = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / d * w, dx / d * w
        left.append((p[0] + nx, p[1] + ny))
        right.append((p[0] - nx, p[1] - ny))
    a = int(150 * power)
    if a <= 3:
        return
    cv.polygon(left + list(reversed(right)), (255, 255, 255), alpha=a)
    cv.polyline(left[max(0, n - 2):], max(1.0, 1.8 * u), (255, 255, 255),
                alpha=min(235, int(a * 1.4)))


def sparks(cv, cx: float, cy: float, age: float, size: float = 1.0,
           seed: float = 0.0) -> None:
    """Metal on metal: short, fast, hot, and they bounce.

    Steel sparks are not round puffs. They are straight streaks that leave the
    contact point fast and fall, so they are drawn as lines with a short bright
    segment and a longer dimmer tail.
    """
    if not (0.0 <= age < 0.45):
        return
    u = cv.unit()
    k = age / 0.45
    rng = np.random.default_rng(int(seed * 977) % 65521)
    n = int(14 * min(1.8, size))
    for i in range(n):
        a = rng.uniform(-math.pi, math.pi)
        spd = rng.uniform(0.4, 1.5) * (1.0 + 0.6 * size)
        t = k * 0.45
        vx = math.cos(a) * 520.0 * spd
        vy = math.sin(a) * 520.0 * spd - 380.0 * t
        px = cx + vx * t * u
        py = cy + vy * t * u + 900.0 * t * t * u * 0.5
        tail = (px - vx * 0.028 * u, py - vy * 0.028 * u)
        fade = (1.0 - k) ** 1.7
        cv.line(tail, (px, py), max(1.0, 1.6 * u), (255, 236, 180),
                alpha=int(200 * fade))
        cv.line(tail, (px, py), max(2.0, 3.2 * u), (255, 176, 62),
                alpha=int(90 * fade))
