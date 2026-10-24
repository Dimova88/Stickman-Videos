"""Second film: STEEL — one blade against three, 30 s.

The duel film is two fighters exchanging blows in a plane. This one is built
around the sword, so the whole thing hangs off three additions:

* a **blade** that follows the hand (``fight/steelblade.py``), so it is always
  held correctly and its angle is simply the angle of the forearm;
* a **real motion blur** driven by the camera's velocity (``fight/blur.py``), so
  the whip pans drag the picture along the path it travelled instead of being
  squashed sideways;
* **more than two bodies on screen at once.** The renderer used to say red and
  blue in a dozen places; it now says ``scene["tracks"]``, and this film is the
  reason, not a hypothetical.

The choreography is the same ``time · x · pose`` notation as the duel, written
by hand: three enemies come in one at a time, get cut down, get up, and the last
one locks blades before the finish.
"""
from __future__ import annotations

import math

from . import poses as PS
from .clash import (BLUE, BLUE_DARK, DESIGN_H, DESIGN_W, DURATION, EASE, GROUND,
                    FIG_SCALE, INK, RED, RED_DARK, STANCE, Track)
from .impact import Clock, compress, push_at, squash_at
from .poses import P, fade, to_pose

TEAL = (58, 128, 122)
TEAL_DARK = (34, 82, 78)
SLATE = (74, 78, 104)
SLATE_DARK = (44, 46, 66)

#: the hero's sword: design pixels from the back of the hand to the tip
BLADE = 132.0

SETS = {
    "mountain": {"title": "MOUNTAIN STEEL", "sub": "ONE BLADE  •  THREE MEN",
                 "hud": "MOUNTAIN  •  STEEL"},
    "desert": {"title": "DESERT STEEL", "sub": "ONE BLADE  •  THREE MEN",
               "hud": "DESERT  •  STEEL"},
}

# ============================================================== sword poses
# The blade lies along the forearm, so ``b_fore`` *is* the sword angle.
#   0   flat forward          -45  up and forward        -110  straight up
#   40  down and forward      -90  vertical, guard high
LOW = P(torso=-80, foot_l=(30, 0), foot_r=(-32, 0),
        a_up=64, a_fore=-26, b_up=70, b_fore=32, head=-2)
READY = P(torso=-78, foot_l=(28, 0), foot_r=(-34, 0),
          a_up=58, a_fore=-40, b_up=44, b_fore=-52, head=0)
HIGH = P(torso=-74, foot_l=(34, 0), foot_r=(-30, 0),
         a_up=48, a_fore=-60, b_up=-30, b_fore=-104, head=-4)
OVER = P(torso=-70, foot_l=(40, 0), foot_r=(-24, 0),
         a_up=36, a_fore=-30, b_up=-46, b_fore=-124, head=-6)
# the cutting poses put the *blade* where it has to be: forearm near level for
# a flat cut, up for the diagonal, down for the low one
CUT = P(torso=-62, foot_l=(52, 0), foot_r=(-20, 0),
        a_up=52, a_fore=-18, b_up=-14, b_fore=-4, head=2)
CUT_HI = P(torso=-66, foot_l=(46, 0), foot_r=(-24, 0),
           a_up=44, a_fore=-24, b_up=-26, b_fore=-27, head=0)
CUT_LO = P(torso=-56, foot_l=(54, 0), foot_r=(-18, 0),
           a_up=60, a_fore=6, b_up=14, b_fore=40, head=4)
SPIN = P(torso=-58, foot_l=(44, 0), foot_r=(-26, 0),
         a_up=10, a_fore=-40, b_up=20, b_fore=8, head=0)
# the parry is a level blade thrown up to meet an incoming edge, not a raised one
PARRY = P(torso=-76, foot_l=(26, 0), foot_r=(-34, 0),
          a_up=44, a_fore=-70, b_up=-4, b_fore=-16, head=-2)
PARRY_LOW = P(torso=-70, foot_l=(30, 0), foot_r=(-32, 0),
              a_up=54, a_fore=-30, b_up=62, b_fore=20, head=0)
LOCK = P(torso=-70, foot_l=(36, 0), foot_r=(-28, 0),
         a_up=40, a_fore=-54, b_up=-2, b_fore=-24, head=-2)
