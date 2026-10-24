"""The camera: a shot list, a follow rig, and a shake with a direction.

Until now there was one camera, and it only existed in the background: the plate
was cropped with a slow push-in while the fighters were drawn with a *fixed*
transform. Nothing could whip, punch in, or look at a foot. This module replaces
it with one transform that both the landscape and the fighters ride:

    screen = centre + (design - camera + shake) * zoom * k

so a shot is just a list of numbers about *where the camera looks* and *how
tight*, and everything painted — background, shadows, bodies, trails, dust —
moves together.

A shot is a row in ``SHOTS``:

``anchor``  what the camera is pointed at: the pair (``action``), one fighter,
            the last impact, or the feet of the downed fighter.
``zoom``    how tight, and how much it may punch in on a hit.
``dof``     0 for everything sharp, 1 for a background blurred into bokeh.
``style``   ``cut`` (hard) or ``whip`` (0.12 s of travel and a smear).
``dy``      framing bias: negative looks slightly up, positive puts the camera
            low so the ground fills the frame.

Two more things the reference fight does and this now does too:

*The shake has a direction.* Every impact carries the vector of the blow, so the
camera kicks along it and only rings perpendicular to it — a punch reads as a
punch, the finisher as a diagonal slam.

*The follow has lag.* The camera target is a mix of where the action is now and
where it was a tenth of a second ago, which is what makes a pan feel like an
operator trying to keep up instead of a rail.
"""
from __future__ import annotations

import math

from .clash import DESIGN_H, DESIGN_W, GROUND

WHIP = 0.13           # seconds a whip pan takes
LAG = 0.10            # how far back the follow looks
FRAME = 1.0 / 24.0


