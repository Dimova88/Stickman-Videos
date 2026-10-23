"""The fight, authored as motion channels rather than as poses.

Read the table at the bottom for the beat sheet. Two rules govern the numbers:

* **Distance is earned.** Every strike starts with a step that closes the gap and
  a root that keeps travelling *through* the punch, then settles back. Fighters
  that stay at one distance have to teleport their arms.
* **The defender moves first.** A punch is authored as a target on the defender's
  head *at the contact frame*, resolved after both fighters' bodies are keyed, so
  the fist goes where the head actually is.

Feet are simulated (``motion.Feet``): planted until the body drifts too far, then
one foot swings across, so steps appear by themselves when someone advances,
retreats, or gets pushed.
"""
from __future__ import annotations

import math

from .core import clamp
from .motion import HIP, Performer, Scalar

GROUND = 432.0
FPS = 24
DURATION = 30.0
RED = (186, 54, 50)
BLUE = (38, 84, 148)

# hand targets are (forward, up) in the fighter's own facing space, measured from
# the shoulder; the arm can reach 101 units, so anything past ~95 is a full commit
# A boxer's guard: lead hand out in front of the face, rear hand at the chin.
# Hands sit 45-60 units from the shoulder so the arms fold like arms, not springs.
GUARD = dict(ha=(52, -22), hb=(30, 12))
GUARD_HIGH = dict(ha=(56, -32), hb=(32, 4))
GUARD_TIGHT = dict(ha=(42, -12), hb=(26, 16))
RELAXED = dict(ha=(34, 4), hb=(16, 20))


