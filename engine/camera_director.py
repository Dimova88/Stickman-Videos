"""The camera director: which lens, how tight, and when time itself slows.

``fight/camera.py`` already owns the shot list, the follow spring and the shake.
This module is the *layer above it* — the decisions a director makes about a
whole act rather than about one frame:

``time_ramp``       slow motion that eases in and out instead of stepping. The
                    film clock is warped, not the frame rate, so a 0.4 s ramp
                    still lands on the beat it was cut for.
``act_pacing``      how long a shot may hold before the act cuts, and how much
                    of an act can be one unbroken take. A 10-minute film that
                    cuts every 1.1 s is a trailer; one that never cuts is a
                    security camera.
``shot_budget``     the per-act tally the director uses to keep the grammar
                    varied: wides, close-ups, overheads, reverse angles.
"""
from __future__ import annotations

import math


def time_ramp(t: float, centre: float, slow: float = 0.22,
              half_width: float = 0.45) -> float:
    """The *playback speed* at film time ``t`` for a slow-motion beat.

    1.0 is real time; ``slow`` is the floor at the centre of the ramp. The curve
    is a raised cosine, so there is no speed step — a hard cut into slow motion
    reads as a dropped frame, not as impact.
    """
    d = abs(t - centre) / max(1e-6, half_width)
    if d >= 1.0:
        return 1.0
    u = 0.5 + 0.5 * math.cos(math.pi * d)
    return 1.0 - (1.0 - slow) * u


def warped_time(t: float, ramps, dt: float = 1.0 / 24.0) -> float:
    """Integrate ``time_ramp`` to get the *animation* clock for a warped shot.

    ``ramps`` is a list of ``(centre, slow, half_width)``. Deterministic, so a
    frame can be fetched in any order — the same rule the rest of the engine
    follows.
    """
    n = int(round(t / dt))
    out = 0.0
    for i in range(n):
        tt = i * dt
        speed = 1.0
        for centre, slow, half in ramps:
            speed *= time_ramp(tt, centre, slow, half)
        out += dt * speed
    return out


def act_pacing(act_seconds: float, cuts: int) -> dict:
    """Is this act cut like a film, or like a metronome?"""
    if cuts <= 0:
        return {"average_shot": act_seconds, "verdict": "one take"}
    avg = act_seconds / cuts
    if avg < 0.7:
        return {"average_shot": avg, "verdict": "trailer cutting"}
    if avg > 12.0:
        return {"average_shot": avg, "verdict": "static"}
    return {"average_shot": avg, "verdict": "ok"}


#: the grammar a 30-second test uses, and the share of each act a long film
#: should keep: a fight that is all close-ups has no geography, and one that is
#: all wides has no intimacy
SHOT_MIX = {"wide": 0.30, "medium": 0.40, "close": 0.20, "overhead": 0.10}


def shot_budget(count: int) -> dict[str, int]:
    """How many of each shot kind a sequence of ``count`` cuts should contain."""
    out = {k: int(round(count * v)) for k, v in SHOT_MIX.items()}
    drift = count - sum(out.values())
    out["medium"] += drift
    return out
