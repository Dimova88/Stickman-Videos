"""The beat engine: a fight is a list of ``CombatBeat`` objects, not loose keys.

A beat is one exchange — one attack, one answer — and it is *compiled* into the
timeline instead of being typed as a dozen keys by hand. Every beat produces the
same four phases, in the same proportions, which is what makes a fight read as
choreography instead of as poses that happen to be near each other:

===================  ==========================================================
``windup``           the body coils: knees bend, the spine arches back, the
                     weapon goes behind the shoulder, and the **free arm** swings
                     forward as a counterweight (it never stays frozen at 90°)
``active``           2–4 frames. The pelvis travels its ``lunge`` in that time
                     (`ease_in_expo`), the weapon sweeps its whole arc, and the
                     feet are stepped by the footwork module because the body
                     moved — not because a key said so
``hitstop``          the contact frame is **held**: attacker and defender share
                     one frozen instant while the camera shakes and the score
                     drops out
``recovery``         the attacker returns to guard; the defender is thrown,
                     skids, or goes down
===================  ==========================================================

Root motion is not optional. A beat carries ``lunge`` in design pixels and moves
the pelvis by it; a ``jump`` lifts the whole figure off the floor for the aerial
moves; a ``side_swap`` puts the attacker down on the far side of the defender, so
the flight crosses the arena instead of standing in front of it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .poses import P, fade

# --------------------------------------------------------------- move presets
# Authored facing RIGHT; ``to_pose`` reflects the solved body for a fighter that
# faces left, so one preset serves both sides of the fight.
#
# ``b_fore`` is the sword angle, because the blade lies along the forearm:
#   -110 straight up    -45 up-forward    0 flat forward    40 down-forward

BLITZ = {
    "windup": P(torso=-94, foot_l=(30, 0), foot_r=(-56, 0),
                a_up=78, a_fore=6, b_up=34, b_fore=-116, head=-8,
                crouch=20, spine=-7.0),
    "active": P(torso=-56, foot_l=(88, 0), foot_r=(-62, 0),
                a_up=48, a_fore=-30, b_up=-10, b_fore=16, head=8, spine=9.0),
    "defend": P(torso=-104, foot_l=(22, 0), foot_r=(-48, 0),
                a_up=52, a_fore=-70, b_up=30, b_fore=-86, head=18, spine=-9.0),
}

RISING = {
    "windup": P(torso=-58, foot_l=(46, 0), foot_r=(-52, 0),
                a_up=64, a_fore=28, b_up=44, b_fore=52, head=10,
                crouch=34, spine=6.0),
    "active": P(torso=-96, foot_l=(54, 0), foot_r=(-56, 0),
                a_up=40, a_fore=-74, b_up=-34, b_fore=-128, head=-10,
                crouch=-6, spine=-10.0),
    "defend": P(torso=-92, foot_l=(18, 0), foot_r=(-34, 0),
                a_up=36, a_fore=-78, b_up=44, b_fore=-104, head=20,
                air=18, spine=-4.0),
}

AERIAL = {
    "windup": P(torso=-88, foot_l=(34, 26), foot_r=(-24, 34),
                a_up=44, a_fore=-70, b_up=-48, b_fore=-126, head=-8,
                air=0, spine=-6.0),
    "active": P(torso=-52, foot_l=(58, 0), foot_r=(-16, 0),
                a_up=56, a_fore=-18, b_up=18, b_fore=54, head=10,
                air=0, spine=10.0),
    "defend": P(torso=-108, foot_l=(8, 0), foot_r=(-26, 0),
                a_up=60, a_fore=-60, b_up=26, b_fore=-70, head=22, spine=-11.0),
}

SPIN = {
    "windup": P(torso=-80, foot_l=(36, 0), foot_r=(-54, 0),
                a_up=50, a_fore=-64, b_up=-2, b_fore=-20, head=-4, spine=-4.0),
    "active": P(torso=-58, foot_l=(80, 0), foot_r=(-58, 0),
                a_up=8, a_fore=-46, b_up=26, b_fore=26, head=6, spine=6.0),
    "defend": P(torso=-98, foot_l=(12, 0), foot_r=(-30, 0),
                a_up=48, a_fore=-66, b_up=34, b_fore=-72, head=16, spine=-8.0),
}

KICK = {
    "windup": P(torso=-86, foot_l=(32, 0), foot_r=(-56, 0),
                a_up=64, a_fore=-20, b_up=52, b_fore=-34, head=-4,
                crouch=16, spine=-5.0),
    "active": P(torso=-98, foot_l=(96, 62), foot_r=(-56, 0),
                a_up=44, a_fore=-56, b_up=60, b_fore=-26, head=-2,
                air=16, spine=4.0),
    "defend": P(torso=-112, foot_l=(6, 0), foot_r=(-24, 0),
                a_up=54, a_fore=-78, b_up=30, b_fore=-92, head=20, spine=-12.0),
}

THRUST = {
    "windup": P(torso=-72, foot_l=(26, 0), foot_r=(-58, 0),
                a_up=70, a_fore=-2, b_up=30, b_fore=-92, head=-6,
                crouch=22, spine=-3.0),
    "active": P(torso=-54, foot_l=(92, 0), foot_r=(-60, 0),
                a_up=44, a_fore=-6, b_up=-4, b_fore=-2, head=6, spine=7.0),
    "defend": P(torso=-100, foot_l=(10, 0), foot_r=(-28, 0),
                a_up=50, a_fore=-72, b_up=32, b_fore=-84, head=16, spine=-9.0),
}

PARRY = {
    "windup": P(torso=-78, foot_l=(28, 0), foot_r=(-32, 0),
                a_up=44, a_fore=-70, b_up=-4, b_fore=-16, head=-2),
    "active": P(torso=-74, foot_l=(56, 0), foot_r=(-54, 0),
                a_up=40, a_fore=-58, b_up=6, b_fore=-30, head=0),
    "defend": P(torso=-88, foot_l=(18, 0), foot_r=(-36, 0),
                a_up=58, a_fore=-40, b_up=44, b_fore=-52, head=8, spine=-6.0),
}

PRESETS = {
    "blitz_dash_slash": BLITZ,
    "rising_dragon_slash": RISING,
    "aerial_helm_breaker": AERIAL,
    "parry_riposte_spin": SPIN,
    "spartan_front_kick": KICK,
    "sonic_thrust_pierce": THRUST,
    "parry_block": PARRY,
}


@dataclass
class CombatBeat:
    """One exchange, compiled into keys by :func:`compile_beats`."""

    t: float                       # the contact frame
    attacker: str
    move: str
    defender: str | None = None
    outcome: str = "hit"           # hit | parry | lethal | whiff
    lunge: float = 150.0           # pelvis travel during the active phase, px
    from_x: float | None = None    # attacker's x at the start of the windup
    to_x: float | None = None      # attacker's x at contact (defaults to the lunge)
    defender_x: float | None = None
    defender_end_x: float | None = None
    knock: float = 120.0           # how far the defender is thrown
    jump: float = 0.0              # extra lift on the windup pose, px
    side_swap: bool = False
    windup: float = 0.26
    active: float = 0.10
    hold: float = 0.13
    recover: float = 0.34
    size: float = 1.0
    sparks: bool = False
    dust: bool = True

    @property
    def phases(self):
        t0 = self.t - self.windup
        return (t0, t0 + self.windup - 0.5 / 24.0, self.t + self.hold,
                self.t + self.hold + self.recover)


def _ease_back(x: float, d: float) -> float:
    """A small step *away* before the lunge: the coil, in root motion."""
    return x - math.copysign(d, 1.0)


#: closest the two engaged bodies may be when the blow lands, in design px
MIN_GAP = 96.0


def compile_beats(beats, tracks, *, guard, on_impact=None, on_dust=None,
                  lanes=None, waiting=None):
    """Write the four phases of every beat into the tracks.

    The tracks keep their own keys, so a beat only ever *adds* keys: the walk-in,
    the get-ups and the ending are authored by hand where they belong. The
    compiler is the only thing that decides how an attack moves.
    """
    from .poses import DOWN

    for b in sorted(beats, key=lambda q: q.t):
        pre = PRESETS[b.move]
        atk = tracks[b.attacker]
        dfd = tracks.get(b.defender) if b.defender else None
        t0, t_hit, t_out, t_back = b.phases

        start = b.from_x
        if start is None:
            start = atk.sample(t0)[1] if atk.keys else 600.0
        end = b.to_x
        if end is None:
            end = start + atk.facing * b.lunge

        wind = dict(pre["windup"])
        if b.jump:
            # ``jump`` is the *height of the leap*, not an addition to whatever
            # the preset already carried: adding them sent the hero 400 px up
            # and off the top of the frame at 10.6 s
            wind["air"] = float(b.jump)
        act = dict(pre["active"])

        # --- the attacker -------------------------------------------------
        atk.key(t0, wind, _ease_back(start, 10.0), "out")
        # 80 % of the distance inside two frames: that is the whole point
        atk.key(t_hit - 0.024, act, start + (end - start) * 0.80, "in")
        atk.key(t_out, act, end, "snap")
        atk.key(t_back, dict(guard), end + atk.facing * 10.0, "out")

        # --- the defender -------------------------------------------------
        if dfd is not None:
            dx = b.defender_x if b.defender_x is not None else dfd.sample(t0)[1]
            # two stickmen need their own air: at a gap under 90 px the heads
            # and the shoulders interpenetrate, and a beat that closes to 8 px
            # reads as one four-armed creature rather than as a fight
            gap = dx - end
            if abs(gap) < MIN_GAP:
                side = 1.0 if gap >= 0.0 else -1.0
                dx = end + side * MIN_GAP
            fx = b.defender_end_x
            if fx is None:
                fx = dx + dfd.facing * b.knock
            else:
                fx = max(dx - 320.0, min(dx + 320.0, fx))
            dfd.key(t0, dict(guard), dx, "out")
            if b.outcome == "lethal":
                dfd.key(t_hit, dict(pre["defend"]), dx, "snap")
                # a body does not *rotate* flat: it is launched, it lands, it
                # bounces, it skids, and then it is still. The ragdoll owns the
                # whole half-second, so nothing here may key over it.
                from . import ragdoll as _rag
                _rag.knockdown(dfd, t_hit, t_hit + 1.55,
                               throw=max(120.0, b.knock * 1.15),
                               power=min(2.0, 0.85 + 0.25 * b.size),
                               dust=(lambda tt: on_dust(tt)) if on_dust else None,
                               stay=True)
            else:
                dfd.key(t_hit, dict(pre["defend"]), dx, "snap")
                dfd.key(t_hit + 0.16, fade(pre["defend"], spine=-4.0),
                        dx + dfd.facing * b.knock * 0.45, "out")
                dfd.key(t_hit + 0.60, dict(guard), fx, "out")

        # --- everybody else holds his lane --------------------------------
        # The rule for a crowd: one man engages, the others are *somewhere
        # else*. Without this every fighter drifts toward the last place the
        # fight happened and three silhouettes become one.
        if lanes:
            for name, tr in tracks.items():
                if name in (b.attacker, b.defender) or name not in lanes:
                    continue
                if tr.sample(t0)[0].get("hip", 999.0) < 60.0:
                    continue                      # a body on the floor stays put
                tr.key(t0 - 0.30, dict(waiting or guard), lanes[name], "out")

        if on_impact:
            on_impact(b)
        if on_dust and b.dust:
            on_dust(b.t)
    return beats