PUSH = P(torso=-64, foot_l=(48, 0), foot_r=(-22, 0),
         a_up=30, a_fore=-40, b_up=-6, b_fore=-30, head=2)
DUCK = P(torso=-64, foot_l=(34, 0), foot_r=(-34, 0), crouch=26,
         a_up=56, a_fore=-52, b_up=20, b_fore=-70, head=6)

# enemies: a sword held forward in a two-hand-ish guard, and a chop
E_GUARD = P(torso=-78, foot_l=(32, 0), foot_r=(-30, 0),
            a_up=52, a_fore=-56, b_up=-10, b_fore=-58, head=0)
E_CHOP = P(torso=-64, foot_l=(48, 0), foot_r=(-22, 0),
           a_up=50, a_fore=-22, b_up=-26, b_fore=-104, head=-2)
E_CHOP_END = P(torso=-60, foot_l=(52, 0), foot_r=(-20, 0),
               a_up=54, a_fore=-14, b_up=34, b_fore=34, head=2)
E_STAG = P(torso=-96, foot_l=(20, 0), foot_r=(-38, 0),
           a_up=66, a_fore=-40, b_up=30, b_fore=-24, head=10)
E_BACK = P(torso=-70, foot_l=(24, 0), foot_r=(-40, 0), crouch=8,
           a_up=62, a_fore=-30, b_up=40, b_fore=-30, head=4)

