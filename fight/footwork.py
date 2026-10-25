"""Real feet: the body does not slide across the ground, it steps.

Every pose in ``poses.py`` is authored around a hip and a pair of foot offsets,
and the choreography moves the fighter by sliding its ``x`` between keys. That
reads as a cut-out being dragged across the floor: the feet stay welded to the
same spot on the body while the ground streams past underneath.

This module derives the step cycle from the one thing the choreography already
knows — how far the fighter has travelled — and hands back the foot offsets and
lifts for that instant:

* the cycle advances with **distance**, not with time, so the feet never skate:
  each stride covers ``stride`` design px whatever the speed is, and a sprint
  simply takes shorter, quicker steps;
* the swinging foot lifts, travels forward and lands; the planted one slides
  back through the stance exactly as far as the body moved;
* a hard deceleration puts **both** feet down — the skid — and leans the torso
  back over the heels, which is the pose that reads as a stop instead of a
  freeze.

Nothing here changes the skeleton solver: it only edits the pose dict before
``to_pose`` gets it.
"""
from __future__ import annotations

import math

#: design px of ground covered by one step at a walk; a run covers more
STEP_LEN = 56.0
#: px/s below which the fighter is standing and the authored feet are kept
STILL = 24.0
#: px/s² that turns a stop into a skid
SKID_DECEL = 520.0
#: how far the front foot reaches ahead of the hips while stepping
REACH = 17.0

_GRID = 0.02


def _x(tr, t: float) -> float:
    return tr.sample(max(0.0, t))[1]


def speed(tr, t: float, dt: float = 0.04) -> float:
    """Horizontal speed in design px/s, measured backwards from ``t``."""
    if t <= dt:
        return 0.0
    return (_x(tr, t) - _x(tr, t - dt)) / dt


def accel(tr, t: float, dt: float = 0.05) -> float:
    """Change of speed per second (negative while stopping)."""
    if t <= 2 * dt:
        return 0.0
    v1 = (_x(tr, t) - _x(tr, t - dt)) / dt
    v0 = (_x(tr, t - dt) - _x(tr, t - 2 * dt)) / dt
    return (v1 - v0) / dt


def _walked(tr, t: float) -> float:
    """Path length travelled up to ``t``, cached on the track.

    Integrating |dx| rather than |x - x0| is what makes a fighter who steps
    back and forth keep stepping instead of teleporting its feet.
    """
    cache = getattr(tr, "_walked", None)
    if cache is None or t < cache["t"] - 0.4:
        # frames are normally drawn in order, but a still or a storyboard can
        # ask for an earlier instant: rebuild rather than walk backwards
        cache = {"t": 0.0, "d": 0.0}
        setattr(tr, "_walked", cache)
    n = int((t - cache["t"]) / _GRID)
    if n <= 0:
        return cache["d"]
    prev = _x(tr, cache["t"])
    d = cache["d"]
    for i in range(n):
        cur_t = cache["t"] + _GRID * (i + 1)
        cur = _x(tr, cur_t)
        d += abs(cur - prev)
        prev = cur
    cache["t"] += _GRID * n
    cache["d"] = d
    return d


def skid_times(tr, t0: float = 0.0, t1: float = 30.0) -> list:
    """Every instant where the fighter brakes hard enough to slide."""
    out = []
    t = t0
    while t < t1:
        if speed(tr, t) > 90.0 and accel(tr, t) < -SKID_DECEL:
            if not out or t - out[-1] > 0.45:
                out.append(round(t, 3))
        t += 0.02
    return out


def apply(tr, t: float, p: dict) -> dict:
    """Return the pose with the step cycle and the skid folded in."""
    v = speed(tr, t)
    spd = abs(v)
    l_lift = p["foot_l"][1]
    r_lift = p["foot_r"][1]
    braking = accel(tr, t)

    # a kick or a jump owns the feet: never argue with an authored lift
    if l_lift > 0.3 or r_lift > 0.3:
        return p
    if braking < -SKID_DECEL and spd > 30.0:
        # sliding to a halt: both feet planted, wide, and the weight back
        out = dict(p)
        out["foot_l"] = (p["foot_l"][0] + REACH * 0.55, 0.0)
        out["foot_r"] = (p["foot_r"][0] - REACH * 0.55, 0.0)
        out["torso"] = p["torso"] - 7.0 * min(1.0, -braking / 900.0) * tr.facing
        out["head"] = p.get("head", 0.0) + 4.0 * min(1.0, -braking / 900.0)
        out["crouch"] = p.get("crouch", 0.0) + 5.0 * min(1.0, -braking / 900.0)
        return out
    if spd < STILL:
        return p

    # stride grows a little with speed, then the cycle runs on distance
    stride = STEP_LEN + 0.06 * min(spd, 260.0)
    d = _walked(tr, t)
    reach = REACH * (0.8 + 0.5 * min(spd, 300.0) / 300.0)

    out = dict(p)
    for key, phase in (("foot_l", 0.0), ("foot_r", 0.5)):
        s = (d / stride + phase) % 1.0
        if s < 0.5:                      # stance: the foot slides back
            off = reach * (1.0 - 4.0 * s)
            lift = 0.0
        else:                            # swing: up, forward, down again
            u = (s - 0.5) * 2.0
            e = u * u * (3.0 - 2.0 * u)
            off = -reach + 2.0 * reach * e
            lift = 0.42 * math.sin(math.pi * u) ** 0.8
        old = out[key]
        out[key] = (old[0] + off, max(old[1], lift))
    # the hips ride a touch higher over the stance leg
    out["crouch"] = p.get("crouch", 0.0) - 2.2 * abs(math.sin(2 * math.pi *
                                                            (d / stride) % math.pi))
    return out
