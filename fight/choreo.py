"""The 30-second fight, authored as poses over time.

Each fighter is a list of (time, pose, ease) keys plus a root-x channel. Poses
come from ``poses.py``; foot locking is applied afterwards so a planted foot
stays planted while the body travels over it.

Beat sheet
----------
 0.0 - 2.2   stand-off, both settling into guard
 2.2 - 5.2   lead jab (blocked), rear cross (slips past)
 5.2 - 7.6   body kick blocked, two quick jabs
 7.6 - 9.4   hook slips over the head, uppercut lands
 9.4 -11.6   clinch, shove apart
11.6 -13.6   knee, then a hook into the guard
13.6 -16.2   low sweep jumped, head kick ducked, counter cross lands
16.2 -18.4   circling
18.4 -21.4   exchange: two counters and a fast 1-2
21.4 -23.4   reload, both settle
23.4 -25.6   both throw a cross at the same instant - clash
25.6 -27.8   final exchange, both land a rising blow
27.8 -30.0   both step back, breathe, fade out
"""
from __future__ import annotations

import math

from . import poses as PS
from .core import Pose, clamp, solve
from .poses import fade, mirror, to_pose

GROUND = 432.0
FPS = 24
DURATION = 30.0
RED = (186, 54, 50)
BLUE = (38, 84, 148)

EASE = {
    "smooth": lambda u: u * u * (3 - 2 * u),
    "out": lambda u: 1 - (1 - u) ** 3,
    "snap": lambda u: 1 - (1 - u) ** 5,
    "in": lambda u: u ** 3,
    "linear": lambda u: u,
    "hold": lambda u: 0.0,
}


class Track:
    """Poses + root x over time, sampled with per-segment easing."""

    def __init__(self, name: str, facing: int):
        self.name = name
        self.facing = facing
        self.keys: list[tuple[float, dict, str, float]] = []   # t, pose, ease, root_x

    def key(self, t: float, pose: dict, root_x: float, ease: str = "smooth") -> "Track":
        self.keys = [k for k in self.keys if abs(k[0] - t) > 1e-6]
        self.keys.append((float(t), dict(pose), ease, float(root_x)))
        self.keys.sort(key=lambda k: k[0])
        return self

    def _pair(self, t: float):
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0], ks[0], 0.0
        if t >= ks[-1][0]:
            return ks[-1], ks[-1], 0.0
        for i in range(len(ks) - 1):
            if ks[i][0] <= t <= ks[i + 1][0]:
                a, b = ks[i], ks[i + 1]
                u = (t - a[0]) / max(b[0] - a[0], 1e-9)
                return a, b, EASE.get(b[2], EASE["smooth"])(u)
        return ks[-1], ks[-1], 0.0

    def sample(self, t: float):
        a, b, u = self._pair(t)
        pose = {k: a[1][k] + (b[1][k] - a[1][k]) * u if isinstance(a[1][k], (int, float))
                else (a[1][k][0] + (b[1][k][0] - a[1][k][0]) * u,
                      a[1][k][1] + (b[1][k][1] - a[1][k][1]) * u)
                for k in a[1]}
        root = a[3] + (b[3] - a[3]) * u
        return pose, root

    def pose_at(self, t: float) -> Pose:
        p, root = self.sample(t)
        return to_pose(p, root, GROUND, facing=self.facing)

    def head_at(self, t: float, root: float | None = None):
        p, r = self.sample(t)
        sk = solve(to_pose(p, r if root is None else root, GROUND, facing=self.facing))
        return sk.head

    def hand_at(self, t: float, near: bool = True):
        p, r = self.sample(t)
        sk = solve(to_pose(p, r, GROUND, facing=self.facing))
        return sk.pts[6] if near else sk.pts[4]


