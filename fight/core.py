"""Headless player for StykAnimate / Pivot stick-figure documents.

The figure definition, angle convention and drawing order are taken from the
StykAnimate source (``vendor/stykanimate/src/demo.mjs``, GPL-3.0-or-later):

    segment(id, parent, length, angle, thickness)
      1  -    78   torso   (hip -> neck)
      2  1    44   head circle at the neck
      3  1    53  arm A upper     4 3  48  arm A fore
      5  1    53  arm B upper     6 5  48  arm B fore
      7  0    66  leg A thigh     8 7  63  leg A shin
      9  0    66  leg B thigh    10 9  63  leg B shin

Angles are absolute, in canvas space (x right, y down, so -pi/2 is straight up),
which is exactly how the app stores ``angles`` per object. A child segment starts
where its parent ends, so the neck carries both arms and the head, and the hip
carries both legs.

On top of that model this module adds the thing the file format does not have:
posing by *target*, i.e. two-bone IK for hands and feet. Authoring a fight by
angle is guesswork; authoring it by where the fist or the foot has to be is not.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

TAU = math.pi * 2

# ----------------------------------------------------------------- the figure
#: (id, parent, length, thickness, kind) — straight from StykAnimate's Walker.
FIGURE = (
    (1, 0, 78.0, 11.0, "line"),
    (2, 1, 44.0, 8.0, "circle"),
    (3, 1, 53.0, 9.0, "line"),
    (4, 3, 48.0, 8.0, "line"),
    (5, 1, 53.0, 9.0, "line"),
    (6, 5, 48.0, 8.0, "line"),
    (7, 0, 66.0, 11.0, "line"),
    (8, 7, 63.0, 10.0, "line"),
    (9, 0, 66.0, 11.0, "line"),
    (10, 9, 63.0, 10.0, "line"),
)

SEG = {s[0]: s for s in FIGURE}
INK = (43, 43, 43)
SEGMENT_ORDER = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


@dataclass
class Pose:
    """One figure state: root position, torso angle, and limb angles 1..10."""

    x: float = 0.0
    y: float = 0.0
    facing: int = 1
    scale: float = 1.0
    head_turn: float = 0.0
    angles: tuple = (0.0,) * 10

    def copy(self, **kw) -> "Pose":
        return replace(self, **kw)

    def vec(self) -> np.ndarray:
        return np.array([self.x, self.y, self.facing, self.scale, self.head_turn, *self.angles],
                        dtype=np.float64)

    @staticmethod
    def from_vec(v) -> "Pose":
        v = [float(a) for a in v]
        return Pose(x=v[0], y=v[1], facing=(1 if v[2] >= 0 else -1), scale=v[3],
                    head_turn=v[4], angles=tuple(v[5:15]))


def angles_of(*vals) -> tuple:
    return tuple(float(v) for v in vals)


# ------------------------------------------------------------------------ IK
def _two_bone(start, target, l1: float, l2: float, bend: float = 1.0):
    """Absolute angles for a two-segment chain reaching ``target``.

    ``bend`` picks which of the two solutions to use (+1 / -1), i.e. whether the
    elbow or knee folds one way or the other.
    """
    dx, dy = target[0] - start[0], target[1] - start[1]
    d = math.hypot(dx, dy)
    d = max(min(d, l1 + l2 - 0.01), abs(l1 - l2) + 0.01)
    base = math.atan2(dy, dx)
    cos_a = (d * d + l1 * l1 - l2 * l2) / (2 * d * l1)
    a = math.acos(max(-1.0, min(1.0, cos_a)))
    a = a * (1.0 if bend >= 0 else -1.0)
    mid = (start[0] + math.cos(base + a) * l1, start[1] + math.sin(base + a) * l1)
    return (base + a, math.atan2(target[1] - mid[1], target[0] - mid[0]))


def pose_from_targets(x: float, y: float, *, facing: int = 1, scale: float = 1.0,
                      torso: float = -math.pi / 2, head_turn: float = 0.0,
                      hand_a=None, hand_b=None, foot_a=None, foot_b=None,
                      elbow_a: float = 1.0, elbow_b: float = 1.0,
                      knee_a: float = 1.0, knee_b: float = -1.0) -> Pose:
    """Build a Pose from where the hands and feet should be (world coords).

    ``hand_a`` / ``foot_a`` are the *far* side limbs (drawn first, behind the
    body), ``b`` the near ones. Any limb left as ``None`` falls back to the
    neutral StykAnimate walker angles.
    """
    s = scale
    hip = (x, y)
    neck = (hip[0] + math.cos(torso) * SEG[1][2] * s, hip[1] + math.sin(torso) * SEG[1][2] * s)
    a = list(SEG[i][3] for i in range(1, 11))  # placeholders, overwritten below
    a[0] = torso
    a[1] = torso + head_turn  # head "angle" is unused for a circle

    if hand_a is None:
        hand_a = (neck[0] + math.cos(1.05) * (SEG[3][2] + SEG[4][2]) * s,
                  neck[1] + math.sin(1.05) * (SEG[3][2] + SEG[4][2]) * s)
    if hand_b is None:
        hand_b = (neck[0] + math.cos(2.02) * (SEG[5][2] + SEG[6][2]) * s,
                  neck[1] + math.sin(2.02) * (SEG[5][2] + SEG[6][2]) * s)
    if foot_a is None:
        foot_a = (hip[0] + math.cos(1.12) * (SEG[7][2] + SEG[8][2]) * s,
                  hip[1] + math.sin(1.12) * (SEG[7][2] + SEG[8][2]) * s)
    if foot_b is None:
        foot_b = (hip[0] + math.cos(2.00) * (SEG[9][2] + SEG[10][2]) * s,
                  hip[1] + math.sin(2.00) * (SEG[9][2] + SEG[10][2]) * s)

    ua, fa = _two_bone(neck, hand_a, SEG[3][2] * s, SEG[4][2] * s, elbow_a)
    ub, fb = _two_bone(neck, hand_b, SEG[5][2] * s, SEG[6][2] * s, elbow_b)
    ta, sa = _two_bone(hip, foot_a, SEG[7][2] * s, SEG[8][2] * s, knee_a)
    tb, sb = _two_bone(hip, foot_b, SEG[9][2] * s, SEG[10][2] * s, knee_b)
    a[2], a[3], a[4], a[5], a[6], a[7], a[8], a[9] = ua, fa, ub, fb, ta, sa, tb, sb
    return Pose(x=x, y=y, facing=facing, scale=s, head_turn=head_turn, angles=tuple(a))


# ---------------------------------------------------------------------- solve
@dataclass
class Skeleton:
    pts: dict = field(default_factory=dict)      # segment id -> tip position
    starts: dict = field(default_factory=dict)   # segment id -> start position
    head: tuple = (0.0, 0.0)
    head_r: float = 0.0
    facing: int = 1
    scale: float = 1.0


def solve(pose: Pose) -> Skeleton:
    pts = {0: (pose.x, pose.y)}
    starts, ends = {}, {}
    for sid in SEGMENT_ORDER:
        _id, parent, length, _th, kind = SEG[sid]
        start = pts[parent]
        a = pose.angles[sid - 1]
        end = (start[0] + math.cos(a) * length * pose.scale,
               start[1] + math.sin(a) * length * pose.scale)
        starts[sid] = start
        ends[sid] = end
        pts[sid] = end  # a circle's end is its far rim point; the chain stops there
    # StykAnimate draws a circle centred on (start+end)/2 with radius = length/2
    head_c = ((starts[2][0] + ends[2][0]) * 0.5, (starts[2][1] + ends[2][1]) * 0.5)
    return Skeleton(pts=ends, starts=starts, head=head_c,
                    head_r=SEG[2][2] * 0.5 * pose.scale, facing=pose.facing, scale=pose.scale)


def plant(pose: Pose, ground: float, which=(8, 10)) -> Pose:
    """Shift the figure so its lowest foot rests on ``ground``."""
    sk = solve(pose)
    low = max(sk.pts[i][1] for i in which)
    return pose.copy(y=pose.y + (ground - low))


def head_top(pose: Pose) -> float:
    sk = solve(pose)
    return sk.head[1] - sk.head_r


# --------------------------------------------------------------------- easing
def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def smooth(u: float) -> float:
    u = clamp(u)
    return u * u * (3 - 2 * u)


def ease_out(u: float) -> float:
    u = clamp(u)
    return 1 - (1 - u) ** 3


def ease_in(u: float) -> float:
    u = clamp(u)
    return u ** 3


def snap(u: float, power: float = 5.0) -> float:
    """Very fast attack, used for strikes: most of the travel in the first 30 %."""
    u = clamp(u)
    return 1 - (1 - u) ** power


def back_out(u: float, k: float = 1.6) -> float:
    u = clamp(u)
    return 1 + (k + 1) * (u - 1) ** 3 + k * (u - 1) ** 2


EASES = {"smooth": smooth, "out": ease_out, "in": ease_in, "snap": snap, "back": back_out,
         "linear": clamp}


def lerp_pose(a: Pose, b: Pose, u: float) -> Pose:
    """Blend two poses. Poses are stored as flat vectors, so this is one lerp."""
    if u <= 0:
        return a
    if u >= 1:
        return b
    return Pose.from_vec(a.vec() + (b.vec() - a.vec()) * u)


class Track:
    """Keyed pose track, sampled with an easing per segment."""

    def __init__(self, pose: Pose | None = None):
        self.keys: list[tuple[float, Pose, str]] = [(0.0, pose or Pose(), "smooth")]

    def key(self, t: float, pose: Pose, ease: str = "smooth") -> "Track":
        self.keys.append((float(t), pose, ease))
        self.keys.sort(key=lambda k: k[0])
        return self

    def at(self, t: float) -> Pose:
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        if t >= ks[-1][0]:
            return ks[-1][1]
        for i in range(len(ks) - 1):
            t0, p0, _ = ks[i]
            t1, p1, e1 = ks[i + 1]
            if t0 <= t <= t1:
                u = EASES[e1]((t - t0) / max(t1 - t0, 1e-9))
                return lerp_pose(p0, p1, u)
        return ks[-1][1]
