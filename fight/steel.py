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
    b.key(2.60, E_GUARD, 986, "out")
    c.key(2.80, E_GUARD, 1064, "out")
    hero.key(3.10, HIGH, 612, "snap")

    # ------------------------------------------------------- 3.4-6.2 first cut
    # A rushes, the swords meet, and the hero's counter takes it down
    a.key(3.60, E_CHOP, 852, "in")
    hero.key(3.92, PARRY, 620, "snap")
    a.key(4.06, E_CHOP_END, 806, "snap")
    impact(3.96, "clash", 1.15, by="blue", on="red", sparks=True)
    hero.key(4.24, OVER, 622, "out")
    a.key(4.30, E_STAG, 806, "out")
    hero.key(4.62, CUT, 634, "snap")
    a.key(4.66, PS.HIT_HEAD, 812, "snap")
    impact(4.64, "hit", 1.0, by="red", on="blue", dmg=34.0)
    a.key(5.10, PS.FALL, 826, "out")
    a.key(5.56, PS.DOWN, 842, "out")
    dust(5.60)
    hero.key(5.10, READY, 628, "out")

    # ------------------------------------------------------ 5.6-8.6 the duck
    b.key(5.60, E_CHOP, 928, "in")
    hero.key(6.10, DUCK, 640, "snap")
    b.key(6.16, E_CHOP_END, 890, "snap")
    impact(6.14, "block", 0.55, by="teal", on="red")
    hero.key(6.44, CUT_HI, 646, "snap")
    b.key(6.46, PS.HIT_HEAD, 894, "snap")
    impact(6.44, "hit", 0.95, by="red", on="teal", dmg=30.0)
    b.key(6.90, PS.FALL, 912, "out")
    b.key(7.36, PS.DOWN, 928, "out")
    dust(7.40)
    hero.key(7.10, READY, 640, "out")

    # ------------------------------------------------- 7.4-11.4 two parries
    c.key(7.20, E_CHOP, 1002, "in")
    hero.key(7.70, PARRY, 646, "snap")
    c.key(7.84, E_CHOP_END, 964, "snap")
    impact(7.74, "clash", 1.0, by="slate", on="red", sparks=True)
    hero.key(8.00, PARRY_LOW, 648, "snap")
    c.key(8.30, E_CHOP, 952, "snap")
    impact(8.32, "clash", 0.95, by="slate", on="red", sparks=True)
    hero.key(8.60, OVER, 650, "out")
    c.key(8.68, E_STAG, 958, "out")
    hero.key(9.10, CUT_LO, 660, "snap")
    c.key(9.12, PS.HIT_BODY, 962, "snap")
    impact(9.10, "hit", 1.05, by="red", on="slate", dmg=40.0)
    c.key(9.60, PS.FALL, 976, "out")
    c.key(10.10, PS.DOWN, 992, "out")
    dust(10.12)
    hero.key(9.70, READY, 652, "out")

    # ------------------------------------------------- 10.1-13.6 back up again
    a.key(10.60, PS.KNEEL, 848, "out")
    a.key(11.30, E_GUARD, 836, "out")
    b.key(11.60, PS.KNEEL, 936, "out")
    b.key(12.30, E_GUARD, 924, "out")
    a.key(12.60, E_CHOP, 812, "in")
    hero.key(12.90, PARRY, 656, "snap")
    a.key(13.04, E_CHOP_END, 790, "snap")
    impact(12.94, "clash", 1.0, by="blue", on="red", sparks=True)
    hero.key(13.20, SPIN, 662, "out")
    hero.key(13.60, CUT, 676, "snap")
    a.key(13.62, PS.HIT_BODY, 796, "snap")
    impact(13.60, "hit", 1.1, by="red", on="blue", dmg=45.0)
    a.key(14.10, PS.FALL, 812, "out")
    a.key(14.60, PS.DOWN, 828, "out")
    dust(14.62)
    hero.key(14.10, READY, 674, "out")

    # ------------------------------------------- 14.6-19.7 two of them at once
    b.key(14.80, E_CHOP, 900, "in")
    c.key(15.20, E_GUARD, 1000, "out")
    hero.key(15.30, PARRY, 682, "snap")
    b.key(15.44, E_CHOP_END, 872, "snap")
    impact(15.34, "clash", 1.0, by="teal", on="red", sparks=True)
    c.key(15.60, E_CHOP, 992, "in")
    hero.key(16.00, PARRY_LOW, 688, "snap")
    c.key(16.14, E_CHOP_END, 956, "snap")
    impact(16.04, "clash", 1.0, by="slate", on="red", sparks=True)
    # the wide one: both of them in the same arc
    hero.key(16.40, SPIN, 694, "out")
    hero.key(16.90, CUT_HI, 712, "snap")
    b.key(16.90, PS.HIT_HEAD, 884, "snap")
    c.key(16.94, PS.HIT_HEAD, 962, "snap")
    impact(16.90, "hit", 1.25, by="red", on="teal", dmg=60.0)
    impact(16.92, "hit", 1.25, by="red", on="slate", dmg=60.0)
    b.key(17.40, PS.FALL, 902, "out")
    b.key(17.86, PS.DOWN, 918, "out")
    c.key(17.50, PS.FALL, 980, "out")
    c.key(18.00, PS.DOWN, 996, "out")
    dust(17.90)
    hero.key(17.60, READY, 700, "out")

    # --------------------------------------------------------- 18.0-25 the last
    a.key(18.30, PS.KNEEL, 864, "out")
    a.key(19.10, E_GUARD, 856, "out")
    a.key(19.60, E_CHOP, 828, "in")
    hero.key(19.90, LOCK, 692, "snap")
    a.key(19.94, LOCK, 812, "snap")
    impact(19.92, "clash", 1.05, by="blue", on="red", sparks=True)
    hero.key(20.60, PUSH, 700, "out")
    a.key(20.66, fade(E_STAG, torso=-72), 824, "out")
    hero.key(21.10, OVER, 704, "out")
    a.key(21.10, E_GUARD, 836, "out")
    hero.key(21.90, HIGH, 708, "out")
    a.key(22.10, E_CHOP, 852, "in")
    hero.key(22.40, fade(DUCK, torso=-72), 712, "snap")
    a.key(22.46, E_CHOP_END, 820, "snap")
    impact(22.44, "block", 0.5, by="blue", on="red")
    hero.key(22.80, OVER, 716, "out")
    a.key(22.86, E_STAG, 824, "out")
    hero.key(23.30, CUT, 726, "snap")
    a.key(23.32, PS.HIT_HEAD, 832, "snap")
    impact(23.30, "final", 1.8, by="red", on="blue", dmg=100.0)
    a.key(23.90, PS.FALL, 858, "out")
    a.key(24.60, PS.DOWN, 884, "out")
    dust(24.64)
    hero.key(24.20, READY, 720, "out")

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
            for f in foes:
                if lie(f, t):
                    continue
                gap = f.skel(t).head[0] - hs[0]
                want = 196.0 if t < 24.0 else 260.0
                if gap < want:
                    push = (want - gap) * 0.25
                    for tr, sgn in ((hero, -1.0), (f, 1.0)):
                        if lie(tr, t):
                            continue
                        ks = tr.keys
                        best = min(range(len(ks)), key=lambda i: abs(ks[i][0] - t))
                        if abs(ks[best][0] - t) > 0.35:
                            continue
                        kt, kp, kx, ke = ks[best]
                        ks[best] = (kt, kp, kx + sgn * push, ke)
            # and the enemies must not stack into one silhouette either
            for i, f1 in enumerate(foes):
                for f2 in foes[i + 1:]:
                    if lie(f1, t) or lie(f2, t):
                        continue
                    d = abs(f2.skel(t).head[0] - f1.skel(t).head[0])
                    if d < 132.0:
                        push = (132.0 - d) * 0.2
                        for tr, sgn in ((f1, -1.0), (f2, 1.0)):
                            ks = tr.keys
                            best = min(range(len(ks)), key=lambda i: abs(ks[i][0] - t))
                            if abs(ks[best][0] - t) > 0.35:
                                continue
                            kt, kp, kx, ke = ks[best]
                            ks[best] = (kt, kp, kx + sgn * push, ke)
            t += 0.1

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

    cuts = (
        (16.90, 0.46, "teal", "hit", "face"),    # the wide cut through two men
        (23.30, 0.52, "blue", "ko", "face"),     # the last one
    )

    named = {tr.name: tr for tr in tracks}
    return {"set": set_name, "tracks": tracks, "hero": hero, **named, "impacts": impacts, "dust": dusts,
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
    dict(t0=6.90, t1=8.10, anchor="down", zoom=1.34, follow=1.0, dof=0.16,
         style="cut", ground=0.75),
    dict(t0=8.10, t1=9.60, anchor="action", zoom=1.00, z1=1.06, follow=0.8,
         dof=0.05, style="cut", ground=0.80),
    dict(t0=9.60, t1=11.40, anchor="down", zoom=1.30, follow=1.0, dof=0.18,
         style="whip", ground=0.74),
    dict(t0=11.40, t1=14.20, anchor="action", zoom=1.04, z1=1.12, follow=1.0,
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
    dict(t0=24.40, t1=25.90, anchor="down", zoom=1.40, follow=1.0, dof=0.20,
         style="cut", ground=0.74),
    # the winner shot sits low: the K.O. card needs the air above his head
    dict(t0=25.90, t1=30.20, anchor="winner", zoom=1.12, z1=1.00, follow=0.5,
         dof=0.14, style="whip", ground=0.87),
)
