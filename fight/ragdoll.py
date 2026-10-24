"""The knockdown: a body that flies, bounces, skids and then has to get up.

The old fall was three keys — hit, ``FALL``, ``DOWN`` — which read as a figure
being rotated flat and then stood back on its feet. A real knockdown is a short
ballistic arc with consequences the camera can see:

* the body **leaves the floor** — the contact shadow follows it for free, since
  the lift is derived from the feet;
* it **bounces**: the pelvis comes down, up 15 units, down again, each landing
  throwing dust, and it **skids** a decelerating distance on the second one;
* getting up is **work**: roll, hands and knees, the arms give out once, push
  up, sway onto the feet — never an instant guard pose.

Only the times of the beats are decided here. The *horizontal* path is filled in
by :func:`reanchor` after the spacing solvers have run, because those solvers
move the contact position: the body has to land relative to where the blow
actually landed, and walk back into the stance at wherever the next key of the
choreography is — otherwise the figure slides on the spot.
"""
from __future__ import annotations

import math

from . import poses as PS


#: the flight, in seconds after the blow: (when, fraction of the throw now
#: travelled, dust puffs to throw, pose)
FLIGHT_BEATS = (
    (0.045, 0.10, None, PS.LAUNCH),      # the feet leave the floor
    (0.130, 0.42, None, PS.FLIGHT),      # airborne, body turning over
    (0.210, 0.74, 3, PS.SLAM),           # first landing, hard
    (0.265, 0.86, 1, PS.BOUNCE),         # it bounces
    (0.330, 0.94, 2, PS.SLAM),           # second landing
    (0.400, 0.98, 1, PS.SPRAWL),         # the skid runs out
    (0.520, 1.00, None, PS.SPRAWL),      # still, gathering itself
)

#: getting up, as fractions of the window between the skid and the guard:
#: (when, pose) — it is a struggle, so the arms give out once on the way
RISE_BEATS = (
    (1 / 7, PS.ROLL),                    # rolls onto the hip
    (2 / 7, PS.ALL_FOURS),               # hands and knees
    (3 / 7, PS.GIVE),                    # the arms give out
    (4 / 7, PS.ALL_FOURS),               # up again
    (5 / 7, PS.PUSHUP),                  # drives off the hands
    (6 / 7, PS.STAGGER),                 # feet under it, still swaying
    (1.00, PS.SPENT),                    # standing, spent
)


def knockdown(track, t_hit: float, end: float, *, throw: float = 32.0,
              power: float = 1.0, dust=None, stay: bool = False) -> None:
    """Replace the flat fall of ``track`` at ``t_hit`` with a real knockdown.

    ``end`` is when the fighter must be back on its feet (ignored when
    ``stay``), ``throw`` how far the body is thrown in pixels, ``power`` scales
    it. :func:`reanchor` must be called once the timeline is complete.
    """
    x0 = track.sample(t_hit)[1]
    throw *= power
    direction = track.facing          # it is knocked away from the opponent
    dust = dust or (lambda t: None)
    group = {"track": track, "t_hit": t_hit, "throw": throw * -direction,
             "stay": stay, "end": end, "fly": [], "rise": [], "guard": None}

    for dt, frac, puffs, pose in FLIGHT_BEATS:
        t = t_hit + dt
        # the launch throws, the skid creeps: ease out of it
        track.key(t, pose, x0 - direction * throw * frac,
                  "out" if dt < 0.2 else "smooth")
        group["fly"].append((t, frac, pose))
        for i in range(puffs or 0):
            dust(t + i * 0.035)

    if stay:
        # a knocked-out body is not still: the chest keeps working
        t_down = t_hit + FLIGHT_BEATS[-1][0]
        x_down = x0 - direction * throw
        track.key(t_down + 0.35, PS.fade(PS.SPRAWL, head=-10), x_down, "smooth")
        track.key(end, PS.fade(PS.SPRAWL, head=-4, spine=1.0), x_down, "smooth")
        group["fly"].append((t_down + 0.35, 1.0, PS.SPRAWL))
        group["fly"].append((end, 1.0, PS.SPRAWL))
        track._kd = getattr(track, "_kd", []) + [group]
        return

    t_rise = t_hit + FLIGHT_BEATS[-1][0]
    span = max(0.55, end - 0.14 - t_rise)
    # placed provisionally where the body landed: the spacing solvers run on
    # this timeline and a fighter sitting at x=0 would drag its neighbours
    provisional = x0 - direction * throw
    for frac, pose in RISE_BEATS:
        t = t_rise + span * frac
        track.key(t, pose, provisional, "smooth" if frac < 1.0 else "out")
        group["rise"].append((t, frac, pose))
    t_guard = t_rise + span + 0.09
    track.key(t_guard, PS.GUARD, provisional, "out")
    group["guard"] = t_guard
    track._kd = getattr(track, "_kd", []) + [group]


def reanchor(track) -> None:
    """Place every knockdown now that the contact positions are final.

    The flight follows the throw; the get-up travels from where the body landed
    to wherever the next key of the fight actually is, with a small sway so the
    rise does not read as a slide.
    """
    groups = getattr(track, "_kd", None)
    if not groups:
        return
    direction = track.facing
    for g in groups:
        x0 = track.sample(g["t_hit"])[1]
        x_land = x0 + g["throw"]
        for t, frac, pose in g["fly"]:
            _set_x(track, t, x0 + g["throw"] * frac)
        if g["stay"] or not g["rise"]:
            continue
        # the target: the next key of the choreography after the rise
        later = [k for k in track.keys if k[0] > g["guard"] + 1e-6]
        target = later[0][2] if later else x0
        span = g["rise"][-1][0] - g["rise"][0][0]
        for t, frac, pose in g["rise"]:
            u = 0.0 if span <= 0 else (t - g["rise"][0][0]) / span
            u = u * u * (3 - 2 * u)
            wobble = math.sin(frac * math.pi * 2.0) * 4.0 if frac < 1.0 else 0.0
            _set_x(track, t, x_land + (target - x_land) * u - direction * wobble)
        _set_x(track, g["guard"], target)


def _set_x(track, t: float, x: float) -> None:
    for i, (kt, kp, kx, ke) in enumerate(track.keys):
        if abs(kt - t) < 1e-6:
            track.keys[i] = (kt, kp, x, ke)
            return
