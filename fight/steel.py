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
import os

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
    # Round 9: 26 beats, not 41. Twenty-six is what fits in thirty seconds once
    # the film is allowed to *breathe*: three Ma holds of twelve frames, and
    # every finishing blow throws its man 280-340 px clear of the duel, so the
    # centre of the frame is two bodies and not a scrum of four.
    #
    #   flurry      three cuts with no recovery between them
    #   grapple     the pair close to a shoulder's width and one is thrown
    #   pincer      one rival on each side, so the hero has to turn
    #   juggle      both men in the air, which no single beat can produce
    #   weave       a dodge inside the blade, then the counter
    def B(t, atk, move, dfd, **kw):
        return CombatBeat(t, atk, move, dfd, **kw)

    #: the Ma holds: the two men stop and look at each other before the storm.
    #: Twelve frames each, at the three places the film changes gear.
    MA = ((4.86, 5.36), (10.05, 10.55), (16.22, 16.72))

    beats = [
        # -- flurry A: three cuts, no pause, then a kick that clears the room
        B(3.90, "red", "blitz_dash_slash", "blue", gap=54, chain=True,
          from_x=700, to_x=742, size=0.9),
        B(4.08, "red", "blitz_dash_slash", "blue", gap=52, chain=True,
          from_x=742, to_x=760, size=0.9),
        B(4.26, "red", "rising_dragon_slash", "blue", gap=50, chain=True,
          from_x=760, to_x=778, size=0.95),
        B(4.52, "red", "spartan_front_kick", "blue", gap=48, knock=300.0,
          from_x=778, to_x=800, size=1.1),
        # -- grapple 1: blue gets a collar, red throws him over the shoulder
        B(6.10, "blue", "dash_collar_grab", "red", gap=30,
          from_x=760, to_x=850, size=0.9),
        B(6.52, "red", "overhead_judo_slam", "blue", gap=26, knock=330.0,
          from_x=820, to_x=846, outcome="down", size=1.1),
        # -- pincer: teal from the left, red turns and cuts back
        B(8.00, "teal", "blitz_dash_slash", "red", gap=56, knock=34.0,
          from_x=700, to_x=800, outcome="parry", size=0.95),
        B(8.30, "red", "spin_back_slash", "teal", gap=54, knock=300.0,
          from_x=846, to_x=904, size=1.15),
        # -- juggle 1: slate is lifted off the floor and finished in the air
        B(8.90, "red", "rising_dragon_slash", "slate", gap=46, launch=240.0,
          hold_air=0.50, from_x=904, to_x=940, size=1.1),
        B(9.10, "red", "air_pursuit_slash", "slate", gap=44, air=170.0,
          launch=230.0, hold_air=0.42, chain=True, from_x=940, to_x=958, size=1.0),
        B(9.38, "red", "air_meteor_slam", "slate", gap=42, air=60.0,
          knock=300.0, from_x=958, to_x=986, outcome="lethal", size=1.35),
        # -- weave and counter: the blade passes his face
        B(11.30, "red", "matrix_weave", "teal", gap=60, outcome="whiff",
          from_x=990, to_x=1000, size=0.8),
        B(11.70, "red", "sonic_thrust_pierce", "teal", gap=54, knock=190.0,
          from_x=1000, to_x=1052, size=1.1),
        # -- flurry B, the other way round, and a kick to answer it
        B(12.40, "blue", "blitz_dash_slash", "red", gap=54, chain=True,
          from_x=760, to_x=812, size=0.9),
        B(12.58, "blue", "rising_dragon_slash", "red", gap=52, chain=True,
          from_x=812, to_x=824, size=0.9),
        B(12.84, "red", "spartan_front_kick", "blue", gap=50, knock=300.0,
          from_x=824, to_x=860, size=1.05),
        # -- grapple 2: teal takes his turn to throw the hero
        B(13.90, "teal", "dash_collar_grab", "red", gap=30,
          from_x=1140, to_x=1050, size=0.95),
        B(14.32, "teal", "overhead_judo_slam", "red", gap=26, knock=330.0,
          from_x=1024, to_x=1048, outcome="down", size=1.1),
        # -- juggle 2, the last kill before the duel comes down to two men
        B(15.20, "red", "rising_dragon_slash", "teal", gap=46, launch=240.0,
          hold_air=0.50, from_x=820, to_x=880, size=1.1),
        B(15.40, "red", "air_pursuit_slash", "teal", gap=44, air=170.0,
          launch=230.0, hold_air=0.42, chain=True, from_x=880, to_x=898, size=1.0),
        B(15.68, "red", "air_meteor_slam", "teal", gap=42, air=60.0,
          knock=300.0, from_x=898, to_x=926, outcome="lethal", size=1.4),
        # -- the duel is down to two men on a cleared floor
        B(17.60, "blue", "blitz_dash_slash", "red", gap=56, knock=60.0,
          from_x=710, to_x=800, size=1.0),
        B(18.30, "red", "spin_back_slash", "blue", gap=54, knock=300.0,
          from_x=850, to_x=908, size=1.15),
        B(19.60, "red", "sonic_thrust_pierce", "blue", gap=54, knock=170.0,
          from_x=960, to_x=1014, size=1.05),
        # -- the finisher: the push-off, then the same cut three times as hard
        B(22.44, "red", "spartan_front_kick", "blue", gap=50, knock=120.0,
          from_x=1060, to_x=1086, size=0.6),
        B(23.30, "red", "blitz_dash_slash", "blue", gap=42, knock=200.0,
          from_x=1086, to_x=1170, outcome="lethal", size=1.8),
    ]

    # ---- the depth lanes ------------------------------------------------
    # The arena is painted flat, so depth has to be staged: a rival that is
    # "behind" the duel stands higher on the plate and is drawn smaller, and the
    # crowd is split to both sides so the hero has a reason to turn. The hero
    # sits a little forward of the axis, because a duel fought dead-on is two
    # silhouettes in a line and the audience cannot tell which is nearer.
    hero.z = 0.30
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

    def busy(t):
        """Who is in the exchange at ``t``: those two are allowed to be close."""
        out = set()
        for b in beats:
            if b.t - b.windup - 0.10 <= t <= b.t + 0.65:
                out.add(b.attacker)
                if b.defender:
                    out.add(b.defender)
        return out

    for _ in range(8):
        t = 0.0
        while t <= DURATION:
            hs = hero.skel(t).head
            # and the enemies must not stack into one silhouette either — but
            # only the ones *waiting*: the pair in the exchange is supposed to
            # be close, and pushing them apart is what broke every grapple
            live = busy(t)
            for i, f1 in enumerate(foes):
                for f2 in foes[i + 1:]:
                    if lie(f1, t) or lie(f2, t):
                        continue
                    if f1.name in live or f2.name in live:
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
            # the window opens on the *wind-up*, not on the contact: a fighter
            # who only turns after the blow has already been thrown is turned
            # by the hit, and the pincer arrives from a side he never looked at
            engagements.append((b.t - 0.26, b.t + 0.30, opp))
    engagements.sort()
    # an exchange ends when the next one begins: a window that runs on into the
    # following beat makes the hero "wrong" for still doing what he was told
    engagements = [(t0, min(t1, engagements[i + 1][0] - 0.02)
                    if i + 1 < len(engagements) else t1, name)
                   for i, (t0, t1, name) in enumerate(engagements)]

    # ---- the horizontal axis and the body capsule ------------------------
    # The two depend on each other: a turn is decided by where the bodies are,
    # and the push that keeps them out of each other's pixels is drawn along the
    # way a body is facing. So they are solved, in that order, twice — the second
    # pass sees the geometry the first one produced, and after that both are
    # stable to the frame.
    from . import rig as _rig
    from .beats import BODY_GAP
    from .clashfilm import pose_of as _pose_of

    def pose_y(tr, tt):
        return _pose_of(tr, tt).y

    def solve_turns():
        return _rig.drive_facings({"tracks": tracks, "hero": hero,
                                   "engagements": engagements},
                                  t0=0.0, t1=30.2)

    def solve_capsule(rounds: int = 8) -> None:
        """Two pelvises closer than BODY_GAP draw two torsos in the same pixels.

        The engaged pair is held at a shoulder's width after every other solver
        has had its turn. The push is a key inserted *on the frame that needs
        it* and on the frame grid the film is actually rendered on: inserting at
        an arbitrary time leaves the sample at the neighbouring frame
        interpolated, which is how a 34 px gap kept collapsing to 3.
        """
        for _ in range(rounds):
            f = 0
            while f / 24.0 < DURATION:
                tt = f / 24.0
                f += 1
                who = _rig.active_opponent({"engagements": engagements}, tt)
                if who is None:
                    continue
                other = by_name.get(who)
                if other is None:
                    continue
                # a body already on the floor is left alone: the capsule is
                # about two men *standing* in each other's space, not about a
                # ragdoll on its way past
                if (pose_y(hero, tt) > hero.ground_y() - 40.0
                        or pose_y(other, tt) > other.ground_y() - 40.0):
                    continue
                # the flinch is part of the body: `push_at` shoves a fighter
                # 13 px off his own keys around a contact, so a gap that is
                # 34 px on the timeline is 8 px on the screen unless counted
                hf = 1 if hero.facing_at(tt) >= 0 else -1
                of = 1 if other.facing_at(tt) >= 0 else -1
                ax = hero.sample(tt)[1] + push_at(impacts, "red", tt, hf)
                dx = other.sample(tt)[1] + push_at(impacts, other.name, tt, of)
                gap = dx - ax
                if abs(gap) >= BODY_GAP - 0.5:
                    continue
                sgn = 1.0 if gap >= 0.0 else -1.0
                pose, _ = other.sample(tt)
                other.key(tt, pose, ax + sgn * BODY_GAP, "smooth")

    # ---- the perimeter: a rival who is not in this exchange watches it from
    # outside it. Standing an idle enemy a shoulder away from the clash is what
    # turns four bodies into one knot: he is not fighting, he is queueing.
    def solve_perimeter(radius: float = 250.0) -> None:
        for tr in tracks:
            if tr is hero:
                continue
            wins = sorted((b.phases[0] - 0.45, b.phases[3] + 0.35)
                          for b in beats if tr.name in (b.attacker, b.defender))
            idle, cur = [], 0.0
            for a, b in wins:
                if a - cur > 0.50:
                    idle.append((cur + 0.05, a - 0.05))
                cur = max(cur, b)
            if DURATION - cur > 0.50:
                idle.append((cur + 0.05, DURATION - 0.10))
            def upright(tt):
                """A body on the floor is owned by the ragdoll: it may not be
                slid sideways to make room, or it skates across the arena."""
                return pose_y(tr, tt) < tr.ground_y() - 40.0

            for a, b in idle:
                mid = (a + b) * 0.5
                if not (upright(a) and upright(mid) and upright(b)):
                    continue
                xa = tr.sample(a)[1]
                xb = tr.sample(b)[1]
                if abs(tr.sample(mid)[1] - hero.sample(mid)[1]) >= radius:
                    continue
                side = 1.0 if xa >= hero.sample(a)[1] else -1.0
                pose_a = tr.sample(a)[0]
                pose_b = tr.sample(b)[0]
                tx = hero.sample(mid)[1] + side * radius
                tin = min(max(a + 0.55, a), b)
                # out to the perimeter, hold it while the duel moves under him,
                # then walk back in for his own beat
                tr.key(a, pose_a, xa, "smooth")
                tr.key(tin, pose_a, min(1160.0, max(120.0, tx)), "smooth")
                if b - 0.60 > tin:
                    tr.key(b - 0.60, pose_b,
                           min(1160.0, max(120.0, hero.sample(b - 0.60)[1] + side * radius)),
                           "smooth")
                tr.key(b, pose_b, xb, "smooth")

    solve_perimeter()
    _turns = 0
    for _ in range(2):
        _turns = solve_turns()
        solve_capsule()

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
            "turns": _turns, "engagements": engagements, "ma": MA,
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
    # -- the arena and the walk-in
    dict(t0=0.00, t1=2.30, anchor="action", zoom=0.92, z1=0.98, follow=0.30,
         dof=0.05, style="cut", ground=0.80),
    dict(t0=2.30, t1=3.70, anchor="action", zoom=1.02, z1=1.08, follow=1.0,
         dof=0.06, style="cut", ground=0.79),
    # -- the first exchange, from the ledge: you need the whole arc in frame
    dict(t0=3.70, t1=4.86, anchor="high", zoom=0.96, z1=1.02, follow=0.6,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    # -- Ma 1: the blade is held, the lens drifts in, nothing cuts
    dict(t0=4.86, t1=5.45, anchor="action", zoom=1.14, z1=1.20, follow=0.35,
         dof=0.06, style="cut", ground=0.80),
    dict(t0=5.45, t1=6.05, anchor="action", zoom=1.08, z1=1.12, follow=1.0,
         dof=0.08, style="cut", ground=0.79),
    # -- the collar grab and the judo throw, tight: this is a grapple, not a swipe
    dict(t0=6.05, t1=6.95, anchor="action", zoom=1.16, follow=1.0, dof=0.10,
         style="whip", ground=0.78, zoom_hit=0.10),
    dict(t0=6.95, t1=7.95, anchor="action", zoom=1.02, z1=1.06, follow=0.8,
         dof=0.05, style="cut", ground=0.80),
    # -- the pincer: two men at him, and the frame has to show both
    dict(t0=7.95, t1=8.65, anchor="high", zoom=0.98, z1=1.02, follow=0.7,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    # -- juggle 1: both men are off the floor, so the lens pulls out and the
    #    floor stays in shot -- the height only reads against the ground
    dict(t0=8.65, t1=9.62, anchor="air", zoom=0.90, z1=1.00, follow=1.0,
         dof=0.08, style="cut", ground=0.70),
    dict(t0=9.62, t1=10.05, anchor="down", zoom=1.34, follow=1.0, dof=0.20,
         style="whip", ground=0.74),
    # -- Ma 2
    dict(t0=10.05, t1=10.62, anchor="action", zoom=1.14, z1=1.20, follow=0.35,
         dof=0.06, style="cut", ground=0.80),
    dict(t0=10.62, t1=11.55, anchor="action", zoom=1.06, z1=1.10, follow=1.0,
         dof=0.05, style="cut", ground=0.79),
    dict(t0=11.55, t1=12.35, anchor="action", zoom=1.12, z1=1.18, follow=1.0,
         dof=0.08, style="cut", ground=0.78, zoom_hit=0.06),
    dict(t0=12.35, t1=13.30, anchor="action", zoom=1.08, z1=1.14, follow=1.0,
         dof=0.06, style="cut", ground=0.79),
    # -- grapple 2, the other way round: teal throws the hero
    dict(t0=13.30, t1=14.50, anchor="action", zoom=1.16, follow=1.0, dof=0.12,
         style="whip", ground=0.78, zoom_hit=0.09),
    dict(t0=14.50, t1=15.15, anchor="action", zoom=1.02, z1=1.06, follow=0.8,
         dof=0.05, style="cut", ground=0.80),
    # -- juggle 2
    dict(t0=15.15, t1=16.10, anchor="air", zoom=0.90, z1=1.00, follow=1.0,
         dof=0.08, style="cut", ground=0.70),
    # -- Ma 3: the last breath before it is one against one
    dict(t0=16.10, t1=16.80, anchor="action", zoom=1.16, z1=1.22, follow=0.35,
         dof=0.06, style="cut", ground=0.80),
    dict(t0=16.80, t1=17.90, anchor="action", zoom=1.04, z1=1.10, follow=0.9,
         dof=0.04, style="cut", ground=0.80),
    # -- the duel: dash, spin-back, thrust
    dict(t0=17.90, t1=19.90, anchor="action", zoom=1.12, z1=1.18, follow=1.0,
         dof=0.10, style="cut", ground=0.78, zoom_hit=0.08),
    # -- straight in on the lock: the two blades are the shot
    dict(t0=19.90, t1=21.60, anchor="action", zoom=1.06, z1=1.20, follow=1.0,
         dof=0.06, style="cut", ground=0.78, zoom_hit=0.07),
    dict(t0=21.60, t1=22.60, anchor="high", zoom=0.98, z1=1.04, follow=0.6,
         dof=0.0, style="cut", sqy=0.90, ground=0.84),
    dict(t0=22.60, t1=24.40, anchor="action", zoom=1.14, z1=1.26, follow=1.0,
         dof=0.10, style="whip", ground=0.78, zoom_hit=0.12),
    # -- tight on the body, but not so tight that the man who put it there is
    #    out of shot
    dict(t0=24.40, t1=25.90, anchor="winner", zoom=1.24, follow=1.0, dof=0.16,
         style="cut", ground=0.80),
    # -- the K.O. card needs the air above his head
    dict(t0=25.90, t1=30.20, anchor="winner", zoom=1.12, z1=1.00, follow=0.5,
         dof=0.14, style="whip", ground=0.87),
)