# ===================================================================== build
def build(set_name: str = "mountain") -> dict:
    words = SETS.get(set_name, SETS["mountain"])
    hero = Track("red", 1, RED, RED_DARK)
    hero.weapon = {"len": BLADE, "sid": 6}
    a = Track("blue", -1, BLUE, BLUE_DARK)
    b = Track("teal", -1, TEAL, TEAL_DARK)
    c = Track("slate", -1, SLATE, SLATE_DARK)
    # only the rival carries steel. Three swords in one frame is a thicket of
    # white bars; one blade against three men is also the better story
    foes = (a, b, c)
    a.weapon = {"len": BLADE * 0.90, "sid": 6}

    impacts: list[dict] = []
    dusts: list[float] = []
    texts: list[dict] = []

    def impact(t, kind, size=1.0, by="red", on=None, dmg=0.0, sparks=False):
        dx = 1.0 if by == "red" else -1.0
        impacts.append({"t": t, "kind": kind, "size": size, "by": by,
                        "on": on, "dx": dx, "sparks": sparks,
                        "dmg_red": dmg if on == "red" else 0.0,
                        "dmg_blue": dmg if on and on != "red" else 0.0,
                        "anchor": "blade" if sparks else None})

    def dust(t):
        dusts.append(t)

    def title(t0, t1, text, style="plain"):
        texts.append({"t0": t0, "t1": t1, "text": text, "style": style})

    # ------------------------------------------------------------ 0-3.4 walk in
    hero.key(0.0, LOW, 566)
    a.key(0.0, E_GUARD, 1180)
    b.key(0.0, E_GUARD, 1268)
    c.key(0.0, E_GUARD, 1348)
    hero.key(1.10, fade(LOW, torso=-82), 578, "out")
    a.key(1.30, fade(E_GUARD, torso=-82), 940, "out")
    b.key(1.55, fade(E_GUARD, torso=-82), 1052, "out")
    c.key(1.80, fade(E_GUARD, torso=-82), 1150, "out")
    hero.key(2.20, READY, 596, "out")
    a.key(2.40, E_GUARD, 900, "out")
    b.key(2.60, E_GUARD, 1096, "out")
    c.key(2.80, E_GUARD, 1216, "out")
    hero.key(3.10, HIGH, 612, "snap")

    # ================================================================ the fight
    # Twenty seconds of choreography, compiled from CombatBeat objects instead
    # of typed key by key (fight/beats.py). Each beat carries its own root
    # motion, so the fight *travels*: the hero covers the arena, jumps an arc
    # over a man, cuts back through the group and finishes on the far side.
    RUN = P(torso=-72, foot_l=(34, 16), foot_r=(-28, 22),
            a_up=72, a_fore=-16, b_up=40, b_fore=-40, head=-4, air=6)
    GUARD = READY

    def travel(tr, t0, t1, x0, x1):
        """A dash between exchanges: the feet are stepped by the footwork pass."""
        tr.key(t0, RUN, x0, "out")
        tr.key(t1, RUN, x1, "in")

    from .beats import CombatBeat, compile_beats

    # ---- the exchanges ------------------------------------------------
    # Round 8: the film is no longer a list of single blows. Each exchange is a
    # *pattern* with its own rhythm, its own distance and its own geometry:
    #
    #   flurry      five cuts with no recovery between them
    #   grapple     the pair closes to a hand's width and one man is thrown
    #   pincer      one rival on each side, so the hero has to turn
    #   juggle      both men in the air, which no single beat can produce
    #   weave       a dodge with a counter, in the middle of the blade
    def B(t, atk, move, dfd, **kw):
        return CombatBeat(t, atk, move, dfd, **kw)

    beats = [
        # -- A. flurry_clash_barrage: five contacts, no pause between them ----
        B(3.58, "red", "blitz_dash_slash", "blue", gap=56, chain=True,
          from_x=700, to_x=740, size=0.9),
        B(3.76, "red", "blitz_dash_slash", "blue", gap=54, chain=True,
          from_x=740, to_x=756, size=0.9),
        B(3.94, "red", "rising_dragon_slash", "blue", gap=52, chain=True,
          from_x=756, to_x=772, size=0.9),
        B(4.12, "red", "blitz_dash_slash", "blue", gap=54, chain=True,
          from_x=772, to_x=788, size=0.9),
        B(4.36, "red", "spartan_front_kick", "blue", gap=58, knock=100.0,
          from_x=788, to_x=800, size=1.0),
        # -- B. close_grapple_throw: collar grab, then a judo throw ---------
        B(4.86, "blue", "dash_collar_grab", "red", gap=34,
          from_x=900, to_x=830, size=0.9, dust=True),
        B(5.28, "red", "overhead_judo_slam", "blue", gap=20, knock=250.0,
          from_x=806, to_x=830, outcome="down", size=1.0),
        # -- C. pincer_ambush_pingpong: one on each side --------------------
        B(5.96, "teal", "blitz_dash_slash", "red", gap=58,
          from_x=700, to_x=768, outcome="parry", knock=30.0, size=0.9),
        B(6.30, "slate", "blitz_dash_slash", "red", gap=56,
          from_x=1120, to_x=940, outcome="parry", knock=30.0, size=0.9),
        B(6.66, "red", "spin_back_slash", "slate", gap=50, knock=160.0,
          from_x=830, to_x=886, defender_x=930, side_swap=True, size=1.1),
        # -- D. aerial_juggle_slam: off the floor, both of them ------------
        B(7.22, "red", "rising_dragon_slash", "slate", gap=48, launch=140.0,
          hold_air=0.40, from_x=886, to_x=930, size=1.1),
        B(7.48, "red", "air_pursuit_slash", "slate", gap=44, air=104.0,
          launch=124.0, hold_air=0.30, chain=True, from_x=930, to_x=948,
          size=1.0),
        B(7.68, "red", "air_pursuit_slash", "slate", gap=42, air=96.0,
          launch=104.0, hold_air=0.24, chain=True, from_x=948, to_x=964,
          size=1.0),
        B(7.96, "red", "air_meteor_slam", "slate", gap=40, air=40.0,
          knock=190.0, from_x=964, to_x=990, outcome="lethal", size=1.3),
        # -- E. matrix_weave_counter: the blade passes his face ------------
        B(8.84, "red", "matrix_weave", "teal", gap=66, outcome="whiff",
          from_x=990, to_x=1000, size=0.8),
        B(9.24, "red", "sonic_thrust_pierce", "teal", gap=58, knock=90.0,
          from_x=1000, to_x=1050, size=1.1),
        # -- F. flurry_clash_barrage, the other way round -------------------
        B(9.96, "blue", "blitz_dash_slash", "red", gap=54, chain=True,
          from_x=700, to_x=760, size=0.85),
        B(10.12, "blue", "blitz_dash_slash", "red", gap=52, chain=True,
          from_x=760, to_x=772, size=0.85),
        B(10.28, "blue", "rising_dragon_slash", "red", gap=54, chain=True,
          from_x=772, to_x=784, size=0.85),
        B(10.44, "blue", "blitz_dash_slash", "red", gap=52, chain=True,
          from_x=784, to_x=796, size=0.85),
        B(10.70, "red", "spartan_front_kick", "blue", gap=56, knock=110.0,
          from_x=800, to_x=838, size=1.0),
        # -- G. the second grapple: teal throws the hero -------------------
        B(11.40, "teal", "dash_collar_grab", "red", gap=34,
          from_x=1100, to_x=1020, size=0.95),
        B(11.86, "teal", "overhead_judo_slam", "red", gap=20, knock=250.0,
          from_x=1044, to_x=1068, outcome="down", size=1.0),
        # -- H. the second juggle, and the second kill ---------------------
        B(13.30, "red", "rising_dragon_slash", "teal", gap=46, launch=140.0,
          hold_air=0.36, from_x=800, to_x=880, size=1.1),
        B(13.52, "red", "air_pursuit_slash", "teal", gap=44, air=104.0,
          launch=122.0, hold_air=0.28, chain=True, from_x=880, to_x=898,
          size=1.0),
        B(13.72, "red", "air_pursuit_slash", "teal", gap=42, air=96.0,
          launch=104.0, hold_air=0.22, chain=True, from_x=898, to_x=912,
          size=1.0),
        B(14.04, "red", "air_meteor_slam", "teal", gap=40, air=40.0,
          knock=210.0, from_x=912, to_x=940, outcome="lethal", size=1.35),
        # -- I. the last third: singles, then another pincer ---------------
        B(15.30, "slate", "blitz_dash_slash", "red", gap=58,
          from_x=1180, to_x=1060, size=1.0),
        B(16.00, "red", "parry_riposte_spin", "slate", gap=50, knock=150.0,
          from_x=980, to_x=1030, size=1.1),
        B(17.10, "blue", "blitz_dash_slash", "red", gap=56,
          from_x=700, to_x=770, size=1.0),
        B(17.80, "red", "spartan_front_kick", "blue", gap=54, knock=90.0,
          from_x=790, to_x=826, size=1.0),
        B(18.50, "slate", "blitz_dash_slash", "red", gap=56,
          from_x=1120, to_x=1000, outcome="parry", knock=28.0, size=0.9),
        B(18.82, "blue", "blitz_dash_slash", "red", gap=54,
          from_x=700, to_x=790, outcome="parry", knock=28.0, size=0.9),
        B(19.30, "red", "spin_back_slash", "slate", gap=48, knock=140.0,
          from_x=850, to_x=906, defender_x=900, side_swap=True, size=1.1),
        B(20.28, "red", "blitz_dash_slash", "blue", gap=52, chain=True,
          from_x=880, to_x=920, size=0.9),
        B(20.46, "red", "blitz_dash_slash", "blue", gap=50, chain=True,
          from_x=920, to_x=940, size=0.9),
        B(20.64, "red", "rising_dragon_slash", "blue", gap=52, chain=True,
          from_x=940, to_x=960, size=0.9),
        B(20.90, "red", "spartan_front_kick", "blue", gap=56, knock=120.0,
          from_x=960, to_x=1000, size=1.05),
        B(21.90, "red", "sonic_thrust_pierce", "blue", gap=56, knock=80.0,
          from_x=1010, to_x=1064, size=1.0),
        # -- the finisher: the same cut as the opening, three times as hard
        B(22.44, "red", "spartan_front_kick", "blue", gap=54, knock=30.0,
          from_x=1060, to_x=1094, size=0.5),
        B(23.30, "red", "blitz_dash_slash", "blue", gap=44, knock=180.0,
          from_x=1094, to_x=1184, outcome="lethal", size=1.8),
    ]

    # ---- the depth lanes ------------------------------------------------
    # The arena is painted flat, so depth has to be staged: a rival that is
    # "behind" the duel stands higher on the plate and is drawn smaller. Without
    # this the four men are a row of cardboard cut-outs on one line.
    hero.z = 0.0
    a.z = -0.85          # blue, stalking from the back
    b.z = 0.45           # teal, half a step towards the lens
    c.z = -0.35          # slate, between the two

    for tr in (hero, a, b, c):
        tr.keys = [k for k in tr.keys if k[0] <= 2.9]

    STEEL_CUTS = {"blitz_dash_slash", "parry_riposte_spin", "spin_back_slash"}
    BLUNT = {"spartan_front_kick", "sonic_thrust_pierce", "rising_dragon_slash",
             "overhead_judo_slam", "air_meteor_slam", "dash_collar_grab",
             "air_pursuit_slash"}

    def kind_of(beat):
        """What a beat sounds and sparks like, derived from the move itself.

        The old table had to be kept in step with the choreography by hand, and
        the moment the beat sheet changed it pointed at the wrong times. The move
        now decides: steel on steel rings, a kick thuds, a grab is a body.
        """
        if beat.outcome == "whiff":
            return None
        if beat.outcome == "lethal":
            return ("final", False)
        if beat.outcome == "parry":
            return ("clash", True)
        if beat.move in STEEL_CUTS:
            return ("clash", True)
        if beat.move in BLUNT:
            return ("hit", False)
        return ("hit", False)

    def on_impact(beat):
        k = kind_of(beat)
        if k is None:
            return
        kind, sparks = k
        on = beat.defender if beat.outcome != "parry" else beat.attacker
        by = beat.attacker if beat.outcome != "parry" else beat.defender
        impact(beat.t, kind, beat.size, by=by or "red", on=on, sparks=sparks,
               dmg=100.0 if beat.outcome == "lethal" else 18.0 * beat.size)

    compile_beats(beats, {t.name: t for t in (hero, a, b, c)}, guard=GUARD,
                  on_impact=on_impact, on_dust=dust,
                  # one rival waits on each side of the arena: a crowd all on
                  # one side is a chorus line, and it also means the hero never
                  # has to turn round
                  # offsets from the fight, not marks on the floor: blue keeps
                  # the left side, teal and slate the right, and they drift with
                  # the action instead of being stood on
                  lanes={"blue": -350.0, "teal": 330.0, "slate": 430.0},
                  waiting=E_GUARD)

    # the walk-in ends where the first beat begins
    hero.key(3.40, READY, 596, "out")
    a.key(3.40, E_GUARD, 588, "out")
    b.key(3.40, E_GUARD, 1152, "out")
    c.key(3.40, E_GUARD, 1228, "out")
    a.key(3.60, E_GUARD, 700, "out")
    hero.key(24.20, READY, 1214, "out")

    # ------------------------------------------------------ 24.2-30 the sword
    hero.key(25.10, fade(READY, torso=-84), 716, "out")
    hero.key(26.40, fade(LOW, b_fore=8), 712, "out")
    hero.key(28.60, fade(LOW, b_fore=6, torso=-86), 708, "smooth")

    title(25.34, 26.95, "K.O.", "ko")
    title(26.95, 29.30, "RED WINS", "title")
    title(26.70, 29.40, words["sub"], "sub")
    title(0.0, 30.0, words["hud"], "hud")

    tracks = [hero, a, b, c]
    # ---- spacing: the enemies never walk into the hero, the hero never walks
    # into them, and a body on the floor is not moved at all
    for tr in tracks:
        tr._kd = ()

    def lie(tr, t):
        return tr.sample(t)[0].get("hip", 999.0) < 95.0

    for _ in range(8):
        t = 0.0
        while t <= DURATION:
            hs = hero.skel(t).head
            # and the enemies must not stack into one silhouette either
            for i, f1 in enumerate(foes):
                for f2 in foes[i + 1:]:
                    if lie(f1, t) or lie(f2, t):
                        continue
                    d = abs(f2.skel(t).head[0] - f1.skel(t).head[0])
                    if d < 168.0:
                        push = (168.0 - d) * 0.25
                        for tr, sgn in ((f1, -1.0), (f2, 1.0)):
                            ks = tr.keys
                            best = min(range(len(ks)), key=lambda i: abs(ks[i][0] - t))
                            if abs(ks[best][0] - t) > 0.35:
                                continue
                            kt, kp, kx, ke = ks[best]
                            ks[best] = (kt, kp, kx + sgn * push, ke)
            t += 0.1

    # ---- and nobody leaves the painted arena: every key is clamped to the
    # strip of ground the plate actually covers
    for tr in tracks:
        tr.keys = [(kt, kp, max(520.0, min(1240.0, kx)), ke)
                   for kt, kp, kx, ke in tr.keys]

    # ---- reach: step the attacker in until the *tip* is on the target
    #
    # The blade is two feet of steel: a pose can be perfect and still miss the
    # head by the length of the sword. Rather than hand-tuning 40 keys, each
    # contact is solved the way the duel solves a punch — but on the tip, with
    # the step capped by the spacing that is left, so the pair can never be
    # walked off the frame by an unreachable contact.
    def nearest(tr, t):
        ks = tr.keys
        i = min(range(len(ks)), key=lambda k: abs(ks[k][0] - t))
        return i if abs(ks[i][0] - t) < 0.6 else None

    def tip_at(sk, scale=0.90):
        a = sk.tip_angle(6)
        return (sk.pts[6][0] + math.cos(a) * BLADE * scale,
                sk.pts[6][1] + math.sin(a) * BLADE * scale)

    by_name = {tr.name: tr for tr in tracks}
    for _ in range(6):
        for e in impacts:
            if e.get("on") is None:
                continue
            t = e["t"]
            own, tgt_tr = by_name[e["by"]], by_name[e["on"]]
            own_sk, tgt_sk = own.skel(t), tgt_tr.skel(t)
            if e["kind"] == "clash":
                a = tgt_sk.tip_angle(6)
                target = (tgt_sk.pts[6][0] + math.cos(a) * BLADE * 0.72,
                          tgt_sk.pts[6][1] + math.sin(a) * BLADE * 0.72)
                want = 10.0
            else:
                target = tgt_sk.head
                want = 40.0
            tip = tip_at(own_sk)
            d = math.hypot(target[0] - tip[0], target[1] - tip[1])
            if d <= want + 4.0:
                continue
            gap = abs(tgt_sk.head[0] - own_sk.head[0])
            room = max(0.0, gap - 176.0)
            step = min((d - want) * 0.35, room * 0.42, 16.0)
            if step <= 0.5:
                continue
            i = nearest(own, t)
            if i is None:
                continue
            kt, kp, kx, ke = own.keys[i]
            own.keys[i] = (kt, kp, kx + step * own.facing, ke)

    # ---- who is the hero actually trading with, beat by beat
    engagements = []
    for b in beats:
        opp = None
        if b.attacker == "red":
            opp = b.defender
        elif b.defender == "red":
            opp = b.attacker
        if opp:
            # the window is the contact, not the whole beat: during the wind-up
            # of the *next* attack the hero is still dealing with this one, and
            # a window that starts at the wind-up has both men "active" at once
            engagements.append((b.t - 0.14, b.t + 0.30, opp))
    engagements.sort()
    # an exchange ends when the next one begins: a window that runs on into the
    # following beat makes the hero "wrong" for still doing what he was told
    engagements = [(t0, min(t1, engagements[i + 1][0] - 0.02)
                    if i + 1 < len(engagements) else t1, name)
                   for i, (t0, t1, name) in enumerate(engagements)]

    # ---- the horizontal axis: every turn is decided by where the bodies are
    from . import rig as _rig
    _turns = _rig.drive_facings({"tracks": tracks, "hero": hero,
                                 "engagements": engagements},
                                t0=0.0, t1=30.2)

    # ---- impact positions: where the steel meets
    for e in impacts:
        t = e["t"]
        sk = {tr.name: tr.skel(t) for tr in tracks}
        col = {tr.name: tr.colour for tr in tracks}
        own = sk[e["by"]]
        tgt = sk[e["on"]] if e.get("on") in sk else None
        if tgt is None:
            continue
        tip = (own.pts[6][0] + math.cos(own.tip_angle(6)) * BLADE * 0.62,
               own.pts[6][1] + math.sin(own.tip_angle(6)) * BLADE * 0.62)
        if e["kind"] == "clash":
            otip = (tgt.pts[6][0] + math.cos(tgt.tip_angle(6)) * BLADE * 0.62,
                    tgt.pts[6][1] + math.sin(tgt.tip_angle(6)) * BLADE * 0.62)
            e["x"] = (tip[0] + otip[0]) * 0.5
            e["y"] = (tip[1] + otip[1]) * 0.5
        else:
            e["x"] = (tip[0] * 0.55 + tgt.head[0] * 0.45)
            e["y"] = (tip[1] * 0.55 + tgt.head[1] * 0.45)
        e["colour"] = col[e["by"]]

    # No face inserts: the accent on these two blows is the ink frame, not a cut
    cuts = ()

    named = {tr.name: tr for tr in tracks}
    return {"set": set_name, "tracks": tracks, "hero": hero, **named, "impacts": impacts, "dust": dusts,
            "beats": beats, "move_types": sorted({b.move for b in beats}),
            "turns": _turns, "engagements": engagements,
            "texts": texts, "cuts": cuts, "blade": True,
            "ink": (16.90, 23.30),
            "clock": Clock(impacts), "squash_at": squash_at,
            "push_at": push_at, "compress": compress,
            "shots": SHOTS_STEEL}


