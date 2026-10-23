"""The fight: 30 seconds, two Pivot figures, one continuous choreography.

Everything is authored in the app's 960x540 design space with the floor at
y = 432. A pose is described by where the hands and feet are, not by joint
angles — that is the only way a fight reads as contact rather than as flailing.

Style rules kept throughout:

* every strike has a wind-up, a 2–3 frame travel and a 4–6 frame recovery;
* the guard never opens between beats — the free hand stays near the head;
* feet stay planted while punching, and step *with* the punch;
* each hit is a single readable silhouette at the moment of contact.
"""
from __future__ import annotations

import math

from .core import Pose, Track, pose_from_targets, clamp, solve

GROUND = 432.0
HIP = 129.0  # leg length: hip to sole
FPS = 24
DURATION = 30.0

RED = (186, 54, 50)
BLUE = (38, 84, 148)


def hip_y(ground=GROUND, crouch: float = 0.0) -> float:
    return ground - HIP + crouch


def P(x: float, *, ground: float = GROUND, facing: int = 1, crouch: float = 0.0,
      lean: float = 0.0, scale: float = 1.0, head_turn: float = 0.0,
      ha=(30, -52), hb=(10, -44), fa=(26, 0), fb=(-28, 0),
      elbow_a=1.0, elbow_b=-1.0, knee_a=1.0, knee_b=1.0, torso_off: float = 0.0) -> Pose:
    """A pose described in *facing space*: dx forward is positive, y from the hip."""
    y = hip_y(ground, crouch)
    torso = -math.pi / 2 + lean + torso_off

    def w(dx, dy):
        return (x + facing * dx, y + dy)

    foot_a = w(fa[0], fa[1] + HIP - crouch)
    foot_b = w(fb[0], fb[1] + HIP - crouch)
    return pose_from_targets(x, y, facing=facing, scale=scale, torso=torso, head_turn=head_turn,
                             hand_a=w(*ha), hand_b=w(*hb), foot_a=foot_a, foot_b=foot_b,
                             elbow_a=elbow_a, elbow_b=elbow_b, knee_a=knee_a, knee_b=knee_b)


# ---------------------------------------------------------------- pose library
def _pose(x, ground, facing, base, kw):
    d = dict(base)
    d.update(kw)
    return P(x, ground=ground, facing=facing, **d)


def guard(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=6.0, lean=-0.05, ha=(46, -64), hb=(22, -50), fa=(36, 0), fb=(-34, 0),
                      elbow_a=1.0, elbow_b=-1.0, head_turn=-0.05 * facing), kw)


def idle(x, facing=1, bob=0.0, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=bob * 3.0, lean=-0.02, ha=(34, -58), hb=(10, -46),
                      fa=(32, 0), fb=(-32, 0)), kw)


def jab_out(x, facing=1, reach=118, ground=GROUND, **kw):
    """Front hand thrown straight, rear hand stays home."""
    return _pose(x, ground, facing,
                 dict(lean=0.10, ha=(reach, -72), hb=(20, -52), fa=(40, 0), fb=(-24, 0),
                      elbow_a=1.0), kw)


def cross_out(x, facing=1, reach=126, ground=GROUND, **kw):
    """Rear hand thrown straight through the target."""
    return _pose(x, ground, facing,
                 dict(lean=0.16, ha=(22, -56), hb=(reach - 4, -78), fa=(44, 0), fb=(-18, 0),
                      elbow_b=-1.0), kw)


def hook_out(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(lean=0.12, crouch=8, ha=(56, -88), hb=(48, -94), fa=(40, 0),
                      fb=(-24, 0), elbow_b=-1.0), kw)


def uppercut_out(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(lean=-0.18, crouch=-6, ha=(62, -102), hb=(24, -54), fa=(32, 0),
                      fb=(-26, 0)), kw)


