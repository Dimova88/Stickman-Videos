"""The assembler: a battle *script* (plain data) turned into a scene.

``fight/steel.py`` used to be both the choreography and the machinery. The
machinery is here now — spacing, capsules, turns, reach, props, powers, debris,
camera — and a script module (``fight/steel_script.py``, ``fight/duel_script.py``)
supplies only the things that make a *particular* film: who is in it, what they
do, what breaks, what the camera looks at.

A script is a plain dict. Nothing in it is executable except three small
callables, which exist because they need the solved tracks:

``intro(tracks)``          keys before the first beat (the walk-in)
``after(tracks, beats)``   keys after the last beat (the walk-in out, the hold)
``props(tracks, hero, wrist, t_end)``  the object timeline

Everything else is data: ``beats``, ``cast``, ``lanes``, ``walls``, ``powers``,
``destruction``, ``titles``, ``shots``, ``ma``, ``ink``.
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
def assemble(script: dict, set_name: str = "mountain") -> dict:
    words = script.get("words", SETS).get(set_name, SETS["mountain"])
    cast = []
    for c in script["cast"]:
        tr = Track(c["name"], c.get("facing", -1), c["colour"], c["dark"])
        tr.z = float(c.get("z", 0.0))
        if c.get("weapon"):
            tr.weapon = {"len": c["weapon"], "sid": c.get("sid", 6)}
        cast.append(tr)
    hero = next(tr for tr in cast if tr.name == script.get("hero", "red"))
    foes = tuple(tr for tr in cast if tr is not hero)
    a, b, c = (foes + (hero, hero, hero))[:3]

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

    # ---------------------------------------------------------------- the cast
    # the walk-in is the script's business: the film opens on its own first
    # frame, and the assembler only needs to know the tracks exist
    script["intro"](cast)

    # ================================================================ the fight
    # The choreography arrives as data — CombatBeat objects built by the script
    # module. Each beat carries its own root motion, so the fight *travels*.
    RUN = P(torso=-72, foot_l=(34, 16), foot_r=(-28, 22),
            a_up=72, a_fore=-16, b_up=40, b_fore=-40, head=-4, air=6)
    GUARD = script.get("guard", READY)

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
    beats = list(script["beats"])
    MA = tuple(script.get("ma", ()))

    # ---- the depth lanes ------------------------------------------------
    # The arena is painted flat, so depth has to be staged: a body that is
    # "behind" the duel stands higher on the plate and is drawn smaller, and the
    # cast is split to both sides so the hero has a reason to turn. The lanes
    # live on the cast, because they are part of the script's staging.
    trim = float(script.get("trim", 2.9))
    for tr in cast:
        tr.keys = [k for k in tr.keys if k[0] <= trim]

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

    compile_beats(beats, {t.name: t for t in cast}, guard=GUARD,
                  on_impact=on_impact, on_dust=dust,
                  # offsets from the fight, not marks on the floor: a waiting
                  # rival keeps his side and drifts with the action instead of
                  # being stood on
                  lanes=script.get("lanes", {}),
                  waiting=script.get("waiting", E_GUARD))

    # ---- the rest of the authoring the script needs once the beats are in
    if script.get("after"):
        script["after"](cast, beats)

    for spec in script.get("titles", lambda w: [])(words):
        texts.append(spec)

    tracks = list(cast)
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
    # A dead body is *long*: clamped to one wall, three men thrown the same way
    # land on the same coordinate and read as one heap of limbs. Each of the
    # three has his own wall, so the pile has three heads in it.
    # The wall only moves for a man who is already down, and only from the blow
    # that put him there: a live fighter still owns the whole strip.
    #: a wall is a *mark on the floor*, so it is data: the script says where
    #: each man's body is allowed to come to rest. Anything not listed is free.
    wall = {id(tr): val for tr, val in
            ((tr, script.get("walls", {}).get(tr.name)) for tr in tracks)
            if val is not None}
    for tr in tracks:
        t_dead, right = wall.get(id(tr), (1e9, 1240.0))
        tr.keys = [(kt, kp, max(520.0, min(right if kt > t_dead else 1240.0, kx)), ke)
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

    # ---- the objects, the powers and the ground -------------------------
    # Built last on purpose: a sword leaves the *drawn* wrist of the frame it is
    # dropped on, not the authored one, so the solver has to have run first.
    from engine.weapons_and_props import WorldProp, PropField
    from engine.destruction_physics import DebrisField

    named_tracks = {tr.name: tr for tr in tracks}

    def wrist(tr, t):
        sk = tr.skel(t)
        return sk.pts[6]

    props = script["props"](named_tracks, hero, wrist, DURATION)
    prop_field = PropField(list(props), duration=DURATION, ground=GROUND)

    #: the powers are a *timeline*, not a switch: what is on screen, when, and
    #: how much of it. The renderer only samples this.
    powers = list(script.get("powers", ()))
    if callable(powers):
        powers = list(powers(named_tracks))
    destruction = list(script.get("destruction", ()))
    if callable(destruction):
        destruction = list(destruction(named_tracks))
    debris = DebrisField(destruction, ground=GROUND, duration=DURATION)

    named = {tr.name: tr for tr in tracks}
    hit_zones = sorted({b.zone for b in beats if b.zone})
    return {"set": set_name, "props": prop_field, "powers": powers,
            "hit_zones": hit_zones, "whip_lag": True,
            "debris": debris, "weapon_transitions": prop_field.transitions(), "tracks": tracks, "hero": hero, **named, "impacts": impacts, "dust": dusts,
            "beats": beats, "move_types": sorted({b.move for b in beats}),
            "turns": _turns, "engagements": engagements, "ma": MA,
            "texts": texts, "cuts": cuts,
            "blade": bool(script.get("blade", True)),
            "ink": tuple(script.get("ink", ())),
            "clock": Clock(impacts), "squash_at": squash_at,
            "push_at": push_at, "compress": compress,
            "shots": script["shots"]}
