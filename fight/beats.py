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

#: a body closing on another body: both hands forward at neck height, weight
#: already over the front foot. This is the only pose in the set that is meant
#: to be *inside* the other man, which is why the compiler allows a 20 px gap
#: for it and nothing else.
GRAB = {
    "windup": P(torso=-74, foot_l=(52, 0), foot_r=(-44, 0),
                a_up=22, a_fore=-26, b_up=28, b_fore=-18, head=2,
                crouch=16, spine=5.0),
    "active": P(torso=-80, foot_l=(38, 0), foot_r=(-30, 0),
                a_up=-10, a_fore=-16, b_up=4, b_fore=-8, head=4,
                crouch=10, spine=9.0),
    "defend": P(torso=-96, foot_l=(20, 0), foot_r=(-40, 0),
                a_up=44, a_fore=-64, b_up=30, b_fore=-80, head=16, spine=-8.0),
}

#: the throw: arms overhead, then the whole body drops through the arc
THROW = {
    "windup": P(torso=-104, foot_l=(24, 0), foot_r=(-52, 0),
                a_up=-138, a_fore=-152, b_up=-128, b_fore=-146, head=-8,
                crouch=22, spine=-10.0),
    "active": P(torso=-44, foot_l=(74, 0), foot_r=(-58, 0),
                a_up=62, a_fore=26, b_up=44, b_fore=10, head=10,
                crouch=26, spine=12.0),
    "defend": P(torso=-70, foot_l=(30, 0), foot_r=(-44, 0),
                a_up=30, a_fore=-40, b_up=44, b_fore=-30, head=6, spine=-4.0),
}

#: the dodge: the spine arches away from the blade, the head goes back with it
WEAVE = {
    "windup": P(torso=-118, foot_l=(34, 0), foot_r=(-46, 0),
                a_up=54, a_fore=-10, b_up=40, b_fore=8, head=-14,
                crouch=8, spine=-14.0),
    "active": P(torso=-156, foot_l=(28, 0), foot_r=(-50, 0),
                a_up=64, a_fore=12, b_up=52, b_fore=26, head=-22,
                crouch=4, spine=-20.0),
    "defend": P(torso=-86, foot_l=(24, 0), foot_r=(-40, 0),
                a_up=40, a_fore=-56, b_up=34, b_fore=-44, head=8, spine=-6.0),
}

#: both men off the floor: the attacker's blade comes down from above his head
AIR_SLASH = {
    "windup": P(torso=-96, foot_l=(30, 22), foot_r=(-26, 30),
                a_up=-30, a_fore=-96, b_up=-20, b_fore=-104, head=-10,
                air=0, spine=-10.0),
    "active": P(torso=-58, foot_l=(56, 18), foot_r=(-30, 26),
                a_up=34, a_fore=-6, b_up=22, b_fore=6, head=8,
                air=0, spine=6.0),
    "defend": P(torso=-84, foot_l=(26, 20), foot_r=(-30, 26),
                a_up=40, a_fore=-58, b_up=30, b_fore=-70, head=14, spine=-6.0),
}

#: the finisher of the juggle: straight down, through the body, into the floor
AIR_SLAM = {
    "windup": P(torso=-110, foot_l=(34, 24), foot_r=(-24, 32),
                a_up=-52, a_fore=-120, b_up=-40, b_fore=-128, head=-12,
                air=0, spine=-14.0),
    "active": P(torso=-30, foot_l=(70, 0), foot_r=(-46, 0),
                a_up=76, a_fore=62, b_up=58, b_fore=44, head=14,
                crouch=18, air=0, spine=14.0),
    "defend": P(torso=-72, foot_l=(28, 0), foot_r=(-40, 0),
                a_up=36, a_fore=-50, b_up=28, b_fore=-62, head=10, spine=-4.0),
}

#: the turn-and-cut: the body leads with the back shoulder and the blade
#: follows it, which is the one move that reads as a fighter changing sides
SPIN_BACK = {
    "windup": P(torso=-98, foot_l=(20, 0), foot_r=(-46, 0),
                a_up=-6, a_fore=-30, b_up=10, b_fore=-18, head=-6, spine=-8.0),
    "active": P(torso=-52, foot_l=(72, 0), foot_r=(-54, 0),
                a_up=20, a_fore=-52, b_up=38, b_fore=18, head=8, spine=8.0),
    "defend": P(torso=-88, foot_l=(22, 0), foot_r=(-38, 0),
                a_up=46, a_fore=-58, b_up=32, b_fore=-68, head=12, spine=-6.0),
}