def block_high(x, facing=1, ground=GROUND, **kw):
    """Forearm up in front of the face, elbow tight."""
    return _pose(x, ground, facing,
                 dict(crouch=4, lean=-0.10, ha=(52, -96), hb=(20, -62), fa=(30, 0),
                      fb=(-32, 0), elbow_a=-1.0), kw)


def block_mid(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=5, lean=-0.04, ha=(54, -78), hb=(18, -60), fa=(30, 0),
                      fb=(-32, 0), elbow_a=-1.0), kw)


def block_low(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=12, lean=0.02, ha=(50, -50), hb=(16, -44), fa=(32, 0),
                      fb=(-34, 0), elbow_a=-1.0), kw)


def duck(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=40, lean=0.26, ha=(40, -46), hb=(14, -40), fa=(38, 0),
                      fb=(-26, 0)), kw)


def lean_back(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=10, lean=-0.34, ha=(26, -64), hb=(4, -52), fa=(6, 0),
                      fb=(-46, 0)), kw)


def kick_low(x, facing=1, ground=GROUND, **kw):
    """Rear-leg low kick: the shin goes out at knee height."""
    return _pose(x, ground, facing,
                 dict(crouch=6, lean=-0.22, ha=(18, -72), hb=(-4, -60), fa=(22, 0),
                      fb=(98, -18), knee_b=1.0), kw)


def kick_mid(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=2, lean=-0.30, ha=(10, -78), hb=(-10, -66), fa=(20, 0),
                      fb=(122, -52), knee_b=1.0), kw)


def kick_high(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=-2, lean=-0.40, ha=(0, -82), hb=(-18, -70), fa=(16, 0),
                      fb=(112, -104), knee_b=1.0), kw)


def knee_strike(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=-10, lean=0.04, ha=(44, -88), hb=(24, -84), fa=(6, 0),
                      fb=(44, -64), knee_b=1.0), kw)


def jump_up(x, facing=1, ground=GROUND, height=0.0, **kw):
    """Airborne: both feet tucked under the body."""
    return _pose(x, ground, facing,
                 dict(crouch=height, ha=(38, -74), hb=(14, -62), fa=(34, -34), fb=(-20, -46)), kw)


def air_kick(x, facing=1, ground=GROUND, height=0.0, reach=110.0, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=height, lean=-0.24, ha=(20, -78), hb=(-2, -68), fa=(18, -60),
                      fb=(reach, -70), knee_b=1.0), kw)


def hit_head(x, facing=1, ground=GROUND, **kw):
    """Struck: head and torso snap away from the blow."""
    return _pose(x, ground, facing,
                 dict(crouch=8, lean=-0.42, ha=(-6, -76), hb=(-24, -64), fa=(-6, 0),
                      fb=(-44, 0)), kw)


def hit_body(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=18, lean=0.34, ha=(24, -54), hb=(2, -46), fa=(16, 0),
                      fb=(-40, 0)), kw)


def clinch(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=6, lean=0.16, ha=(58, -84), hb=(46, -74), fa=(34, 0),
                      fb=(-30, 0), elbow_b=-1.0), kw)


def shove(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(lean=0.26, crouch=0, ha=(72, -80), hb=(60, -70), fa=(44, 0),
                      fb=(-24, 0)), kw)


def landing(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=26, lean=0.10, ha=(40, -54), hb=(16, -46), fa=(38, 0),
                      fb=(-34, 0)), kw)


def spin_back(x, facing=1, ground=GROUND, **kw):
    return _pose(x, ground, facing,
                 dict(crouch=4, lean=0.0, ha=(-34, -84), hb=(-52, -66), fa=(22, 0),
                      fb=(-30, 0)), kw)