def build() -> dict:
    a = Track("red", facing=1)
    b = Track("blue", facing=-1)
    events: list[dict] = []

    def spark(t, size=1.0, kind="spark", anchor=None):
        events.append({"t": t, "kind": kind, "size": size, "anchor": anchor})

    def whoosh(t, dur=0.16, size=1.0, direction=1, y=0.0):
        events.append({"t": t, "kind": "whoosh", "dur": dur, "size": size,
                       "dir": direction, "y": y})

    def dust(t, size=1.0):
        events.append({"t": t, "kind": "dust", "size": size})

    def shake(t, amp=1.0, dur=0.25, kick=0.0):
        events.append({"t": t, "kind": "shake", "amp": amp, "dur": dur, "kick": kick})

    def flash(t, size=1.0):
        events.append({"t": t, "kind": "flash", "size": size})

    G = PS.GUARD
    X_A, X_B = 374.0, 548.0        # starting roots (~164 apart)

    # ---------------------------------------------------------------- opening
    a.key(0.0, PS.IDLE, X_A)
    b.key(0.0, PS.IDLE, X_B)
    a.key(1.0, fade(G, torso=-82), X_A + 2)
    b.key(1.15, fade(G, torso=-82), X_B - 2)
    a.key(2.0, G, X_A + 6)
    b.key(2.05, G, X_B - 6)

    # ---------------------------------------------------------------- jab, blocked
    a.key(2.45, PS.TIGHT, X_A + 14, "out")
    b.key(2.45, PS.BLOCK_HI, X_B - 4, "out")
    a.key(2.72, PS.JAB, X_A + 30, "snap")
    b.key(2.72, PS.BLOCK_HI, X_B - 4, "smooth")
    spark(2.72, 0.45)
    whoosh(2.60, direction=1)
    a.key(3.00, G, X_A + 22, "out")
    b.key(3.05, G, X_B - 8)

    # ---------------------------------------------------------------- cross, slips
    a.key(3.40, fade(PS.TIGHT, torso=-76), X_A + 26, "out")
    b.key(3.45, PS.SLIP, X_B + 4, "out")
    a.key(3.72, PS.CROSS, X_A + 44, "snap")
    whoosh(3.58, direction=1)
    b.key(3.74, PS.SLIP, X_B + 8, "smooth")
    a.key(4.05, G, X_A + 30, "out")
    b.key(4.15, G, X_B)

    # ---------------------------------------------------------------- body kick blocked
    b.key(4.60, fade(PS.TIGHT, torso=-74), X_B - 6, "out")
    b.key(4.95, PS.KICK_MID, X_B - 44, "snap")
    whoosh(4.80, direction=-1, dur=0.2)
    a.key(4.92, PS.BLOCK_MID, X_A + 34, "snap")
    spark(4.98, 0.8)
    shake(4.98, 0.7, 0.22, kick=0.03)
    b.key(5.35, G, X_B - 4, "out")
    a.key(5.40, G, X_A + 28)

    # ---------------------------------------------------------------- two jabs
    a.key(5.85, PS.TIGHT, X_A + 30, "out")
    a.key(6.10, PS.JAB, X_A + 40, "snap")
    b.key(6.10, PS.BLOCK_HI, X_B - 2, "snap")
    whoosh(6.00, direction=1)
    spark(6.10, 0.35)
    a.key(6.32, PS.TIGHT, X_A + 32, "out")
    a.key(6.55, PS.CROSS, X_A + 44, "snap")
    b.key(6.55, PS.BLOCK_HI, X_B - 2, "snap")
    spark(6.55, 0.45)
    a.key(6.85, G, X_A + 30, "out")
    b.key(6.90, G, X_B)

    # ---------------------------------------------------------------- hook slips, uppercut lands
    b.key(7.25, fade(PS.TIGHT, torso=-76), X_B - 8, "out")
    b.key(7.55, PS.HOOK, X_B - 22, "snap")
    whoosh(7.42, direction=-1)
    a.key(7.50, PS.DUCK, X_A + 34, "snap")
    b.key(7.90, PS.TIGHT, X_B - 10, "out")
    a.key(8.05, fade(PS.TIGHT, torso=-76), X_A + 40, "out")
    a.key(8.35, PS.UPPERCUT, X_A + 50, "snap")
    whoosh(8.22, direction=1)
    b.key(8.36, PS.HIT_HEAD, X_B + 6, "snap")
    spark(8.36, 1.0)
    shake(8.36, 1.1, 0.3, kick=0.05)
    a.key(8.70, G, X_A + 40, "out")
    b.key(8.85, fade(G, torso=-84), X_B + 2)

    # ---------------------------------------------------------------- clinch, shove
    a.key(9.30, PS.CLINCH, X_A + 58, "out")
    b.key(9.30, PS.CLINCH, X_B - 10, "out")
    a.key(9.80, fade(PS.CLINCH, torso=-68), X_A + 66)
    b.key(9.80, fade(PS.CLINCH, torso=-68), X_B - 16)
    a.key(10.30, PS.SHOVE, X_A + 50, "out")
    b.key(10.30, PS.SHOVE, X_B - 6, "out")
    shake(10.30, 0.4, 0.25)
    a.key(10.80, G, X_A + 34, "out")
    b.key(10.85, G, X_B - 2, "out")

    # ---------------------------------------------------------------- knee, hook
    a.key(11.25, fade(PS.CLINCH, torso=-76), X_A + 52, "out")
    b.key(11.25, PS.TIGHT, X_B - 8, "out")
    a.key(11.55, PS.KNEE, X_A + 58, "snap")
    whoosh(11.42, direction=1, dur=0.14)
    spark(11.55, 0.7)
    shake(11.55, 0.6, 0.2, kick=0.03)
    b.key(11.55, PS.HIT_BODY, X_B + 2, "snap")
    a.key(11.90, G, X_A + 48, "out")
    b.key(12.00, PS.TIGHT, X_B - 4)
    a.key(12.35, PS.HOOK, X_A + 58, "snap")
    b.key(12.35, PS.BLOCK_HI, X_B - 2, "snap")
    whoosh(12.24, direction=1)
    spark(12.35, 0.9)
    shake(12.35, 0.8, 0.25, kick=0.04)
    a.key(12.70, G, X_A + 46, "out")
    b.key(12.80, G, X_B - 6)

    # ---------------------------------------------------------------- sweep jumped, head kick, counter
    b.key(13.20, fade(PS.TIGHT, torso=-74), X_B - 10, "out")
    b.key(13.55, PS.KICK_LOW, X_B - 40, "snap")
    whoosh(13.44, direction=-1, dur=0.18, y=30)
    a.key(13.45, PS.AIRBORNE, X_A + 40, "snap")
    a.key(13.90, PS.AIRBORNE, X_A + 44, "smooth")
    dust(14.02, 0.5)
    a.key(14.10, PS.LANDED, X_A + 46, "snap")
    b.key(14.05, G, X_B - 6, "out")
    a.key(14.45, G, X_A + 42, "out")

    b.key(14.80, fade(PS.TIGHT, torso=-74), X_B - 8, "out")
    b.key(15.15, PS.KICK_HI, X_B - 52, "snap")
    whoosh(15.02, direction=-1, dur=0.2, y=-40)
    a.key(15.10, PS.SLIP, X_A + 34, "snap")
    b.key(15.55, PS.ONE_LEG, X_B - 6, "out")
    a.key(15.50, fade(PS.TIGHT, torso=-74), X_A + 52, "out")
    a.key(15.82, PS.CROSS, X_A + 64, "snap")
    whoosh(15.70, direction=1)
    b.key(15.82, PS.HIT_HEAD, X_B + 10, "snap")
    spark(15.82, 1.1)
    shake(15.82, 1.2, 0.3, kick=0.05)
    a.key(16.15, G, X_A + 54, "out")
    b.key(16.35, fade(G, torso=-84), X_B + 4)

    # ---------------------------------------------------------------- circling
    a.key(17.10, G, X_A + 50)
    b.key(17.10, G, X_B)
    a.key(18.05, fade(G, torso=-82), X_A + 54)
    b.key(18.05, fade(G, torso=-82), X_B - 6)

    # ---------------------------------------------------------------- exchange
    b.key(18.45, PS.JAB, X_B - 18, "snap")
    whoosh(18.34, direction=-1)
    a.key(18.45, PS.BLOCK_HI, X_A + 58, "snap")
    spark(18.45, 0.5)
    b.key(18.80, G, X_B - 8, "out")
    a.key(18.95, PS.JAB, X_A + 62, "snap")
    whoosh(18.86, direction=1)
    b.key(18.95, PS.BLOCK_HI, X_B - 4, "snap")
    spark(18.95, 0.5)
    a.key(19.30, G, X_A + 56, "out")
    b.key(19.35, G, X_B - 6)
    a.key(19.75, PS.TIGHT, X_A + 58, "out")
    b.key(19.75, PS.TIGHT, X_B - 8, "out")
    a.key(20.05, PS.JAB, X_A + 64, "snap")
    b.key(20.05, PS.BLOCK_MID, X_B - 6, "snap")
    spark(20.05, 0.4)
    a.key(20.35, PS.TIGHT, X_A + 58, "out")
    a.key(20.62, PS.CROSS, X_A + 66, "snap")
    b.key(20.62, PS.BLOCK_HI, X_B - 6, "snap")
    spark(20.62, 0.55)
    a.key(20.95, G, X_A + 56, "out")
    b.key(21.00, G, X_B - 10)

    # ---------------------------------------------------------------- reload
    a.key(21.65, fade(G, torso=-78), X_A + 52)
    b.key(21.65, fade(G, torso=-78), X_B - 12)
    a.key(22.45, fade(G, torso=-80, crouch=10), X_A + 54)
    b.key(22.45, fade(G, torso=-80, crouch=10), X_B - 14)
    a.key(23.05, G, X_A + 62)
    b.key(23.05, G, X_B - 24)

    # ---------------------------------------------------------------- clash
    a.key(23.45, PS.TIGHT, X_A + 66, "out")
    b.key(23.45, PS.TIGHT, X_B - 28, "out")
    a.key(23.78, PS.CROSS, X_A + 78, "snap")
    b.key(23.78, PS.CROSS, X_B - 40, "snap")
    whoosh(23.66, direction=1)
    whoosh(23.66, direction=-1)
    spark(23.78, 1.0, anchor="fists")
    flash(23.78, 0.55)
    shake(23.78, 1.6, 0.4, kick=0.06)
    a.key(24.20, PS.HIT_HEAD, X_A + 58, "out")
    b.key(24.20, PS.HIT_HEAD, X_B - 18, "out")
    a.key(24.75, G, X_A + 52, "out")
    b.key(24.75, G, X_B - 10, "out")

    # ---------------------------------------------------------------- final exchange
    a.key(25.45, PS.TIGHT, X_A + 54, "out")
    b.key(25.45, PS.TIGHT, X_B - 12, "out")
    a.key(25.95, PS.JAB, X_A + 62, "snap")
    b.key(25.95, PS.BLOCK_HI, X_B - 8, "snap")
    spark(25.95, 0.5)
    b.key(26.25, PS.JAB, X_B - 20, "snap")
    a.key(26.25, PS.BLOCK_HI, X_A + 54, "snap")
    spark(26.25, 0.5)
    a.key(26.70, fade(PS.TIGHT, torso=-78), X_A + 58, "out")
    b.key(26.70, fade(PS.TIGHT, torso=-78), X_B - 14, "out")
    a.key(27.05, PS.UPPERCUT, X_A + 68, "snap")
    b.key(27.05, PS.UPPERCUT, X_B - 24, "snap")
    spark(27.05, 1.0, anchor="fists")
    flash(27.05, 0.5)
    shake(27.05, 1.7, 0.42, kick=0.06)
    a.key(27.45, PS.HIT_HEAD, X_A + 54, "out")
    b.key(27.45, PS.HIT_HEAD, X_B - 14, "out")

    # ---------------------------------------------------------------- settle, fade
    a.key(28.30, fade(PS.GUARD, torso=-82), X_A + 40, "out")
    b.key(28.30, fade(PS.GUARD, torso=-82), X_B - 4, "out")
    a.key(29.20, PS.TIRED, X_A + 34, "smooth")
    b.key(29.20, PS.TIRED, X_B, "smooth")
    a.key(30.0, fade(PS.TIRED, torso=-66), X_A + 32)
    b.key(30.0, fade(PS.TIRED, torso=-66), X_B + 2)

    # ---------------------------------------------------------------- foot locking
    # A pose's feet are offsets from the hip, so a moving root drags them along.
    # Walk the keys; whenever a foot stays planted across a key, shift the later
    # root so that foot lands in the same world spot (a step, not a slide).
    def lock(track: Track):
        for i in range(1, len(track.keys)):
            t0, p0, _e0, x0 = track.keys[i - 1]
            t1, p1, e1, x1 = track.keys[i]
            if p0["foot_l"][1] <= 0.5 and p1["foot_l"][1] <= 0.5:
                want = x0 + p0["foot_l"][0] * track.facing
                x1 = want - p1["foot_l"][0] * track.facing
            elif p0["foot_r"][1] <= 0.5 and p1["foot_r"][1] <= 0.5:
                want = x0 + p0["foot_r"][0] * track.facing
                x1 = want - p1["foot_r"][0] * track.facing
            track.keys[i] = (t1, p1, e1, x1)
    # travel is ~0.3 px/frame here, so a full lock would only cancel the staging;
    # a light lock keeps the feet from skating without freezing the advance.
    K = 0.25

    def lock_blend(track: Track):
        base = [k[3] for k in track.keys]
        lock(track)
        for i, (t, p, e, x) in enumerate(track.keys):
            track.keys[i] = (t, p, e, base[i] + (x - base[i]) * K)
    lock_blend(a)
    lock_blend(b)

    # how close the two heads may get, over time: almost touching in the clinch,
    # a fist-plus-forearm apart everywhere else
    gap_keys = [(0.0, 176.0), (4.6, 172.0), (4.95, 152.0), (5.4, 172.0),
                (9.0, 172.0), (9.5, 138.0), (10.5, 138.0), (11.1, 168.0),
                (13.25, 168.0), (13.55, 152.0), (14.2, 172.0),
                (14.9, 168.0), (15.15, 146.0), (15.5, 162.0), (16.2, 174.0),
                (23.6, 170.0), (24.2, 174.0), (28.2, 178.0), (30.0, 182.0)]

    def gap_at(t):
        if t <= gap_keys[0][0]:
            return gap_keys[0][1]
        for i in range(len(gap_keys) - 1):
            t0, g0 = gap_keys[i]
            t1, g1 = gap_keys[i + 1]
            if t0 <= t <= t1:
                u = (t - t0) / max(t1 - t0, 1e-9)
                return g0 + (g1 - g0) * (u * u * (3 - 2 * u))
        return gap_keys[-1][1]

    # ---------------------------------------------------------------- separation
    # Sample the whole timeline and relax the roots apart wherever the heads get
    # closer than the beat allows, so the pair never collapses into one blob.
    def relax(iters=4, step=0.08):
        for _ in range(iters):
            t = 0.0
            while t <= 30.0:
                g = b.head_at(t)[0] - a.head_at(t)[0]
                want = gap_at(t)
                if g < want - 0.5:
                    push = (want - g) * 0.5
                    for tr, sgn in ((a, -1.0), (b, 1.0)):
                        ks = tr.keys
                        for i in range(len(ks) - 1):
                            t0, p0, e0, x0 = ks[i]
                            t1, p1, e1, x1 = ks[i + 1]
                            if t0 <= t <= t1:
                                u = (t - t0) / max(t1 - t0, 1e-9)
                                w0, w1 = (1 - u) ** 2, u * u
                                ks[i] = (t0, p0, e0, x0 + sgn * push * w0 * step * 4)
                                ks[i + 1] = (t1, p1, e1, x1 + sgn * push * w1 * step * 4)
                                break
                t += 0.1
    relax()

    # ---------------------------------------------------------------- effect anchors
    for e in events:
        t = e["t"]
        pa, pb = a.pose_at(t), b.pose_at(t)
        sa, sb = solve(pa), solve(pb)
        if e["kind"] in ("spark", "flash") and e.get("anchor") == "fists":
            # two punches meeting in the air: the star sits between the fists
            fa = min((sa.pts[4], sa.pts[6]), key=lambda p: abs(p[0] - sb.head[0]))
            fb = min((sb.pts[4], sb.pts[6]), key=lambda p: abs(p[0] - sa.head[0]))
            e["x"] = (fa[0] + fb[0]) * 0.5
            e["y"] = (fa[1] + fb[1]) * 0.5
        elif e["kind"] in ("spark", "flash"):
            # anchor the impact where the nearest limb of one fighter meets the
            # nearest body target of the other: head first, then the torso
            def torso(sk):
                hip, sh = sk.starts[1], sk.pts[1]
                return ((hip[0] + sh[0]) * 0.5, (hip[1] + sh[1]) * 0.5)
            cands = []
            for own, other in ((sa, sb), (sb, sa)):
                for i in (4, 6, 8, 10):
                    for target in (other.head, torso(other)):
                        d = math.hypot(target[0] - own.pts[i][0], target[1] - own.pts[i][1])
                        cands.append((d, own.pts[i], target))
            d, limb, target = min(cands, key=lambda c: c[0])
            d = max(d, 1.0)
            e["x"] = target[0] + (limb[0] - target[0]) / d * 16.0
            e["y"] = target[1] + (limb[1] - target[1]) / d * 12.0
        elif e["kind"] == "whoosh":
            e["x"] = (sa.head[0] + sb.head[0]) * 0.5 + e.get("dir", 1) * 10
            e["y"] = 300 + e.get("y", 0)
        elif e["kind"] == "dust":
            e["x"] = (a.head_at(t)[0] + b.head_at(t)[0]) * 0.5
            e["y"] = GROUND

    camera = [
        (0.0, 452, 286, 1.24),
        (4.6, 458, 284, 1.34),
        (8.2, 462, 286, 1.28),
        (11.4, 466, 284, 1.38),
        (14.2, 460, 282, 1.32),
        (17.6, 458, 286, 1.26),
        (20.6, 464, 284, 1.36),
        (23.7, 468, 282, 1.44),
        (25.0, 464, 284, 1.34),
        (27.1, 468, 282, 1.46),
        (28.6, 462, 286, 1.30),
        (30.0, 460, 288, 1.22),
    ]
    return {"a": a, "b": b, "events": events, "camera": camera}
