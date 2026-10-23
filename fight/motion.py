"""Human-ish motion for a 2-D stick rig.

The previous version animated *poses*: a key pose, another key pose, a linear
blend between them. That reads as a puppet being posed, not as a body moving,
because real movement is layered:

* the **feet stay where they were put** — the body travels over them, and a foot
  only leaves the ground to take a step;
* the **hips lead**. A punch starts in the legs and the pelvis, the shoulder
  arrives a frame later, the fist a frame after that;
* nothing goes in a straight line: the hand travels on an arc, the body
  overshoots and settles;
* a body at rest is never still — breath, weight shift, small head drift.

So this module builds motion out of *channels* instead of poses:

    root x        where the pelvis is (moves over planted feet)
    lean, crouch  spine angle and hip height (softness / weight)
    hand targets  two points in space per hand
    feet          simulated: planted, or swinging along an authored kick

and samples them with splines, per-channel lag and an idle layer. The IK in
``core.py`` turns those targets into joint angles.
"""
from __future__ import annotations

import math

from .core import (EASES, Pose, SEG, clamp, pose_from_targets, solve)

HIP = 129.0          # hip to sole, unstretched
SHOULDER = 78.0      # hip to neck


# --------------------------------------------------------------------- tracks
def _catmull(p0, p1, p2, p3, u: float):
    """Uniform Catmull-Rom, with an ease applied to u before the spline."""
    u2, u3 = u * u, u * u * u
    return (0.5 * ((2 * p1) + (-p0 + p2) * u
                   + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u2
                   + (-p0 + 3 * p1 - 3 * p2 + p3) * u3))


class Scalar:
    """A spline through scalar keys. Overshoot is a feature, not a bug."""

    def __init__(self, v: float = 0.0):
        self.keys: list[tuple[float, float, str]] = [(0.0, float(v), "smooth")]

    def key(self, t: float, v: float, ease: str = "smooth") -> "Scalar":
        self.keys = [k for k in self.keys if abs(k[0] - t) > 1e-9]
        self.keys.append((float(t), float(v), ease))
        self.keys.sort(key=lambda k: k[0])
        return self

    def at(self, t: float) -> float:
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        if t >= ks[-1][0]:
            return ks[-1][1]
        for i in range(len(ks) - 1):
            t0, v0, _ = ks[i]
            t1, v1, e1 = ks[i + 1]
            if t0 <= t <= t1:
                u = EASES[e1]((t - t0) / max(t1 - t0, 1e-9))
                p1, p2 = v0, v1
                p0 = ks[i - 1][1] if i > 0 else p1 - (p2 - p1) * 0.35
                p3 = ks[i + 2][1] if i + 2 < len(ks) else p2 + (p2 - p1) * 0.55
                return _catmull(p0, p1, p2, p3, u)
        return ks[-1][1]


class Vec2:
    """A spline through 2-D keys (hand targets, kick targets)."""

    def __init__(self, v=(0.0, 0.0)):
        self.keys: list[tuple[float, tuple, str]] = [(0.0, (float(v[0]), float(v[1])), "smooth")]

    def key(self, t: float, v, ease: str = "smooth") -> "Vec2":
        self.keys = [k for k in self.keys if abs(k[0] - t) > 1e-9]
        self.keys.append((float(t), (float(v[0]), float(v[1])), ease))
        self.keys.sort(key=lambda k: k[0])
        return self

    def at(self, t: float):
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        if t >= ks[-1][0]:
            return ks[-1][1]
        for i in range(len(ks) - 1):
            t0, v0, _ = ks[i]
            t1, v1, e1 = ks[i + 1]
            if t0 <= t <= t1:
                u = EASES[e1]((t - t0) / max(t1 - t0, 1e-9))
                x0, y0 = v0
                x1, y1 = v1
                px, py = (ks[i - 1][1] if i > 0 else (x0 - (x1 - x0) * 0.35,
                                                     y0 - (y1 - y0) * 0.35))
                nx, ny = (ks[i + 2][1] if i + 2 < len(ks) else (x1 + (x1 - x0) * 0.55,
                                                               y1 + (y1 - y0) * 0.55))
                return (_catmull(px, x0, x1, nx, u), _catmull(py, y0, y1, ny, u))
        return ks[-1][1]