# ------------------------------------------------------------------ the fight
def build() -> dict:
    """Return the scene: two tracks, the camera, and the effect events."""
    a = Track(guard(352, facing=1))
    b = Track(guard(612, facing=-1))

    # Everything is authored at "contact range"; SPREAD opens the distance so
    # two figures with 100-unit arms still read as two figures, not one blob.
    SPREAD = 1.45

    def spread(pose):
        return pose.copy(x=480.0 + (pose.x - 480.0) * SPREAD)

    def A(t, pose, ease="smooth"):
        a.key(t, spread(pose), ease)

    def B(t, pose, ease="smooth"):
        b.key(t, spread(pose), ease)

    events = []

    def hit(t, x, y, size=1.0, kind="spark"):
        events.append({"t": t, "kind": kind, "x": x, "y": y, "size": size})

    def whoosh(t, x, y, dur=0.18, size=1.0, direction=1):
        events.append({"t": t, "kind": "whoosh", "x": x, "y": y, "size": size,
                       "dir": direction, "dur": dur})

    def dust(t, x, y, size=1.0):
        events.append({"t": t, "kind": "dust", "x": x, "y": y, "size": size})

    def shake(t, amp=1.0, dur=0.25, kick=0.0):
        events.append({"t": t, "kind": "shake", "amp": amp, "dur": dur, "kick": kick})

    # ---- 0: stand-off ---------------------------------------------------
    A(0.0, idle(356, 1), "smooth")
    B(0.0, idle(604, -1), "smooth")
    for i in range(1, 5):
        t = i * 0.55
        A(t, idle(356 + 2 * (-1) ** i, 1, bob=0.4 if i % 2 else -0.2), "smooth")
        B(t, idle(604 + 2 * (1) ** i, -1, bob=-0.2 if i % 2 else 0.4), "smooth")
    A(2.2, guard(366, 1))
    B(2.2, guard(592, -1))

    # ---- 1: A steps in with a jab, B parries ---------------------------
    A(2.75, guard(424, 1, crouch=4))          # step in
    B(2.75, guard(588, -1))
    whoosh(2.9, 430, 330, size=0.8, direction=1)
    A(3.05, jab_out(436, 1, reach=112), "snap")
    B(3.05, block_high(586, -1), "snap")
    hit(3.05, 520, 322, 0.55)
    A(3.35, guard(428, 1), "smooth")
    B(3.35, guard(586, -1))

    # ---- 2: cross, B slips and counters --------------------------------
    A(3.95, cross_out(486, 1, reach=128), "snap")
    whoosh(3.85, 440, 320, size=0.9, direction=1)
    B(4.05, lean_back(592, -1), "snap")
    B(4.35, hit_head(600, -1), "smooth")      # grazing, head turns
    hit(4.12, 540, 318, 0.5)
    shake(4.12, 0.5, 0.18)
    A(4.6, guard(446, 1))

    # ---- 3: B counter body kick, A blocks with the shin ----------------
    B(5.0, kick_mid(586, -1), "snap")
    whoosh(4.95, 520, 350, size=1.1, direction=-1)
    A(5.05, block_low(452, 1, crouch=10), "snap")
    hit(5.05, 486, 356, 0.8)
    shake(5.05, 0.8, 0.22, kick=0.03)
    A(5.5, guard(450, 1))
    B(5.6, guard(592, -1))

    # ---- 4: two quick jabs, both parried ------------------------------
    A(6.15, jab_out(456, 1, reach=104), "snap")
    B(6.15, block_mid(584, -1), "snap")
    hit(6.15, 512, 336, 0.4)
    A(6.45, guard(456, 1))
    A(6.85, cross_out(464, 1, reach=110), "snap")
    B(6.9, block_high(578, -1), "snap")
    hit(6.9, 510, 326, 0.5)
    A(7.25, guard(458, 1))
    B(7.3, guard(578, -1))

    # ---- 5: B leaps in with an overhead, A ducks ----------------------
    B(7.8, guard(572, -1, crouch=16))
    B(8.15, jump_up(556, -1, ground=GROUND, height=-46))
    B(8.45, air_kick(524, -1, height=-40, reach=-104), "snap")
    whoosh(8.35, 520, 300, size=1.2, direction=-1)
    A(8.5, duck(470, 1), "snap")
    B(8.8, landing(500, -1))
    dust(8.8, 500, GROUND, 1.0)
    shake(8.8, 0.9, 0.25)
    A(9.0, guard(462, 1))
    B(9.15, guard(516, -1))

    # ---- 6: clinch -----------------------------------------------------
    A(9.7, clinch(445, 1))
    B(9.7, clinch(522, -1))
    A(10.4, clinch(448, 1, crouch=10))
    B(10.4, clinch(520, -1, crouch=10))
    A(11.0, shove(452, 1))
    B(11.0, shove(510, -1))
    shake(10.9, 0.5, 0.3)
    A(11.6, guard(452, 1))
    B(11.7, guard(534, -1))

    # ---- 7: A knees, then spins a backfist into B's guard --------------
    A(12.2, knee_strike(452, 1), "snap")
    B(12.25, block_low(530, -1, crouch=12), "snap")
    hit(12.2, 500, 352, 0.7)
    shake(12.2, 0.7, 0.2)
    A(12.6, guard(466, 1))
    A(13.0, spin_back(474, 1), "smooth")
    whoosh(13.05, 500, 316, size=0.9, direction=1)
    A(13.4, hook_out(462, 1), "snap")
    B(13.45, block_high(556, -1), "snap")
    hit(13.40, 516, 328, 1.0)
    shake(13.45, 1.2, 0.3, kick=0.06)
    A(13.9, guard(470, 1))
    B(14.0, guard(552, -1))

    # ---- 8: B sweeps low, A jumps it ----------------------------------
    B(14.5, kick_low(536, -1), "snap")
    whoosh(14.45, 500, 392, size=1.0, direction=-1)
    A(14.55, jump_up(478, 1, ground=GROUND, height=-40), "snap")
    A(14.9, jump_up(470, 1, ground=GROUND, height=-56))
    A(15.25, jump_up(462, 1, ground=GROUND, height=-44))
    A(15.6, landing(452, 1), "snap")
    dust(15.6, 452, GROUND, 0.8)
    B(15.0, guard(540, -1))

    # ---- 9: B catches A's kick and shoves -----------------------------
    A(16.1, kick_mid(470, 1), "snap")
    B(16.15, block_mid(520, -1, crouch=6), "snap")
    hit(16.1, 500, 340, 0.8)
    shake(16.1, 0.8, 0.22)
    A(16.6, clinch(446, 1))
    B(16.65, clinch(524, -1))
    B(17.1, shove(536, -1), "snap")
    A(17.15, lean_back(432, 1), "snap")
    whoosh(17.05, 490, 320, size=1.1, direction=1)
    A(17.7, guard(418, 1))
    B(17.8, guard(520, -1))

    # ---- 10: reset, circling ------------------------------------------
    A(18.6, guard(404, 1, crouch=4))
    B(18.6, guard(534, -1, crouch=4))
    A(19.4, guard(398, 1))
    B(19.4, guard(540, -1))

    # ---- 11: final exchange, three clashes ----------------------------
    A(20.1, jab_out(424, 1, reach=112), "snap")
    B(20.1, block_high(516, -1), "snap")
    hit(20.1, 478, 322, 0.7)
    shake(20.1, 0.6, 0.2)
    A(20.5, guard(436, 1))
    B(20.5, guard(504, -1))
    B(21.0, kick_mid(510, -1), "snap")
    whoosh(20.95, 470, 340, size=1.0, direction=-1)
    A(21.05, block_low(452, 1), "snap")
    hit(21.05, 486, 344, 0.8)
    shake(21.05, 0.8, 0.22)
    A(21.5, guard(450, 1))
    B(21.55, guard(524, -1))
    A(22.05, hook_out(456, 1), "snap")
    B(22.08, block_high(548, -1), "snap")
    hit(22.05, 492, 322, 1.0)
    shake(22.05, 1.1, 0.28)

    # ---- 12: both reload, then throw at the same time -----------------
    A(22.7, lean_back(452, 1))
    B(22.7, lean_back(516, -1))
    A(23.3, guard(446, 1))
    B(23.3, guard(520, -1))
    A(23.9, idle(444, 1, bob=0.5))
    B(23.9, idle(522, -1, bob=0.5))
    A(24.6, guard(450, 1, crouch=8))
    B(24.6, guard(516, -1, crouch=8))

    # the charge
    A(25.3, cross_out(452, 1, reach=124), "snap")
    B(25.35, cross_out(522, -1, reach=124), "snap")
    whoosh(25.2, 470, 320, size=1.2, direction=1)
    whoosh(25.25, 500, 320, size=1.2, direction=-1)
    hit(25.42, 487, 320, 1.05)
    shake(25.42, 2.0, 0.45, kick=0.08)
    events.append({"t": 25.42, "kind": "flash", "x": 487, "y": 320, "size": 1.4})

    # both recoil, then reset for the last blow
    A(26.1, hit_head(444, 1))
    B(26.1, hit_head(534, -1))
    A(26.7, guard(452, 1))
    B(26.75, guard(522, -1))

    A(27.4, guard(448, 1, crouch=10))
    B(27.4, guard(540, -1, crouch=10))
    A(28.0, uppercut_out(442, 1), "snap")
    B(28.0, uppercut_out(534, -1), "snap")
    hit(28.05, 487, 300, 1.25)
    events.append({"t": 28.05, "kind": "flash", "x": 487, "y": 300, "size": 1.8})
    shake(28.05, 2.4, 0.7, kick=0.10)

    # hold the freeze, then drift apart
    A(28.6, uppercut_out(442, 1), "linear")
    B(28.6, uppercut_out(534, -1), "linear")
    A(29.4, lean_back(440, 1))
    B(29.4, lean_back(534, -1))
    A(30.0, guard(452, 1))
    B(30.0, guard(522, -1))

    # ---- camera --------------------------------------------------------
    camera = [
        # t,     x,    y,   zoom
        (0.0, 482, 268, 1.02),
        (4.6, 486, 266, 1.10),
        (8.0, 486, 268, 1.04),
        (10.5, 488, 266, 1.14),
        (13.5, 490, 266, 1.08),
        (17.0, 482, 272, 1.02),
        (20.0, 486, 268, 1.08),
        (24.0, 486, 268, 1.04),
        (28.0, 488, 264, 1.14),
        (30.0, 488, 268, 1.02),
    ]
    # Put every impact star exactly where the strike meets the body: the
    # choreography is authored by feel, the contact point is measured.
    for e in events:
        if e["kind"] not in ("spark", "flash"):
            continue
        pa, pb = a.at(e["t"]), b.at(e["t"])
        sa, sb = solve(pa), solve(pb)
        options = []
        for fist in (sa.pts[4], sa.pts[6], sa.pts[8], sa.pts[10]):
            options.append((math.dist(fist, sb.head), fist, sb.head))
        for fist in (sb.pts[4], sb.pts[6], sb.pts[8], sb.pts[10]):
            options.append((math.dist(fist, sa.head), fist, sa.head))
        _d, fist, head = min(options, key=lambda o: o[0])
        k = 0.86 if e.get("kind") == "spark" else 0.5
        e["x"] = fist[0] + (head[0] - fist[0]) * k
        e["y"] = fist[1] + (head[1] - fist[1]) * k

    return {"a": a, "b": b, "events": events, "camera": camera}


# ---------------------------------------------------------------- air helpers
def airborne_offset(t: float, t0: float, t1: float, apex: float = 60.0) -> float:
    """Vertical offset for a jump between t0 and t1 (negative = up)."""
    if t <= t0 or t >= t1:
        return 0.0
    u = (t - t0) / (t1 - t0)
    return -apex * math.sin(math.pi * u)