PRESETS = {
    "dash_collar_grab": GRAB,
    "overhead_judo_slam": THROW,
    "matrix_weave": WEAVE,
    "air_pursuit_slash": AIR_SLASH,
    "air_meteor_slam": AIR_SLAM,
    "spin_back_slash": SPIN_BACK,
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

    #: pelvis separation the beat wants at contact, in px (None = free)
    gap: float | None = None
    #: no recovery: the next beat starts from the contact pose
    chain: bool = False
    #: how far the defender is lifted off the floor by the blow, px
    launch: float = 0.0
    #: how long the defender stays up there, seconds
    hold_air: float = 0.24
    #: the attacker's own height above the floor at contact, px
    air: float = 0.0

    def gap_or(self, default: float) -> float:
        return default if self.gap is None else self.gap

    @property
    def phases(self):
        t0 = self.t - self.windup
        rec = 0.0 if self.chain else self.recover
        return (t0, t0 + self.windup - 0.5 / 24.0, self.t + self.hold,
                self.t + self.hold + rec)


def _ease_back(x: float, d: float) -> float:
    """A small step *away* before the lunge: the coil, in root motion."""
    return x - math.copysign(d, 1.0)


#: The bodies are capsules, not points. Two pelvis coordinates closer than this
#: draw two torsos and two heads in the same pixels, which is the "scrum" — so
#: the engaged pair is held at a shoulder's width whatever the beat asks for.
#: The single exception is a coreographed side swap, where one man passes the
#: other, and even then only for the frames he is actually crossing.
BODY_GAP = 34.0

#: how far apart two *waiting* rivals are held, in design px. This is a crowd
#: rule, not a combat rule: applying it to the pair that is actually fighting is
#: what made every attack a poke from medium range.
CROWD_GAP = 110.0


def compile_beats(beats, tracks, *, guard, on_impact=None, on_dust=None,
                  lanes=None, waiting=None):
    """Write the four phases of every beat into the tracks.

    The tracks keep their own keys, so a beat only ever *adds* keys: the walk-in,
    the get-ups and the ending are authored by hand where they belong. The
    compiler is the only thing that decides how an attack moves.

    Three things here exist because the first version of this fought from a
    distance and never turned:

    ``gap``     the pelvis separation the beat wants at contact. When it is set
                it wins over the authored ``defender_x``, which is how a grapple
                gets to 20 px and a dash gets to 220 px. Only a *waiting* rival
                is held off at :data:`CROWD_GAP`.
    ``chain``   no recovery. The attacker's next wind-up starts from the contact
                pose, so five beats in a row are five cuts and not five separate
                attacks with a pause between them.
    ``launch``  the defender leaves the floor by this many pixels, which is what
                an aerial juggle is: he goes up, the attacker follows him, and
                the film is off the ground for a dozen frames.
    """
    from .poses import DOWN

    #: windows in which a body is being *held* in the air by a juggle. Inside
    #: one of these every key that touches him inherits the lift, or the next
    #: beat's idle guard quietly drops him back to the floor between two hits.
    float_windows: dict[str, list[tuple[float, float, float]]] = {}

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

        # --- where the other body is --------------------------------------
        # The separation is decided here, before a single key is written, because
        # a beat asks for a *gap* (a grapple wants 20 px, a dash wants 200) and
        # the gap can put the attacker on the far side of his man.
        dx = None
        if dfd is not None:
            dx = b.defender_x if b.defender_x is not None else dfd.sample(t0)[1]
            g = max(BODY_GAP, b.gap) if b.gap is not None else None
            if g is not None:
                side = 1.0 if dx >= start else -1.0
                if b.side_swap:
                    end = dx + side * g            # through him, out the far side
                else:
                    dx = end + (1.0 if dx >= end else -1.0) * g
            elif b.side_swap:
                end = dx + (1.0 if dx >= start else -1.0) * b.gap_or(80.0)

        wind = dict(pre["windup"])
        lift = max(b.jump, b.air)
        if lift:
            # ``jump`` is the *height of the leap*, not an addition to whatever
            # the preset already carried: adding them sent the hero 400 px up
            # and off the top of the frame at 10.6 s
            wind["air"] = float(lift)
        act = dict(pre["active"])
        if b.air:
            act["air"] = float(b.air)

        # --- the attacker -------------------------------------------------
        atk.key(t0, wind, _ease_back(start, 10.0), "out")
        # 80 % of the distance inside two frames: that is the whole point
        atk.key(t_hit - 0.024, act, start + (end - start) * 0.80, "in")
        atk.key(t_out, act, end, "snap")
        if not b.chain:
            atk.key(t_back, dict(guard), end + atk.facing * 10.0, "out")

        # --- the defender -------------------------------------------------
        if dfd is not None:
            fx = b.defender_end_x
            if fx is None:
                # knocked *away from the man who hit him*, by geometry: using
                # the defender's built-in facing sent bodies flying back through
                # the attacker when the fight had already changed sides
                away = 1.0 if dx >= end else -1.0
                fx = dx + away * b.knock
            else:
                fx = max(dx - 320.0, min(dx + 320.0, fx))
            def dkey(t, pose, x, mode):
                """Key the defender, keeping whatever juggle is holding him up."""
                for w0, w1, wa in float_windows.get(dfd.name, ()):
                    if w0 - 1e-6 <= t <= w1 + 1e-6:
                        pose = dict(pose)
                        pose["air"] = max(float(pose.get("air", 0.0)), wa)
                        break
                dfd.key(t, pose, x, mode)

            dkey(t0, dict(guard), dx, "out")
            defd = dict(pre["defend"])
            if b.launch:
                defd["air"] = float(b.launch)
            dkey(t_hit, defd, dx, "snap")
            if b.launch:
                # held in the air for the juggle: two more beats happen while
                # this body is off the floor, and it must not fall back down
                air_pose = dict(pre["defend"])
                air_pose["air"] = float(b.launch)
                dkey(t_hit + max(0.10, b.hold_air), air_pose, dx + dfd.facing * 12.0,
                     "smooth")
                float_windows.setdefault(dfd.name, []).append(
                    (t_hit, t_hit + max(0.10, b.hold_air), float(b.launch)))
            if b.outcome in ("lethal", "down"):
                # the ragdoll owns this window: anything already keyed inside it
                # (a recovery from the previous beat, a later wind-up) fights the
                # flight and the body jumps backwards mid-air
                limit = t_hit + 1.55
                dfd.keys = [k for k in dfd.keys
                            if not (t_hit + 1e-6 < k[0] < limit)]
            if b.outcome == "lethal":
                # a body does not *rotate* flat: it is launched, it lands, it
                # bounces, it skids, and then it is still. The ragdoll owns the
                # whole half-second, so nothing here may key over it.
                from . import ragdoll as _rag
                _rag.knockdown(dfd, t_hit + (0.28 if b.launch else 0.0),
                               t_hit + 1.55,
                               throw=max(120.0, b.knock * 1.15),
                               power=min(2.0, 0.85 + 0.25 * b.size),
                               dust=(lambda tt: on_dust(tt)) if on_dust else None,
                               stay=True)
            elif b.outcome == "down":
                # thrown, not killed: the ragdoll owns the landing and the
                # scramble back to his feet, so nothing here keys over it
                from . import ragdoll as _rag
                _rag.knockdown(dfd, t_hit, t_hit + 1.45,
                               throw=max(150.0, b.knock),
                               power=min(1.8, 0.9 + 0.2 * b.size),
                               dust=(lambda tt: on_dust(tt)) if on_dust else None,
                               stay=False)
            elif b.chain:
                away = 1.0 if dx >= end else -1.0
                dkey(t_hit + 0.09, dict(pre["defend"]),
                     dx + away * b.knock * 0.25, "smooth")
            else:
                away = 1.0 if dx >= end else -1.0
                dkey(t_hit + 0.16, fade(pre["defend"], spine=-4.0),
                     dx + away * b.knock * 0.45, "out")
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
                # a man waiting his turn is not a statue: he shifts his
                # weight, and a lane that breathes reads as a fighter holding
                # position instead of as a prop parked on the ground
                phase = (sum(map(ord, name)) % 7) * 0.9
                sway = 16.0 * math.sin(t0 * 1.9 + phase)
                # a lane is an *offset* from the fight, not a fixed mark: a rival
                # parked on a fixed coordinate ends up standing inside whatever
                # exchange has drifted over to him, and four bodies in one place
                # is not a fight, it is a scrum
                lane = lanes[name]
                x_lane = (lane if abs(lane) > 260.0 else end + lane)
                x_lane = max(540.0, min(1230.0, x_lane))
                tr.key(t0 - 0.30, dict(waiting or guard), x_lane + sway, "out")

        if on_impact:
            on_impact(b)
        if on_dust and b.dust:
            on_dust(b.t)
    return beats