# ==================================================================== camera
# Thirteen shots for the blade film: the sword needs air around it, so the
# standard cut is a little wider than the duel's, and the whip pans land on the
# clashes — that is where the steel rings.
SHOTS_STEEL = (
    dict(t0=0.00, t1=2.30, anchor="action", zoom=0.92, z1=0.98, follow=0.30,
         dof=0.05, style="cut", ground=0.80),
    dict(t0=2.30, t1=3.70, anchor="action", zoom=1.02, z1=1.08, follow=1.0,
         dof=0.06, style="cut", ground=0.79),
    # the first exchange, from the ledge: you need the whole arc in frame
    dict(t0=3.70, t1=5.40, anchor="high", zoom=0.96, z1=1.02, follow=0.6,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    dict(t0=5.40, t1=6.10, anchor="action", zoom=1.10, z1=1.14, follow=1.0,
         dof=0.08, style="cut", ground=0.79),
    dict(t0=6.10, t1=6.90, anchor="action", zoom=1.16, follow=1.0, dof=0.10,
         style="whip", ground=0.78, zoom_hit=0.10),
    # the juggle: both men are off the floor, so framing them on the ground
    # line cuts their heads off — the camera goes up with them
    dict(t0=6.90, t1=8.10, anchor="air", zoom=0.86, z1=0.94, follow=1.0,
         dof=0.08, style="cut", ground=0.68),
    dict(t0=8.10, t1=9.60, anchor="action", zoom=1.00, z1=1.06, follow=0.8,
         dof=0.05, style="cut", ground=0.80),
    dict(t0=9.60, t1=11.40, anchor="down", zoom=1.30, follow=1.0, dof=0.18,
         style="whip", ground=0.74),
    dict(t0=13.16, t1=14.20, anchor="air", zoom=0.86, z1=0.96, follow=1.0,
         dof=0.08, style="cut", ground=0.68),
    dict(t0=11.40, t1=13.16, anchor="action", zoom=1.04, z1=1.12, follow=1.0,
         dof=0.05, style="cut", ground=0.79),
    dict(t0=14.20, t1=16.40, anchor="action", zoom=0.94, z1=1.00, follow=0.8,
         dof=0.0, style="cut", ground=0.80),
    dict(t0=16.40, t1=17.60, anchor="high", zoom=0.98, z1=1.04, follow=0.6,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    dict(t0=17.60, t1=19.60, anchor="action", zoom=1.12, z1=1.18, follow=1.0,
         dof=0.10, style="cut", ground=0.78, zoom_hit=0.08),
    # straight in on the lock: the two blades are the shot, so the lens goes to
    # them rather than to a fist -- and it cuts, because a whip here would smear
    # the very frame where the steel meets
    dict(t0=19.60, t1=21.20, anchor="action", zoom=1.06, z1=1.22, follow=1.0,
         dof=0.06, style="cut", ground=0.78, zoom_hit=0.07),
    dict(t0=21.20, t1=22.90, anchor="action", zoom=1.06, z1=1.12, follow=1.0,
         dof=0.06, style="cut", ground=0.79),
    dict(t0=22.90, t1=24.40, anchor="action", zoom=1.18, z1=1.26, follow=1.0,
         dof=0.10, style="whip", ground=0.78, zoom_hit=0.12),
    # tight on the body, but not so tight that the man who put it there is out
    # of shot: at 1.40 the winner was cropped and the beat had no author
    dict(t0=24.40, t1=25.90, anchor="winner", zoom=1.24, follow=1.0, dof=0.16,
         style="cut", ground=0.80),
    # the winner shot sits low: the K.O. card needs the air above his head
    dict(t0=25.90, t1=30.20, anchor="winner", zoom=1.12, z1=1.00, follow=0.5,
         dof=0.14, style="whip", ground=0.87),
)