# -------------------------------------------------------------------- footwork
class Feet:
    """Planted feet with automatic stepping, plus authored kicks and air time.

    ``simulate`` walks the whole film at 1/48 s and records where each foot is,
    so sampling is a lookup and the result is deterministic frame to frame.
    """

    def __init__(self, ground: float, facing: int, stance: float = 56.0,
                 trigger: float = 17.0, step_time: float = 0.17, lift: float = 11.0):
        self.ground = ground
        self.facing = facing
        self.stance = stance
        self.trigger = trigger
        self.step_time = step_time
        self.lift = lift
        self.kicks: list[dict] = []     # {t0, t1, foot, to, arc}
        self.air: list[tuple] = []      # (t0, t1, height)
        self.table: list[tuple] = []    # (t, (x0,y0), (x1,y1))

    def kick(self, t0: float, t1: float, foot: int, to, arc: float = 40.0):
        self.kicks.append({"t0": t0, "t1": t1, "foot": foot, "to": to, "arc": arc})

    def jump(self, t0: float, t1: float, height: float):
        self.air.append((t0, t1, height))

    # -- simulation ------------------------------------------------------
    def simulate(self, root_at, x0: float, t_end: float = 30.0, dt: float = 1 / 48):
        f = self.facing
        # staggered stance: lead foot forward, rear foot back — feet side by side
        # read as a tripod, staggered feet read as a fighter
        xs = [x0 + f * self.stance * 0.58, x0 - f * self.stance * 0.42]
        swing = [None, None]            # (t0, t1, from_x, to_x)
        self.table = []
        t = 0.0
        while t <= t_end + 1e-9:
            root = root_at(t)
            air = next((a for a in self.air if a[0] <= t < a[1]), None)
            if air is None:
                for k, kk in enumerate(self.kicks):
                    if kk["t0"] <= t < kk["t1"]:
                        break
                else:
                    kk = None
                # decide on a step
                if kk is None:
                    mid = (xs[0] + xs[1]) * 0.5
                    err = root - mid
                    if abs(err) > self.trigger and not any(s for s in swing):
                        d = 1.0 if err > 0 else -1.0
                        trail = 0 if (xs[0] - mid) * d < (xs[1] - mid) * d else 1
                        to_x = root + d * self.stance * 0.42
                        swing[trail] = (t, t + self.step_time, xs[trail], to_x)
                for i in (0, 1):
                    s = swing[i]
                    if s is None:
                        continue
                    if t >= s[1]:
                        xs[i] = s[3]
                        swing[i] = None
            pos = []
            for i in (0, 1):
                # a kick overrides the foot entirely
                kick = next((kk for kk in self.kicks if kk["foot"] == i and
                             kk["t0"] <= t <= kk["t1"]), None)
                if kick is not None:
                    u = clamp((t - kick["t0"]) / max(kick["t1"] - kick["t0"], 1e-9))
                    plant = (xs[i], self.ground)
                    tgx, tgy = kick["to"]
                    # out along an arc, then back down onto the original plant:
                    # a kick is a fold and unfold, never a drag along the floor
                    if u < 0.55:
                        k = (u / 0.55) ** 0.72
                        x = plant[0] + (tgx - plant[0]) * k
                        y = plant[1] + (tgy - plant[1]) * k - math.sin(math.pi * min(1.0, k)) * kick["arc"] * 0.35
                    else:
                        k = (u - 0.55) / 0.45
                        k = k * k * (3 - 2 * k)
                        x = tgx + (plant[0] - tgx) * k
                        y = tgy + (plant[1] - tgy) * k - math.sin(math.pi * k) * kick["arc"] * 0.45
                    pos.append((x, y))
                    continue
                if air is not None:
                    u = (t - air[0]) / max(air[1] - air[0], 1e-9)
                    tuck = math.sin(math.pi * u)
                    pos.append((root + (-1 if i == 0 else 1) * (16 + 10 * tuck),
                                self.ground - air[2] - 34 * tuck - 42 * min(1.0, u * 3.0)))
                    continue
                s = swing[i]
                if s is None:
                    pos.append((xs[i], self.ground))
                else:
                    u = clamp((t - s[0]) / max(s[1] - s[0], 1e-9))
                    x = s[2] + (s[3] - s[2]) * (u * u * (3 - 2 * u))
                    y = self.ground - math.sin(math.pi * u) * self.lift
                    pos.append((x, y))
            self.table.append((t, pos[0], pos[1]))
            t += dt

    # -- sampling --------------------------------------------------------
    def at(self, t: float):
        tb = self.table
        if not tb:
            return ((0.0, self.ground), (0.0, self.ground))
        if t <= tb[0][0]:
            return tb[0][1], tb[0][2]
        if t >= tb[-1][0]:
            return tb[-1][1], tb[-1][2]
        lo, hi = 0, len(tb) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if tb[mid][0] <= t:
                lo = mid
            else:
                hi = mid
        t0, a0, b0 = tb[lo]
        t1, a1, b1 = tb[hi]
        u = clamp((t - t0) / max(t1 - t0, 1e-9))
        lerp = lambda p, q: (p[0] + (q[0] - p[0]) * u, p[1] + (q[1] - p[1]) * u)
        return lerp(a0, a1), lerp(b0, b1)

    def grounded(self, t: float) -> bool:
        return any(a[0] <= t < a[1] for a in self.air)