def build() -> dict:
    a = Performer(372.0, GROUND, facing=1)
    b = Performer(596.0, GROUND, facing=-1)

    events: list[dict] = []

    def spark(t, size=1.0, kind="spark"):
        events.append({"t": t, "kind": kind, "size": size})

    def whoosh(t, dur=0.16, size=1.0, direction=1, y=-10):
        events.append({"t": t, "kind": "whoosh", "dur": dur, "size": size,
                       "dir": direction, "y": y})

    def dust(t, size=1.0):
        events.append({"t": t, "kind": "dust", "size": size})

    def shake(t, amp=1.0, dur=0.25, kick=0.0):
        events.append({"t": t, "kind": "shake", "amp": amp, "dur": dur, "kick": kick})

    def flash(t, size=1.0):
        events.append({"t": t, "kind": "flash", "size": size})

    # strikes are recorded now and aimed at the defender's head afterwards
    aims: list[dict] = []

    def strike(t, att: Performer, dfd: Performer, *, hand="b", size=0.8, off=(0, 0),
               ease="snap", recover=0.20, guard=None):
        """Throw a hand at the defender's head at time ``t`` and snap it back."""
        aims.append(dict(t=t, att=att, dfd=dfd, hand=hand, off=off, ease=ease,
                         recover=recover, guard=guard))
        return t

    # ================================================================ opening
    # both breathe and shift weight; the camera pushes in
    a.key_pose(0.0, root=372, lean=-0.05, crouch=3, **GUARD)
    b.key_pose(0.0, root=596, lean=-0.05, crouch=3, **GUARD)
    a.key_pose(1.1, lean=-0.02, crouch=2, **GUARD_HIGH)
    b.key_pose(1.3, lean=-0.02, crouch=2, **GUARD_HIGH)
    a.key_pose(2.1, root=384, lean=-0.06, crouch=4, **GUARD)
    b.key_pose(2.1, root=588, crouch=2, **GUARD)

    # ================================================================ jab (parried)
    a.key_pose(2.55, root=414, lean=-0.02, crouch=5, ha=(10, -10), hb=(6, 6), ease="out")
    b.key_pose(2.55, root=586, **GUARD_HIGH)
    whoosh(2.72, direction=1)
    strike(2.86, a, b, hand="a", size=0.5, off=(6, -6))
    b.key_pose(2.86, lean=-0.10, crouch=4, **GUARD_HIGH, ease="snap")
    spark(2.86, 0.5)
    a.key_pose(3.06, root=418, lean=0.02, crouch=4, **GUARD)
    b.key_pose(3.10, root=590, **GUARD_HIGH)

    # ================================================================ cross (slipped)
    a.key_pose(3.55, root=440, lean=-0.10, crouch=6, ha=(6, -4), hb=(14, 4), ease="out")
    whoosh(3.72, direction=1)
    strike(3.86, a, b, hand="b", size=0.45, off=(0, -2))
    b.key_pose(3.80, root=602, lean=-0.26, crouch=3, ha=(18, -16), hb=(4, 2), ease="snap")
    b.key_pose(4.20, root=598, lean=-0.10, crouch=4, **GUARD)
    a.key_pose(4.30, root=428, lean=0.04, crouch=3, **GUARD)

    # ================================================================ B body kick
    b.key_pose(4.75, root=570, lean=-0.22, crouch=1, ha=(4, -4), hb=(-16, 10), ease="out")
    whoosh(4.95, direction=-1, dur=0.2, y=26)
    b.feet.kick(4.95, 5.42, 0, (a.head_at(5.16)[0] - 30, GROUND - 74.0), arc=18)
    a.key_pose(5.02, root=436, lean=0.16, crouch=8, ha=(20, 2), hb=(6, 16), ease="snap")
    spark(5.16, 0.85)
    shake(5.16, 0.8, 0.24, kick=0.03)
    b.key_pose(5.42, root=576, lean=-0.06, crouch=3, **GUARD)
    a.key_pose(5.55, root=430, lean=0.04, crouch=4, **GUARD)

    # ================================================================ two jabs, both read
    a.key_pose(5.95, root=452, lean=-0.04, crouch=4, **GUARD)
    b.key_pose(5.95, root=582, **GUARD_HIGH)
    whoosh(6.06, direction=1)
    strike(6.18, a, b, hand="a", size=0.35, off=(4, -6))
    b.key_pose(6.18, lean=-0.08, **GUARD_HIGH, ease="snap")
    spark(6.18, 0.35)
    a.key_pose(6.34, root=456, **GUARD)
    whoosh(6.46, direction=1)
    strike(6.58, a, b, hand="b", size=0.45, off=(2, -4))
    b.key_pose(6.58, lean=-0.12, **GUARD_TIGHT, ease="snap")
    spark(6.58, 0.45)
    a.key_pose(6.78, root=450, **GUARD)
    b.key_pose(6.86, root=578, **GUARD)

    # ================================================================ B steps in, hook + duck
    b.key_pose(7.30, root=556, lean=0.06, crouch=4, ha=(24, -2), hb=(12, 8), ease="out")
    whoosh(7.46, direction=-1)
    strike(7.58, b, a, hand="b", size=0.5, off=(0, -6))
    a.key_pose(7.56, root=444, crouch=15, lean=0.26, ha=(16, 6), hb=(4, 16), ease="snap")
    spark(7.58, 0.4)
    b.key_pose(7.84, root=552, lean=0.10, crouch=4, **GUARD_HIGH)
    a.key_pose(7.96, root=446, crouch=3, lean=-0.04, **GUARD)

    # ================================================================ A uppercut lands
    a.key_pose(8.22, root=470, lean=0.10, crouch=8, ha=(10, 14), hb=(6, 12), ease="out")
    whoosh(8.34, direction=1)
    strike(8.46, a, b, hand="b", size=1.0, off=(-2, 10), guard=None)
    b.key_pose(8.50, root=566, lean=-0.30, crouch=1, ha=(10, -18), hb=(-6, -6), ease="snap")
    spark(8.46, 1.0)
    shake(8.46, 1.2, 0.3, kick=0.05)
    a.key_pose(8.74, root=478, lean=-0.06, crouch=4, **GUARD)
    b.key_pose(8.95, root=570, lean=-0.10, crouch=4, **GUARD_HIGH)

    # ================================================================ clinch, shove
    a.key_pose(9.40, root=494, lean=0.08, crouch=5, ha=(34, -6), hb=(26, 4), ease="out")
    b.key_pose(9.40, root=546, lean=0.10, crouch=5, ha=(34, -6), hb=(26, 4), ease="out")
    a.key_pose(9.95, root=500, lean=0.14, crouch=7, ha=(38, -2), hb=(30, 8))
    b.key_pose(9.95, root=542, lean=0.14, crouch=7, ha=(38, -2), hb=(30, 8))
    a.key_pose(10.45, root=478, lean=-0.14, crouch=2, ha=(20, -12), hb=(10, 0), ease="out")
    b.key_pose(10.45, root=560, lean=-0.14, crouch=2, ha=(20, -12), hb=(10, 0), ease="out")
    f = 10.42
    events.append({"t": f, "kind": "spark", "size": 0.3})
    shake(10.42, 0.4, 0.28)
    a.key_pose(11.0, root=470, lean=-0.04, crouch=3, **GUARD)
    b.key_pose(11.0, root=566, lean=-0.04, crouch=3, **GUARD)

    # ================================================================ knee, backfist
    a.key_pose(11.45, root=488, lean=0.16, crouch=1, ha=(24, 4), hb=(16, 10), ease="out")
    b.key_pose(11.45, root=548, lean=-0.10, crouch=5, **GUARD_TIGHT)
    a.feet.kick(11.55, 11.95, 1, (b.head_at(11.7)[0] - 52, GROUND - 62.0), arc=14)
    whoosh(11.6, direction=1, dur=0.14, y=30)
    spark(11.74, 0.75)
    shake(11.74, 0.7, 0.2, kick=0.03)
    b.key_pose(11.74, crouch=9, lean=0.24, ease="snap")
    a.key_pose(12.0, root=492, lean=0.02, crouch=4, **GUARD)
    b.key_pose(12.05, root=552, lean=-0.02, crouch=5, **GUARD_HIGH)

    # spin-ish backfist: the hand starts behind the head, then whips across
    a.key_pose(12.35, root=496, lean=-0.16, crouch=5, ha=(-6, -18), hb=(20, -10), ease="out")
    whoosh(12.5, direction=1, dur=0.14)
    strike(12.62, a, b, hand="b", size=1.0, off=(0, -4))
    b.key_pose(12.62, root=560, lean=-0.22, crouch=4, ha=(16, -14), hb=(4, 0), ease="snap")
    spark(12.62, 1.0)
    shake(12.62, 1.1, 0.3, kick=0.05)
    a.key_pose(12.92, root=486, lean=-0.02, crouch=4, **GUARD)
    b.key_pose(13.1, root=566, lean=-0.06, crouch=4, **GUARD_HIGH)

    # ================================================================ sweep, jumped
    b.key_pose(13.45, root=556, lean=0.18, crouch=8, ha=(10, 2), hb=(0, 12), ease="out")
    whoosh(13.6, direction=-1, dur=0.2, y=44)
    b.feet.kick(13.62, 14.05, 0, (a.root.at(13.8) + 24, GROUND - 46.0), arc=10)
    a.feet.jump(13.66, 14.12, 26.0)
    a.key_pose(13.66, root=482, lean=-0.10, crouch=-8, ha=(14, -10), hb=(2, 2), ease="snap")
    a.key_pose(13.95, root=486, lean=-0.04, crouch=-4, ha=(16, -6), hb=(4, 4))
    dust(14.12, 0.6)
    a.key_pose(14.16, root=488, lean=0.10, crouch=12, ha=(18, 4), hb=(6, 14), ease="snap")
    b.key_pose(14.1, root=558, lean=-0.04, crouch=4, **GUARD)
    a.key_pose(14.5, root=492, lean=-0.02, crouch=4, **GUARD)

    # ================================================================ B head kick, A counter
    b.key_pose(14.85, root=550, lean=-0.16, crouch=2, ha=(6, -8), hb=(-14, 12), ease="out")
    whoosh(14.98, direction=-1, dur=0.2, y=-40)
    b.feet.kick(15.0, 15.4, 0, (a.head_at(15.2)[0] - 56, GROUND - 116.0), arc=26)
    a.key_pose(15.05, root=474, lean=-0.30, crouch=3, ha=(18, -18), hb=(6, -4), ease="snap")
    b.key_pose(15.4, root=548, lean=-0.06, crouch=4, **GUARD)
    # counter straight while B is still on one leg
    a.key_pose(15.62, root=506, lean=0.14, crouch=5, ha=(10, -6), hb=(16, 2), ease="out")
    whoosh(15.7, direction=1)
    strike(15.82, a, b, hand="b", size=1.1, off=(0, -6))
    b.key_pose(15.82, root=562, lean=-0.34, crouch=2, ha=(12, -16), hb=(-4, -4), ease="snap")
    spark(15.82, 1.1)
    shake(15.82, 1.3, 0.32, kick=0.06)
    a.key_pose(16.1, root=500, lean=-0.02, crouch=4, **GUARD)
    b.key_pose(16.35, root=572, lean=-0.08, crouch=4, **GUARD_HIGH)

    # ================================================================ circling
    a.key_pose(17.0, root=488, lean=-0.04, crouch=4, **GUARD)
    b.key_pose(17.0, root=576, lean=-0.04, crouch=4, **GUARD)
    a.key_pose(18.0, root=496, lean=-0.02, crouch=3, **GUARD_HIGH)
    b.key_pose(18.0, root=570, lean=-0.02, crouch=3, **GUARD_HIGH)

    # ================================================================ exchange
    b.key_pose(18.4, root=560, lean=0.06, ha=(18, -2), hb=(12, 8), ease="out")
    whoosh(18.5, direction=-1)
    strike(18.62, b, a, hand="b", size=0.5, off=(0, -6))
    a.key_pose(18.6, root=486, lean=-0.12, crouch=5, **GUARD_HIGH, ease="snap")
    spark(18.62, 0.5)
    b.key_pose(18.86, root=562, **GUARD)
    a.key_pose(19.06, root=512, lean=0.12, crouch=5, ha=(8, -4), hb=(16, 2), ease="out")
    whoosh(19.16, direction=1)
    strike(19.28, a, b, hand="b", size=0.6, off=(0, -4))
    b.key_pose(19.26, root=574, lean=-0.20, crouch=3, **GUARD_HIGH, ease="snap")
    spark(19.28, 0.6)
    a.key_pose(19.55, root=506, **GUARD)
    b.key_pose(19.6, root=576, **GUARD)

    # ================================================================ quick 1-2
    a.key_pose(20.15, root=524, lean=0.02, crouch=4, **GUARD)
    b.key_pose(20.15, root=566, **GUARD_HIGH)
    whoosh(20.24, direction=1)
    strike(20.34, a, b, hand="a", size=0.4, off=(4, -6))
    b.key_pose(20.34, lean=-0.08, **GUARD_HIGH, ease="snap")
    spark(20.34, 0.4)
    a.key_pose(20.52, root=526, **GUARD)
    whoosh(20.6, direction=1)
    strike(20.72, a, b, hand="b", size=0.55, off=(2, -2))
    b.key_pose(20.72, lean=-0.14, **GUARD_TIGHT, ease="snap")
    spark(20.72, 0.55)
    a.key_pose(20.95, root=516, **GUARD)

    # ================================================================ reload
    a.key_pose(21.6, root=506, lean=-0.06, crouch=4, **GUARD)
    b.key_pose(21.6, root=574, lean=-0.06, crouch=4, **GUARD)
    a.key_pose(22.4, root=500, lean=-0.10, crouch=6, ha=(10, -14), hb=(2, -2))
    b.key_pose(22.4, root=578, lean=-0.10, crouch=6, ha=(10, -14), hb=(2, -2))
    a.key_pose(23.05, root=512, lean=0.06, crouch=3, **GUARD)
    b.key_pose(23.05, root=566, lean=0.06, crouch=3, **GUARD)

    # ================================================================ clash
    a.key_pose(23.5, root=534, lean=0.16, crouch=4, ha=(12, -6), hb=(14, 0), ease="out")
    b.key_pose(23.5, root=548, lean=0.16, crouch=4, ha=(12, -6), hb=(14, 0), ease="out")
    whoosh(23.62, direction=1)
    whoosh(23.64, direction=-1)
    strike(23.76, a, b, hand="a", size=1.5, off=(-2, -24))
    strike(23.82, b, a, hand="b", size=1.5, off=(2, 4))
    spark(23.78, 1.0)
    flash(23.78, 0.6)
    shake(23.78, 2.0, 0.42, kick=0.07)
    a.key_pose(24.12, root=492, lean=-0.24, crouch=3, ha=(14, -14), hb=(2, -2), ease="snap")
    b.key_pose(24.12, root=590, lean=-0.24, crouch=3, ha=(14, -14), hb=(2, -2), ease="snap")
    a.key_pose(24.7, root=498, lean=-0.04, crouch=4, **GUARD)
    b.key_pose(24.7, root=584, lean=-0.04, crouch=4, **GUARD)

    # ================================================================ final exchange
    a.key_pose(25.5, root=508, lean=-0.02, crouch=4, **GUARD)
    b.key_pose(25.5, root=576, lean=-0.02, crouch=4, **GUARD)
    a.key_pose(26.1, root=524, lean=0.10, crouch=3, ha=(14, -8), hb=(12, 0), ease="out")
    b.key_pose(26.1, root=562, lean=0.10, crouch=3, ha=(14, -8), hb=(12, 0), ease="out")
    a.key_pose(26.9, root=536, lean=0.14, crouch=4, ha=(10, -4), hb=(16, 4), ease="out")
    b.key_pose(26.9, root=552, lean=0.14, crouch=4, ha=(10, -4), hb=(16, 4), ease="out")
    whoosh(27.0, direction=1)
    whoosh(27.02, direction=-1)
    strike(27.14, a, b, hand="a", size=1.6, off=(-2, -22))
    strike(27.20, b, a, hand="b", size=1.6, off=(2, 6))
    spark(27.16, 1.1)
    flash(27.16, 0.7)
    shake(27.16, 2.3, 0.45, kick=0.08)
    a.key_pose(27.55, root=504, lean=-0.20, crouch=4, ha=(10, -12), hb=(0, 0), ease="snap")
    b.key_pose(27.55, root=584, lean=-0.20, crouch=4, ha=(10, -12), hb=(0, 0), ease="snap")

    # last beat: both drop into a low guard, breathing, and the film fades
    a.key_pose(28.4, root=500, lean=0.04, crouch=8, ha=(22, 0), hb=(10, 10))
    b.key_pose(28.4, root=582, lean=0.04, crouch=8, ha=(22, 0), hb=(10, 10))
    a.key_pose(29.4, root=498, lean=0.02, crouch=6, ha=(20, 2), hb=(8, 12))
    b.key_pose(29.4, root=580, lean=0.02, crouch=6, ha=(20, 2), hb=(8, 12))

    # ================================================================ resolve aims
    for s in aims:
        att, dfd = s["att"], s["dfd"]
        hx, hy = dfd.head_at(s["t"])
        sx, sy = att.shoulder_at(s["t"])
        off = s["off"]
        dx = (hx + off[0] - sx) * att.facing
        dy = (hy + off[1] - sy)
        # the arm cannot reach past ~99; clamp and let the body keep the rest
        r = math.hypot(dx, dy)
        if r > 99.0:
            dx *= 99.0 / r
            dy *= 99.0 / r
        trk = att.hand_a if s["hand"] == "a" else att.hand_b
        trk.key(s["t"], (dx, dy), s["ease"])
        # snap back to whatever guard the author asked for (or the default)
        back = s["guard"] or (GUARD["ha"] if s["hand"] == "a" else GUARD["hb"])
        trk.key(s["t"] + s["recover"], back, "out")

    # ================================================================ keep the distance
    # Two figures with 100-unit arms need ~150 units between their heads or the
    # bodies interpenetrate. The author works in beats, not in numbers, so the
    # pair is separated afterwards: the midpoint of every authored approach is
    # kept and the gap is opened to the minimum — baked at 1/20 s so the spline
    # cannot dip back through it between keys.
    MIN_GAP = 150.0
    ts = [i / 20.0 for i in range(int(DURATION * 20) + 1)]
    xs = [(a.root.at(t), b.root.at(t)) for t in ts]
    for _ in range(3):
        for i, t in enumerate(ts):
            xa, xb = xs[i]
            # heads, not roots: a lean moves the head 30 units
            ha = a.head_at(t, xa)
            hb = b.head_at(t, xb)
            if hb[0] - ha[0] < MIN_GAP:
                push = (MIN_GAP - (hb[0] - ha[0])) * 0.5
                xs[i] = (xa - push, xb + push)
    a.root = Scalar(xs[0][0])
    b.root = Scalar(xs[0][1])
    for t, (xa, xb) in zip(ts, xs):
        a.root.key(t, xa, "smooth")
        b.root.key(t, xb, "smooth")

    # ================================================================ simulate feet
    a.feet.simulate(a.root.at, 372.0, DURATION)
    b.feet.simulate(b.root.at, 596.0, DURATION)

    # place the effect positions from the resolved bodies
    for e in events:
        t = e["t"]
        pa, pb = a.pose_at(t), b.pose_at(t)
        from .core import solve
        sa, sb = solve(pa), solve(pb)
        if e["kind"] in ("spark", "flash"):
            cands = [((sa.pts[i][0] - sb.head[0]) ** 2 + (sa.pts[i][1] - sb.head[1]) ** 2,
                      sa.pts[i], sb.head) for i in (4, 6, 8, 10)]
            cands += [((sb.pts[i][0] - sa.head[0]) ** 2 + (sb.pts[i][1] - sa.head[1]) ** 2,
                       sb.pts[i], sa.head) for i in (4, 6, 8, 10)]
            _d, fist, head = min(cands, key=lambda c: c[0])
            k = 0.8
            e["x"] = fist[0] + (head[0] - fist[0]) * k
            e["y"] = fist[1] + (head[1] - fist[1]) * k
        elif e["kind"] == "whoosh":
            e["x"] = (sa.head[0] + sb.head[0]) * 0.5 + e.get("dir", 1) * 14
            e.setdefault("y", -10)
            e["y"] = 300 + e["y"]
        elif e["kind"] == "dust":
            e["x"] = (a.head_at(t)[0] + b.head_at(t)[0]) * 0.5
            e["y"] = GROUND

    camera = [
        # t,    cx,  cy, zoom
        (0.0, 484, 286, 1.06),
        (4.5, 500, 284, 1.18),
        (8.0, 505, 286, 1.10),
        (11.5, 512, 284, 1.22),
        (14.0, 500, 280, 1.16),
        (17.5, 494, 288, 1.08),
        (20.5, 505, 284, 1.16),
        (23.8, 512, 282, 1.24),
        (26.0, 520, 284, 1.14),
        (27.2, 522, 282, 1.28),
        (30.0, 518, 286, 1.06),
    ]
    return {"a": a, "b": b, "events": events, "camera": camera}