def smooth(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * (3.0 - 2.0 * u)


#: the edit. ``t1`` is exclusive; the last shot runs to the end of the film.
SHOTS = (
    # establish: the arena, the two fighters walking in
    dict(t0=0.00, t1=2.40, anchor="action", zoom=1.00, z1=1.05, follow=0.35,
         dof=0.0, style="cut", ground=0.80),
    # first exchange: tight and level, the camera works to keep them both in
    dict(t0=2.40, t1=5.10, anchor="action", zoom=1.14, z1=1.18, follow=1.0,
         dof=0.10, style="cut", ground=0.79),
    # wide again for the kicks: you need the whole body to read a sweep
    dict(t0=5.10, t1=7.55, anchor="action", zoom=1.04, follow=0.7,
         dof=0.0, style="cut", ground=0.80),
    # the uppercut that drops blue
    dict(t0=7.55, t1=8.10, anchor="action", zoom=1.26, follow=1.0,
         dof=0.18, style="whip", ground=0.78, zoom_hit=0.10),
    # floor level: the body lands, bounces and skids
    dict(t0=8.10, t1=9.55, anchor="down", zoom=1.52, fg=0.30, follow=1.0,
         dof=0.30, style="whip", ground=0.74, zoom_hit=0.06),
    dict(t0=9.55, t1=12.75, anchor="action", zoom=1.12, z1=1.20, follow=1.0,
         dof=0.10, style="cut", ground=0.79),
    # the clash of fists at 13.44 gets its own push, then the insert cuts in
    dict(t0=12.75, t1=13.44, anchor="impact", zoom=1.30, follow=1.0,
         dof=0.22, style="whip", ground=0.78, zoom_hit=0.12),
    dict(t0=13.44, t1=13.88, anchor="action", zoom=1.10, follow=1.0,
         dof=0.0, style="cut", ground=0.80),
    dict(t0=13.88, t1=15.60, anchor="action", zoom=1.06, follow=0.8,
         dof=0.05, style="cut", ground=0.80),
    # the uppercut at 15.80 and red's fall: the camera drops with him
    dict(t0=15.60, t1=16.30, anchor="action", zoom=1.22, follow=1.0,
         dof=0.15, style="whip", ground=0.72, zoom_hit=0.10),
    dict(t0=16.30, t1=17.45, anchor="down", zoom=1.42, fg=0.30, follow=1.0,
         dof=0.28, style="whip", ground=0.73, zoom_hit=0.05),
    dict(t0=17.45, t1=18.95, anchor="action", zoom=1.10, z1=1.16, follow=1.0,
         dof=0.08, style="cut", ground=0.79),
    # blue goes down at 18.98
    dict(t0=18.95, t1=19.30, anchor="action", zoom=1.20, follow=1.0,
         dof=0.12, style="whip", ground=0.75, zoom_hit=0.08),
    dict(t0=19.30, t1=20.15, anchor="down", zoom=1.50, fg=0.30, follow=1.0,
         dof=0.30, style="whip", ground=0.73, zoom_hit=0.05),
    dict(t0=20.15, t1=21.30, anchor="action", zoom=1.08, z1=1.14, follow=1.0,
         dof=0.06, style="cut", ground=0.80),
    # the last exchange: the camera is inside it now
    dict(t0=21.30, t1=23.40, anchor="action", zoom=1.18, z1=1.26, follow=1.0,
         dof=0.12, style="cut", ground=0.78, zoom_hit=0.07),
    dict(t0=23.40, t1=24.40, anchor="action", zoom=1.06, follow=0.9,
         dof=0.0, style="cut", ground=0.80),
    # the finisher, then its insert
    dict(t0=24.40, t1=25.24, anchor="action", zoom=1.26, follow=1.0,
         dof=0.20, style="whip", ground=0.76, zoom_hit=0.16),
    # the pull-back: the winner, and the body on the floor
    dict(t0=25.24, t1=30.20, anchor="winner", zoom=1.12, z1=1.02, follow=0.6,
         dof=0.0, style="whip", ground=0.80),
)


def shot_at(t: float) -> dict:
    for s in SHOTS:
        if s["t0"] <= t < s["t1"]:
            return s
    return SHOTS[-1]


# --------------------------------------------------------------------- anchors
def _feet(sk) -> tuple[float, float]:
    xs = (sk.pts[8][0] + sk.pts[10][0]) * 0.5
    ys = max(sk.pts[8][1], sk.pts[10][1])
    return xs, ys


def _pair(scene, t: float):
    return scene["red"].skel(t), scene["blue"].skel(t)


def _downed(scene, t: float):
    """The fighter on the floor, if there is one — the camera follows it down."""
    best = None
    for name in ("red", "blue"):
        tr = scene[name]
        p = tr.sample(t)[0]
        h = p.get("hip", 999.0)
        if best is None or h < best[1]:
            best = (name, h, tr)
    return best


def _floor_y(shot, zoom: float) -> float:
    """Where the camera has to sit for the floor to land at ``ground`` of the
    frame — the one number that makes a shot read as wide, level or low, and it
    keeps the framing identical whatever the zoom does."""
    return GROUND - (shot.get("ground", 0.79) - 0.5) * DESIGN_H / zoom


def anchor_point(scene, shot, t: float, zoom: float):
    kind = shot["anchor"]
    sa, sb = _pair(scene, t)
    y = _floor_y(shot, zoom) + shot.get("dy", 0.0)
    if kind == "down":
        name, hip, tr = _downed(scene, t)
        sk = sa if name == "red" else sb
        # between the chest and the floor: a body on the ground sits low
        return (sk.head[0] * 0.55 + _feet(sk)[0] * 0.45, y)
    if kind == "impact":
        for e in reversed(scene["impacts"]):
            if e["t"] <= t + 1e-6:
                return (e["x"], e["y"] + 30.0 + shot.get("dy", 0.0))
        return ((sa.head[0] + sb.head[0]) * 0.5, y)
    if kind == "winner":
        name, hip, tr = _downed(scene, t)
        win = sb if name == "red" else sa
        down = sa if name == "red" else sb
        return (win.head[0] * 0.62 + down.head[0] * 0.38, y)
    # action: the middle of the pair, framed on the floor line
    return ((sa.head[0] + sb.head[0]) * 0.5, y)


def _shot_cam(scene, shot, t: float):
    """Camera state for one shot: centre, zoom, defocus."""
    span = max(1e-6, shot["t1"] - shot["t0"])
    u = smooth((t - shot["t0"]) / span)
    base = shot["zoom"] + (shot.get("z1", shot["zoom"]) - shot["zoom"]) * u
    x, y = anchor_point(scene, shot, t, base)
    if shot["follow"] > 0.0:
        xl, yl = anchor_point(scene, shot, max(shot["t0"], t - LAG), base)
        f = shot["follow"]
        x = x + (xl - x) * LAG * 2.0 * f * 0.5
        y = y + (yl - y) * LAG * 2.0 * f * 0.5
    zoom = base
    # a punch-in at every contact inside the shot
    kick = shot.get("zoom_hit", 0.0)
    if kick:
        for e in scene["impacts"]:
            age = t - e["t"]
            if 0.0 <= age < 0.34:
                zoom += kick * e.get("size", 1.0) * math.exp(-age / 0.13)
    return x, y, zoom, shot.get("dof", 0.0)


def camera(scene, t: float, ta: float | None = None) -> dict:
    """Position, zoom, defocus and directional shake at real time ``t``.

    ``ta`` is the animation clock: the shake rides it, so at the instant of
    contact the camera is as frozen as the bodies.
    """
    ta = t if ta is None else ta
    shot = shot_at(t)
    x, y, zoom, dof = _shot_cam(scene, shot, t)
    if shot["style"] == "whip":
        prev = None
        for s in SHOTS:
            if s["t1"] <= t and s is not shot:
                prev = s
        if prev is not None and t < shot["t0"] + WHIP:
            px, py, pz, pd = _shot_cam(scene, prev, prev["t1"] - 1e-4)
            u = smooth((t - shot["t0"]) / WHIP)
            x, y, zoom = px + (x - px) * u, py + (y - py) * u, pz + (zoom - pz) * u
            dof = pd + (dof - pd) * u
            whip = 1.0 - u
        else:
            whip = 0.0
    else:
        whip = 0.0
    sx, sy = shake(scene["impacts"], ta)
    return {"x": x, "y": y, "zoom": zoom, "dof": dof, "shake_x": sx,
            "shake_y": sy, "whip": whip, "shot": shot,
            "foreground": shot.get("fg", 1.0)}


# ----------------------------------------------------------------------- shake
def shake(impacts, t: float):
    """Directional camera shake: the frame kicks along the force of the blow.

    Each impact carries ``dx`` (+1 if it lands to the right, -1 to the left,
    0 for a clash straight on). The camera moves along that axis at full
    amplitude and only rings at 35 % across it, which is what makes a punch feel
    like a punch and not like a rumble.
    """
    sx = sy = 0.0
    for e in impacts:
        age = t - e["t"]
        if not (0.0 <= age < 0.36):
            continue
        k = (1.0 - age / 0.36) ** 2
        amp = (15.0 if e["kind"] == "final" else
               10.0 if e["kind"] == "clash" else
               7.0 if e["kind"] == "hit" else 3.4) * e.get("size", 1.0)
        d = float(e.get("dx", 0.0))
        along = math.sin(age * 86.0 + e["t"] * 11.0) * amp * k
        across = math.cos(age * 63.0 + e["t"] * 7.0) * amp * 0.35 * k
        sx += along * d + across * (1.0 - abs(d))
        sy += across * abs(d) + along * 0.30 * (1.0 - abs(d))
        sy -= math.cos(age * 49.0 + e["t"] * 5.0) * amp * 0.30 * k * abs(d)
    return sx, sy


def background_parallax(cam: dict, factor: float = 0.36) -> tuple[float, float]:
    """Where the plate is cropped: it lags the camera, which is the depth cue."""
    return (DESIGN_W * 0.5 + (cam["x"] - DESIGN_W * 0.5) * factor + cam["shake_x"],
            DESIGN_H * 0.5 + (cam["y"] - DESIGN_H * 0.5) * factor * 0.55 + cam["shake_y"])