# ------------------------------------------------------------------- performer
class Performer:
    """One fighter: channels in, a solved ``Pose`` out."""

    def __init__(self, x0: float, ground: float, facing: int, scale: float = 1.0):
        self.ground = ground
        self.facing = facing
        self.scale = scale
        self.root = Scalar(x0)
        self.lean = Scalar(-0.04)
        self.crouch = Scalar(0.0)
        self.head_turn = Scalar(0.0)
        self.hand_a = Vec2((40.0, -22.0))     # far hand, relative to the shoulder
        self.hand_b = Vec2((20.0, 2.0))       # near hand
        self.feet = Feet(ground, facing)
        self._hands_world_ok = False
        # idle layer: slow breathing + weight drift, keeps stillness alive
        self.breath_amp = 2.0
        self.breath_rate = 0.30
        # a fighter is never still: a light bounce on the balls of the feet plus
        # a weight shift left/right, both a touch faster than breathing
        self.bob_amp = 3.4
        self.bob_rate = 1.15
        self.sway_amp = 2.6
        self.sway_rate = 0.55
        self.phase = 0.0 if facing > 0 else 1.7

    # -- authoring shortcuts --------------------------------------------
    def key_pose(self, t: float, root=None, lean=None, crouch=None, head_turn=None,
                 ha=None, hb=None, ease: str = "smooth"):
        if root is not None:
            self.root.key(t, root, ease)
        if lean is not None:
            self.lean.key(t, lean, ease)
        if crouch is not None:
            self.crouch.key(t, crouch, ease)
        if head_turn is not None:
            self.head_turn.key(t, head_turn, ease)
        if ha is not None:
            self.hand_a.key(t, ha, ease)
        if hb is not None:
            self.hand_b.key(t, hb, ease)
        return self

    def shoulder_at(self, t: float, root: float | None = None):
        """Where the neck is, from the channels only (used to aim at a head)."""
        r = self.root.at(t) if root is None else root
        hip = (r, self.ground - HIP * self.scale + self.crouch.at(t))
        ang = -math.pi / 2 + self.lean.at(t)
        return (hip[0] + math.cos(ang) * SHOULDER * self.scale,
                hip[1] + math.sin(ang) * SHOULDER * self.scale)

    def head_at(self, t: float, root: float | None = None):
        sx, sy = self.shoulder_at(t, root)
        ang = -math.pi / 2 + self.lean.at(t)
        return (sx + math.cos(ang) * 22 * self.scale, sy + math.sin(ang) * 22 * self.scale)

    def torso_at(self, t: float) -> float:
        return -math.pi / 2 + self.lean.at(t)

    # -- sampling --------------------------------------------------------
    def pose_at(self, t: float) -> Pose:
        """Solve the fighter at ``t``.

        Timing is spread on purpose: the hips come from ``t``, the hands from a
        frame earlier (drag / follow-through) and the head from two frames
        earlier, so a fast turn whips the head and a punch leaves the hand behind
        the body for one frame before it lands.
        """
        f = self.facing
        s = self.scale

        # idle layer -----------------------------------------------------
        ph = 2 * math.pi * self.breath_rate * t + self.phase
        breath = math.sin(ph) * self.breath_amp
        # bounce: two bobs per sway, so the weight visibly rocks between the feet
        bob = -abs(math.sin(math.pi * self.bob_rate * t + self.phase)) * self.bob_amp
        shift = math.sin(2 * math.pi * self.sway_rate * t + self.phase * 0.7) * self.sway_amp
        drift = math.sin(ph * 0.41 + 1.2) * 1.6

        root = self.root.at(t) + drift * 0.6 + shift
        crouch = self.crouch.at(t) + breath + bob
        lean = self.lean.at(t)
        # the hip height follows the stance: with the feet apart the legs must be
        # allowed to bend, otherwise the IK clamps at full extension and the
        # figure locks its knees and splays like a tripod
        fa, fb = self.feet.at(t)
        # hip height from the *planted* foot; an airborne kick must not drop the
        # pelvis to the floor
        planted = [p for p in (fa, fb) if p[1] >= self.ground - 3.0] or [fa, fb]
        foot_y = max(p[1] for p in planted)
        dxs = [abs(p[0] - self.root.at(t)) for p in planted]
        half = max(dxs) if dxs else 0.0
        # Standing legs are nearly straight: at 0.985 of full extension the knee
        # bend is ~10 deg, which reads as a person. Below ~0.95 the thigh rotates
        # so far forward that the leg turns into a diamond.
        leg = (SEG[7][2] + SEG[8][2]) * s * 0.985
        free = math.sqrt(max(leg * leg - half * half, (leg * 0.55) ** 2))
        hip_y = foot_y - free + crouch
        air = next((a for a in self.feet.air if a[0] <= t < a[1]), None)
        if air is not None:
            u = (t - air[0]) / max(air[1] - air[0], 1e-9)
            hip_y -= math.sin(math.pi * u) * air[2] * 0.55 + min(1.0, u * 3.0) * air[2] * 0.45
        hip = (root, hip_y)

        torso = -math.pi / 2 + lean
        sh = (hip[0] + math.cos(torso) * SHOULDER * s, hip[1] + math.sin(torso) * SHOULDER * s)

        # hands: sampled slightly late, then offset from the shoulder in facing space
        tl = t - 1.0 / 48.0
        ha = self.hand_a.at(tl)
        hb = self.hand_b.at(tl)
        lag = 2.0 / 48.0
        bob_l = -abs(math.sin(math.pi * self.bob_rate * (t - lag) + self.phase)) * self.bob_amp
        hand_a = (sh[0] + f * ha[0], sh[1] + ha[1] + (bob_l - bob) * 0.8)
        hand_b = (sh[0] + f * hb[0], sh[1] + hb[1] + (bob_l - bob) * 0.8)

        # feet: simulated positions, plus a shin extension so a kick reads
        foot_a, foot_b = self.feet.at(t)

        ht = self.head_turn.at(t - 2.0 / 48.0)
        pose = pose_from_targets(hip[0], hip[1], facing=f, scale=s, torso=torso,
                                 head_turn=ht, hand_a=hand_a, hand_b=hand_b,
                                 foot_a=foot_a, foot_b=foot_b,
                                 elbow_a=1.0, elbow_b=-1.0, knee_a=1.0, knee_b=-1.0)
        return pose
