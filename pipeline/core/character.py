"""Stick-figure character rig: FK skeleton, pose library, smears, rim light.

Angle convention
----------------
Bones use *absolute* angles in degrees measured from "straight down", rotating
toward +x (forward) as the angle grows:

    0°   straight down
    90°  forward (+x)
    180° straight up
   -90°  backward (-x)

Characters are authored facing +x and mirrored by ``facing = -1``, so every pose
can be re-used for either side of a fight.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Iterable, Sequence

import numpy as np

from .easing import Track, clamp, ease, lerp

D2R = math.pi / 180.0


def dirv(deg: float) -> tuple[float, float]:
    r = deg * D2R
    return math.sin(r), math.cos(r)


@dataclass
class Rig:
    """Bone lengths, in world units (1.0 = 1080p pixel)."""

    spine: float = 78.0
    neck: float = 20.0
    head_r: float = 26.0
    upper_arm: float = 58.0
    fore_arm: float = 55.0
    thigh: float = 68.0
    shin: float = 65.0
    foot: float = 21.0
    hand_r: float = 7.0
    # stroke widths (world units; ~7 px at zoom 1 looks like a bold marker line)
    w_spine: float = 11.0
    w_arm: float = 8.2
    w_fore: float = 6.8
    w_leg: float = 9.6
    w_shin: float = 7.4
    shoulder_w: float = 21.0
    hip_w: float = 15.0


@dataclass
class Pose:
    """One authored body position. Missing channels inherit from the base pose."""

    px: float = 0.0          # pelvis x (world)
    py: float = 0.0          # pelvis y (world)
    spine: float = 0.0       # pelvis -> chest angle
    neck: float = 180.0      # chest -> neck angle
    head: float = 180.0      # head tilt (visual rotation, not a bone)
    arm_f: tuple[float, float] = (8.0, 12.0)      # shoulder, elbow (front arm)
    arm_b: tuple[float, float] = (-8.0, -12.0)    # shoulder, elbow (back arm)
    leg_f: tuple[float, float, float] = (10.0, 2.0, 90.0)   # hip, knee, foot
    leg_b: tuple[float, float, float] = (-10.0, -2.0, 90.0)
    facing: int = 1
    scale: float = 1.0
    squash: float = 1.0      # 1 = neutral; <1 squashed (wide), >1 stretched
    lean_off: float = 0.0    # extra hip translation for weight shifts
    bob: float = 0.0
    head_turn: float = 0.0   # -1..1 profile amount for the head "cheek" mark

    def copy(self, **kw) -> "Pose":
        return replace(self, **kw)

    def lerp(self, other: "Pose", t: float) -> "Pose":
        def L(a, b):
            return lerp(a, b, t)

        def Lt(a, b):
            return tuple(L(x, y) for x, y in zip(a, b))

        return Pose(
            px=L(self.px, other.px), py=L(self.py, other.py),
            spine=L(self.spine, other.spine), neck=L(self.neck, other.neck),
            head=L(self.head, other.head),
            arm_f=Lt(self.arm_f, other.arm_f), arm_b=Lt(self.arm_b, other.arm_b),
            leg_f=Lt(self.leg_f, other.leg_f), leg_b=Lt(self.leg_b, other.leg_b),
            scale=L(self.scale, other.scale), squash=L(self.squash, other.squash),
            lean_off=L(self.lean_off, other.lean_off), bob=L(self.bob, other.bob),
            head_turn=L(self.head_turn, other.head_turn),
            facing=self.facing if t < 1 else other.facing,
        )


@dataclass
class Skeleton:
    pelvis: tuple[float, float]
    chest: tuple[float, float]
    neck: tuple[float, float]
    head_c: tuple[float, float]
    head_r: float
    shoulder: tuple[float, float]
    elbow_f: tuple[float, float]
    hand_f: tuple[float, float]
    elbow_b: tuple[float, float]
    hand_b: tuple[float, float]
    hip: tuple[float, float]
    knee_f: tuple[float, float]
    foot_f: tuple[float, float]
    knee_b: tuple[float, float]
    foot_b: tuple[float, float]
    to_f: tuple[float, float]
    to_b: tuple[float, float]
    facing: int = 1
    scale: float = 1.0


def solve(pose: Pose, rig: Rig) -> Skeleton:
    """Forward kinematics for one pose."""
    f = pose.facing
    s = pose.scale
    sq = pose.squash

    def pt(origin, length, ang, sy=1.0):
        dx, dy = dirv(ang)
        return (origin[0] + f * dx * length * s * sq, origin[1] + dy * length * s / sq * sy)

    px = pose.px + f * pose.lean_off * s
    py = pose.py + pose.bob * s
    pelvis = (px, py)
    chest = pt(pelvis, rig.spine * 0.55, pose.spine)
    neck = pt(chest, rig.spine * 0.45, pose.spine * 0.85)
    # head sits above the neck joint
    hx, hy = dirv(pose.neck)
    head_c = (neck[0] + f * hx * (rig.head_r + rig.neck * 0.25) * s,
              neck[1] + hy * (rig.head_r + rig.neck * 0.25) * s)

    sh = pt(chest, 0.0, pose.spine)
    shoulder = (sh[0] + f * 0.0, sh[1] + 2 * s)

    ex_f, ey_f = dirv(pose.arm_f[0])
    elbow_f = (shoulder[0] + f * ex_f * rig.upper_arm * s, shoulder[1] + ey_f * rig.upper_arm * s)
    hx2, hy2 = dirv(pose.arm_f[1])
    hand_f = (elbow_f[0] + f * hx2 * rig.fore_arm * s, elbow_f[1] + hy2 * rig.fore_arm * s)

    bx, by = dirv(pose.arm_b[0])
    elbow_b = (shoulder[0] + f * bx * rig.upper_arm * s, shoulder[1] + by * rig.upper_arm * s)
    bx2, by2 = dirv(pose.arm_b[1])
    hand_b = (elbow_b[0] + f * bx2 * rig.fore_arm * s, elbow_b[1] + by2 * rig.fore_arm * s)

    hip = (pelvis[0], pelvis[1] + 6 * s)
    hxp, hyp = dirv(pose.leg_f[0])
    knee_f = (hip[0] + f * hxp * rig.thigh * s * sq, hip[1] + hyp * rig.thigh * s / sq)
    kx, ky = dirv(pose.leg_f[1])
    foot_f = (knee_f[0] + f * kx * rig.shin * s * sq, knee_f[1] + ky * rig.shin * s / sq)
    tx, ty = dirv(pose.leg_f[2])
    to_f = (foot_f[0] + f * tx * rig.foot * s, foot_f[1] + ty * rig.foot * s)

    hxb, hyb = dirv(pose.leg_b[0])
    knee_b = (hip[0] + f * hxb * rig.thigh * s * sq, hip[1] + hyb * rig.thigh * s / sq)
    kxb, kyb = dirv(pose.leg_b[1])
    foot_b = (knee_b[0] + f * kxb * rig.shin * s * sq, knee_b[1] + kyb * rig.shin * s / sq)
    txb, tyb = dirv(pose.leg_b[2])
    to_b = (foot_b[0] + f * txb * rig.foot * s, foot_b[1] + tyb * rig.foot * s)

    return Skeleton(pelvis, chest, neck, head_c, rig.head_r * s * (1 + 0.03 * (sq - 1)),
                    shoulder, elbow_f, hand_f, elbow_b, hand_b, hip,
                    knee_f, foot_f, knee_b, foot_b, to_f, to_b, f, s)


# --------------------------------------------------------------------- colours
@dataclass
class Look:
    color: tuple = (0.86, 0.90, 0.96)
    ink: tuple = (0.02, 0.025, 0.04)
    rim: tuple = (0.45, 0.75, 1.0)
    rim_amount: float = 0.8
    aura: tuple = (0.25, 0.6, 1.0)
    aura_amount: float = 0.0
    eye: tuple = (0.9, 0.95, 1.0)
    glow: float = 1.0
    trail: tuple = (0.4, 0.7, 1.0)
    w_scale: float = 1.0
    head_style: str = "light"       # "light" line-art, "dark" rim-lit silhouette, "mask"
    head_fill: tuple = (0.075, 0.090, 0.135)   # interior tone of the head
    band: tuple | None = None       # headband / accent stripe
    weapon: str | None = None


# ------------------------------------------------------------------ pose bank
def P(**kw) -> Pose:
    base = {
        "idle": dict(px=0, py=0, spine=4, neck=180, head=180,
                     arm_f=(6, 14), arm_b=(-6, -12),
                     leg_f=(9, 3, 88), leg_b=(-9, -4, 92)),
        "guard": dict(px=0, py=-4, spine=14, neck=172, head=172,
                      arm_f=(52, 96), arm_b=(30, 84),
                      leg_f=(26, -14, 84), leg_b=(-22, -6, 96)),
        "crouch": dict(px=0, py=26, spine=26, neck=158, head=158,
                       arm_f=(24, 60), arm_b=(-4, 40),
                       leg_f=(40, -58, 88), leg_b=(-30, -46, 92)),
        "run": dict(px=0, py=-6, spine=22, neck=166, head=166,
                    arm_f=(58, 108), arm_b=(-52, -96),
                    leg_f=(38, -24, 82), leg_b=(-34, -12, 96)),
        "run2": dict(px=0, py=-2, spine=20, neck=168, head=168,
                     arm_f=(-46, -92), arm_b=(54, 104),
                     leg_f=(-32, -10, 96), leg_b=(40, -26, 80)),
        "punch_wind": dict(px=0, py=0, spine=-10, neck=190, head=190,
                           arm_f=(-46, -70), arm_b=(46, 84),
                           leg_f=(20, -10, 84), leg_b=(-24, -8, 96)),
        "punch": dict(px=0, py=-2, spine=24, neck=160, head=160,
                      arm_f=(92, 88), arm_b=(-34, -62),
                      leg_f=(34, -6, 86), leg_b=(-28, -4, 94)),
        "kick_wind": dict(px=0, py=6, spine=14, neck=172, head=172,
                          arm_f=(46, 96), arm_b=(-40, -80),
                          leg_f=(34, -44, 80), leg_b=(-12, -4, 92)),
        "kick": dict(px=0, py=-10, spine=-16, neck=196, head=196,
                     arm_f=(-34, -72), arm_b=(52, 100),
                     leg_f=(98, 86, 84), leg_b=(-6, -2, 92)),
        "jump": dict(px=0, py=-12, spine=10, neck=176, head=176,
                     arm_f=(-24, 30), arm_b=(-42, 20),
                     leg_f=(28, -72, 78), leg_b=(-16, -66, 88)),
        "air": dict(px=0, py=0, spine=18, neck=170, head=170,
                    arm_f=(66, 100), arm_b=(-48, -84),
                    leg_f=(56, 30, 84), leg_b=(-28, -40, 92)),
        "land": dict(px=0, py=32, spine=32, neck=152, head=152,
                     arm_f=(40, 48), arm_b=(-46, -20),
                     leg_f=(46, -66, 84), leg_b=(-34, -58, 94)),
        "hit": dict(px=0, py=-6, spine=-26, neck=208, head=208,
                    arm_f=(-56, -30), arm_b=(-70, -96),
                    leg_f=(-14, 6, 88), leg_b=(-32, -20, 94)),
        "block": dict(px=0, py=6, spine=10, neck=176, head=176,
                      arm_f=(70, 150), arm_b=(60, 142),
                      leg_f=(24, -22, 86), leg_b=(-24, -14, 94)),
        "draw": dict(px=0, py=-2, spine=8, neck=178, head=178,
                     arm_f=(-14, 34), arm_b=(48, 92),
                     leg_f=(18, -4, 88), leg_b=(-18, -6, 92)),
        "slash": dict(px=0, py=0, spine=22, neck=164, head=164,
                      arm_f=(72, 54), arm_b=(-52, -88),
                      leg_f=(38, -10, 86), leg_b=(-30, -6, 94)),
        "slash_high": dict(px=0, py=-8, spine=-14, neck=192, head=192,
                           arm_f=(126, 150), arm_b=(-70, -110),
                           leg_f=(26, -16, 84), leg_b=(-26, -10, 94)),
        "point": dict(px=0, py=0, spine=6, neck=178, head=178,
                      arm_f=(88, 88), arm_b=(-10, -16),
                      leg_f=(12, 0, 88), leg_b=(-12, -2, 92)),
        "stand_tall": dict(px=0, py=-2, spine=0, neck=180, head=180,
                           arm_f=(4, 6), arm_b=(-4, -6),
                           leg_f=(5, 0, 90), leg_b=(-5, 0, 90)),
        "kneel": dict(px=0, py=34, spine=30, neck=150, head=150,
                      arm_f=(30, 76), arm_b=(6, 40),
                      leg_f=(64, -96, 84), leg_b=(-22, -88, 90)),
        "fly_back": dict(px=0, py=-26, spine=-36, neck=214, head=214,
                         arm_f=(-84, -60), arm_b=(-96, -70),
                         leg_f=(-32, 24, 84), leg_b=(-8, 44, 90)),
    }
    base.update(kw)
    return base


class _PoseBank(dict):
    def __init__(self, raw):
        super().__init__({k: Pose(**v) for k, v in raw.items()})

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e


def P() -> dict:
    """Authored pose bank.

    Angles: 0 = straight down, +90 = forward, 180 = straight up, -90 = back.
    """
    return {
        # --- neutral -------------------------------------------------------
        "idle": dict(px=0, py=0, spine=178, neck=180, head=180,
                     arm_f=(5, 11), arm_b=(-6, -14),
                     leg_f=(7, 2, 86), leg_b=(-7, -2, 92)),
        "stand_tall": dict(px=0, py=0, spine=179, neck=180, head=180,
                           arm_f=(3, 5), arm_b=(-4, -7),
                           leg_f=(5, 0, 90), leg_b=(-5, 0, 90)),
        "breath": dict(px=0, py=-2, spine=177, neck=181, head=181,
                       arm_f=(4, 9), arm_b=(-7, -16),
                       leg_f=(8, 3, 86), leg_b=(-8, -3, 92)),
        "point": dict(px=0, py=0, spine=182, neck=179, head=179,
                      arm_f=(92, 91), arm_b=(-8, -14),
                      leg_f=(12, 1, 88), leg_b=(-12, -2, 92)),
        "cross_arms": dict(px=0, py=0, spine=182, neck=180, head=180,
                           arm_f=(48, 150), arm_b=(40, 142),
                           leg_f=(10, 2, 88), leg_b=(-10, -2, 92)),
        # --- combat --------------------------------------------------------
        "guard": dict(px=0, py=-3, spine=191, neck=176, head=176,
                      arm_f=(56, 102), arm_b=(34, 90),
                      leg_f=(27, -13, 84), leg_b=(-24, -7, 96)),
        "guard_low": dict(px=0, py=6, spine=194, neck=172, head=172,
                          arm_f=(44, 80), arm_b=(24, 66),
                          leg_f=(32, -26, 84), leg_b=(-30, -18, 96)),
        "crouch": dict(px=0, py=24, spine=168, neck=176, head=176,
                       arm_f=(34, 74), arm_b=(4, 44),
                       leg_f=(46, -58, 88), leg_b=(-36, -46, 92)),
        "dash": dict(px=0, py=-4, spine=206, neck=158, head=158,
                     arm_f=(-58, -104), arm_b=(62, 112),
                     leg_f=(-40, -14, 96), leg_b=(46, -34, 80)),
        "run": dict(px=0, py=-6, spine=202, neck=160, head=160,
                    arm_f=(62, 112), arm_b=(-52, -98),
                    leg_f=(40, -22, 82), leg_b=(-36, -12, 96)),
        "run2": dict(px=0, py=-2, spine=198, neck=164, head=164,
                     arm_f=(-48, -94), arm_b=(56, 106),
                     leg_f=(-34, -10, 96), leg_b=(42, -26, 80)),
        "punch_wind": dict(px=0, py=0, spine=160, neck=196, head=196,
                           arm_f=(-44, -74), arm_b=(48, 88),
                           leg_f=(22, -8, 84), leg_b=(-28, -10, 96)),
        "punch": dict(px=0, py=-2, spine=203, neck=158, head=158,
                      arm_f=(94, 92), arm_b=(-32, -64),
                      leg_f=(36, -6, 86), leg_b=(-30, -4, 94)),
        "punch_up": dict(px=0, py=-8, spine=190, neck=172, head=172,
                         arm_f=(146, 150), arm_b=(-26, -54),
                         leg_f=(24, -4, 86), leg_b=(-22, -4, 94)),
        "kick_wind": dict(px=0, py=4, spine=186, neck=176, head=176,
                          arm_f=(48, 96), arm_b=(-42, -82),
                          leg_f=(58, -56, 80), leg_b=(-14, -4, 92)),
        "kick": dict(px=0, py=-8, spine=158, neck=198, head=198,
                     arm_f=(-36, -74), arm_b=(54, 102),
                     leg_f=(102, 96, 84), leg_b=(-8, -2, 92)),
        "jump": dict(px=0, py=-10, spine=190, neck=178, head=178,
                     arm_f=(-26, 26), arm_b=(-44, 16),
                     leg_f=(32, -84, 78), leg_b=(-20, -74, 88)),
        "air": dict(px=0, py=0, spine=196, neck=168, head=168,
                    arm_f=(68, 104), arm_b=(-50, -86),
                    leg_f=(58, 26, 84), leg_b=(-30, -44, 92)),
        "air_spin": dict(px=0, py=0, spine=140, neck=220, head=220,
                         arm_f=(-60, -20), arm_b=(-90, -60),
                         leg_f=(70, 40, 80), leg_b=(20, 60, 90)),
        "land": dict(px=0, py=30, spine=162, neck=178, head=178,
                     arm_f=(44, 52), arm_b=(-48, -22),
                     leg_f=(48, -68, 84), leg_b=(-38, -60, 94)),
        "hit": dict(px=0, py=-4, spine=148, neck=206, head=206,
                    arm_f=(-58, -34), arm_b=(-72, -98),
                    leg_f=(-10, 10, 88), leg_b=(-30, -18, 94)),
        "hit_hard": dict(px=0, py=-18, spine=132, neck=214, head=214,
                         arm_f=(-80, -50), arm_b=(-96, -120),
                         leg_f=(-24, 26, 84), leg_b=(-40, 6, 92)),
        "fly_back": dict(px=0, py=-24, spine=138, neck=214, head=214,
                         arm_f=(-86, -60), arm_b=(-98, -74),
                         leg_f=(-30, 26, 84), leg_b=(-6, 46, 90)),
        "block": dict(px=0, py=6, spine=186, neck=176, head=176,
                      arm_f=(78, 158), arm_b=(68, 148),
                      leg_f=(24, -22, 86), leg_b=(-26, -16, 94)),
        "kneel": dict(px=0, py=32, spine=174, neck=170, head=170,
                      arm_f=(32, 78), arm_b=(6, 42),
                      leg_f=(66, -98, 84), leg_b=(-22, -92, 90)),
        "kneel_hurt": dict(px=0, py=38, spine=150, neck=196, head=196,
                           arm_f=(20, 60), arm_b=(-30, 20),
                           leg_f=(70, -104, 84), leg_b=(-26, -100, 90)),
        "draw": dict(px=0, py=0, spine=184, neck=178, head=178,
                     arm_f=(-16, 32), arm_b=(50, 94),
                     leg_f=(18, -2, 88), leg_b=(-18, -4, 92)),
        "slash": dict(px=0, py=0, spine=202, neck=162, head=162,
                      arm_f=(78, 56), arm_b=(-54, -90),
                      leg_f=(40, -10, 86), leg_b=(-32, -6, 94)),
        "slash_high": dict(px=0, py=-8, spine=156, neck=194, head=194,
                           arm_f=(128, 154), arm_b=(-72, -112),
                           leg_f=(26, -16, 84), leg_b=(-26, -10, 94)),
        "sheathe": dict(px=0, py=-2, spine=182, neck=180, head=180,
                        arm_f=(24, 62), arm_b=(38, 84),
                        leg_f=(14, 0, 88), leg_b=(-14, -2, 92)),
        # --- chapter one: training ------------------------------------------
        "stance": dict(px=0, py=10, spine=192, neck=172, head=172,
                       arm_f=(52, 96), arm_b=(30, 74),
                       leg_f=(34, -26, 84), leg_b=(-34, -22, 96)),
        "staff_guard": dict(px=0, py=4, spine=189, neck=176, head=176,
                            arm_f=(76, 104), arm_b=(44, 76),
                            leg_f=(28, -18, 84), leg_b=(-28, -16, 96)),
        "staff_wind": dict(px=0, py=2, spine=176, neck=188, head=188,
                           arm_f=(132, 168), arm_b=(96, 148),
                           leg_f=(24, -12, 84), leg_b=(-26, -14, 96)),
        "staff_swing": dict(px=0, py=6, spine=200, neck=164, head=164,
                            arm_f=(96, 62), arm_b=(58, 34),
                            leg_f=(36, -20, 84), leg_b=(-30, -14, 96)),
        "staff_follow": dict(px=0, py=14, spine=206, neck=156, head=156,
                             arm_f=(70, 26), arm_b=(36, 2),
                             leg_f=(40, -30, 84), leg_b=(-34, -20, 96)),
        "bow": dict(px=0, py=2, spine=136, neck=184, head=184,
                    arm_f=(16, 26), arm_b=(-14, -6),
                    leg_f=(6, 0, 88), leg_b=(-6, -1, 92)),
        "bow_wait": dict(px=0, py=6, spine=142, neck=186, head=186,
                         arm_f=(24, 44), arm_b=(-8, 4),
                         leg_f=(10, 2, 88), leg_b=(-10, -2, 92)),
        "palm_stop": dict(px=0, py=0, spine=186, neck=178, head=178,
                          arm_f=(94, 96), arm_b=(20, 52),
                          leg_f=(18, -4, 88), leg_b=(-18, -6, 92)),
        "sit_seiza": dict(px=0, py=40, spine=178, neck=182, head=182,
                          arm_f=(28, 70), arm_b=(20, 62),
                          leg_f=(78, -104, 88), leg_b=(64, -96, 92)),
        "reach_up": dict(px=0, py=-4, spine=186, neck=176, head=176,
                         arm_f=(96, 148), arm_b=(84, 132),
                         leg_f=(16, -2, 88), leg_b=(-16, -4, 92)),
        "tired": dict(px=0, py=10, spine=166, neck=186, head=186,
                      arm_f=(28, 60), arm_b=(-18, 22),
                      leg_f=(18, -10, 88), leg_b=(-20, -12, 92)),
    }


POSES = _PoseBank(P())


# ------------------------------------------------------------- pose keyframes
@dataclass
class PoseKey:
    t: float
    pose: Pose
    ease: str = "smooth"


class PoseTrack:
    """Keyed body animation with per-segment easing + optional overshoot."""

    def __init__(self, pose: Pose | None = None):
        self.keys: list[PoseKey] = [PoseKey(0.0, pose or POSES["idle"])]

    def add(self, t: float, pose: Pose | str, ease_name: str = "smooth") -> "PoseTrack":
        if isinstance(pose, str):
            pose = POSES[pose]
        if self.keys and abs(self.keys[-1].t - t) < 1e-9:
            self.keys[-1] = PoseKey(t, pose, ease_name)
            return self
        self.keys.append(PoseKey(t, pose, ease_name))
        self.keys.sort(key=lambda k: k.t)
        return self

    def hold(self, t: float) -> "PoseTrack":
        return self.add(t, self.keys[-1].pose, "smooth")

    def at(self, t: float) -> Pose:
        ks = self.keys
        if t <= ks[0].t:
            return ks[0].pose
        if t >= ks[-1].t:
            return ks[-1].pose
        lo, hi = 0, len(ks) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if ks[mid].t <= t:
                lo = mid
            else:
                hi = mid
        a, b = ks[lo], ks[hi]
        u = ease(b.ease, (t - a.t) / max(b.t - a.t, 1e-9))
        p = a.pose.lerp(b.pose, u)
        # stylised spacing: hold near the end of fast moves (anime "snap & settle")
        return p


# --------------------------------------------------------------------- drawing
def _perp(a, b, k):
    """Unit perpendicular of segment a->b, scaled by k."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1e-6
    return (-dy / L * k, dx / L * k)


def _side(a, b, light):
    """Sign that puts the perpendicular offset on the light side of the segment."""
    px, py = _perp(a, b, 1.0)
    return 1.0 if (px * light[0] + py * light[1]) >= 0 else -1.0


def capsule(p, a, b, w0, w1, color, alpha=1.0, depth=1.0, glow=0.0, glow_color=None, additive=False):
    p.line([a, b], w0 * 2, color, alpha=alpha, depth=depth, glow=glow, glow_color=glow_color,
           taper=w1 / max(w0, 1e-6), additive=additive)
    k = p.cam.scale(p.st, depth)
    if w0 * k > 1.0:
        p.circle(a, w0, color, alpha=alpha, depth=depth, additive=additive)
    if w1 * k > 1.0:
        p.circle(b, w1, color, alpha=alpha, depth=depth, additive=additive)


def draw_character(p: "Painter", sk: Skeleton, rig: Rig, look: Look, depth: float = 1.0,
                   alpha: float = 1.0, aura: float = 0.0, light: tuple[float, float] = (0.35, -1.0),
                   shade: float = 1.0, eye_glow: float = 0.0, dark_line: bool = True,
                   rim_on: bool = True):
    """Paint a solved skeleton with the film's line-art + rim-light model.

    Pass 1 dark outline (separation), pass 2 body, pass 3 rim light, pass 4 head
    and eye.  Lighting comes from ``light`` (world direction to the light).
    """
    w = look.w_scale * sk.scale
    base = np.asarray(look.color, np.float32)
    ink = np.asarray(look.ink, np.float32)
    rimc = np.asarray(look.rim, np.float32)
    far = base * 0.72 + ink * 0.28

    f_arm = (sk.shoulder, sk.elbow_f, sk.hand_f)
    b_arm = (sk.shoulder, sk.elbow_b, sk.hand_b)
    f_leg = (sk.hip, sk.knee_f, sk.foot_f)
    b_leg = (sk.hip, sk.knee_b, sk.foot_b)
    torso = [(sk.pelvis, sk.chest), (sk.chest, sk.neck)]

    def stroke_all(color, width_mul, a=1.0, glowk=0.0):
        for seg, ww in (((b_arm[0], b_arm[1]), rig.w_arm), ((b_arm[1], b_arm[2]), rig.w_fore),
                        ((b_leg[0], b_leg[1]), rig.w_leg), ((b_leg[1], b_leg[2]), rig.w_shin)):
            capsule(p, seg[0], seg[1], ww * 0.62 * w * width_mul, ww * 0.56 * w * width_mul,
                    color, a, depth, glow=glowk, glow_color=tuple(rimc))
        p.line([sk.foot_b, sk.to_b], rig.w_shin * 0.5 * w * 2 * width_mul, color, a, depth,
               taper=0.55, glow=glowk, glow_color=tuple(rimc))
        for seg, ww in (torso[0], torso[1]), :
            pass
        capsule(p, sk.pelvis, sk.chest, rig.w_spine * 0.58 * w * width_mul, rig.w_spine * 0.5 * w * width_mul,
                color, a, depth, glow=glowk, glow_color=tuple(rimc))
        capsule(p, sk.chest, sk.neck, rig.w_spine * 0.48 * w * width_mul, rig.w_spine * 0.36 * w * width_mul,
                color, a, depth, glow=glowk, glow_color=tuple(rimc))
        for seg, ww in (((f_leg[0], f_leg[1]), rig.w_leg), ((f_leg[1], f_leg[2]), rig.w_shin)):
            capsule(p, seg[0], seg[1], ww * 0.62 * w * width_mul, ww * 0.56 * w * width_mul,
                    color, a, depth, glow=glowk, glow_color=tuple(rimc))
        p.line([sk.foot_f, sk.to_f], rig.w_shin * 0.5 * w * 2 * width_mul, color, a, depth,
               taper=0.55, glow=glowk, glow_color=tuple(rimc))
        for seg, ww in (((f_arm[0], f_arm[1]), rig.w_arm), ((f_arm[1], f_arm[2]), rig.w_fore)):
            capsule(p, seg[0], seg[1], ww * 0.62 * w * width_mul, ww * 0.56 * w * width_mul,
                    color, a, depth, glow=glowk, glow_color=tuple(rimc))

    # 0. aura bloom behind everything ---------------------------------------
    if aura > 0:
        g = tuple(np.asarray(look.aura, np.float32))
        p.circle(sk.head_c, sk.head_r * 1.6, g, alpha=0.0, depth=depth, glow=aura * 0.30 * look.glow, glow_color=g)
        p.circle(sk.chest, rig.spine * 0.75 * w, g, alpha=0.0, depth=depth, glow=aura * 0.22 * look.glow, glow_color=g)

    # 1. outline pass -------------------------------------------------------
    if dark_line:
        stroke_all(tuple(ink), 1.55, alpha, glowk=0.0)

    # 2. body pass ----------------------------------------------------------
    stroke_all(tuple(base), 1.0, alpha)

    # torso fill reads as a chest/shoulder block
    k = p.cam.scale(p.st, depth)
    if sk.scale * k > 0.35:
        sw = rig.shoulder_w * w * 0.5
        hw = rig.hip_w * w * 0.5
        quad = [(sk.shoulder[0] - sw, sk.shoulder[1] + 2 * w), (sk.shoulder[0] + sw, sk.shoulder[1] + 2 * w),
                (sk.hip[0] + hw, sk.hip[1]), (sk.hip[0] - hw, sk.hip[1])]
        p.polygon_world(quad, tuple(base), alpha=alpha, depth=depth, blur=1.2 * k)
        if dark_line:
            p.line(quad + [quad[0]], 3.0 * w, tuple(ink), alpha * 0.55, depth=depth, closed=False)

    # back limbs get a cooler, darker read
    # 3. head ---------------------------------------------------------------
    hr = sk.head_r
    if look.head_style == "light":
        p.circle(sk.head_c, hr, tuple(np.asarray(look.head_fill, np.float32)), alpha=alpha, depth=depth)
        p.circle(sk.head_c, hr, tuple(base), alpha=alpha, depth=depth, ring=2.8 * w)
    elif look.head_style == "mask":
        p.circle(sk.head_c, hr, tuple(base), alpha=alpha, depth=depth)
        p.circle(sk.head_c, hr * 0.72, tuple(ink), alpha=alpha * 0.9, depth=depth)
    else:  # dark, rim-lit silhouette
        p.circle(sk.head_c, hr, tuple(ink), alpha=alpha, depth=depth)
        p.circle(sk.head_c, hr * 0.80, tuple(np.asarray(ink) * 0.4 + np.asarray(look.rim) * 0.06),
                 alpha=alpha, depth=depth)

    # anime profile mark: a dark cheek line on the facing side
    f = sk.facing
    cx, cy = sk.head_c
    if dark_line and hr * k > 14:
        p.arc((cx, cy), hr * 0.92, (-0.55 if f > 0 else math.pi - 0.55), (0.55 if f > 0 else math.pi + 0.55),
              hr * 0.16, tuple(ink), alpha=alpha * 0.5, depth=depth, world=True)

    # 4. rim light ----------------------------------------------------------
    if rim_on and look.rim_amount > 0 and alpha > 0.35:
        r = look.rim_amount
        for (a, b), ww in (((f_arm[0], f_arm[1]), rig.w_arm), ((f_arm[1], f_arm[2]), rig.w_fore),
                           ((f_leg[0], f_leg[1]), rig.w_leg), ((f_leg[1], f_leg[2]), rig.w_shin),
                           ((b_arm[0], b_arm[1]), rig.w_arm * 0.8), ((b_leg[0], b_leg[1]), rig.w_leg * 0.8),
                           ((sk.pelvis, sk.chest), rig.w_spine), ((sk.chest, sk.neck), rig.w_spine * 0.85)):
            sg = _side(a, b, light)
            px, py = _perp(a, b, sg * ww * 0.21 * w)
            p.line([(a[0] + px, a[1] + py), (b[0] + px, b[1] + py)], ww * 0.21 * w * 2,
                   tuple(rimc), alpha * clamp(r), depth=depth, glow=r * 0.10 * look.glow, glow_color=tuple(rimc))
        # head rim: thin arc sitting on the lit edge of the skull
        ang = math.atan2(light[1], light[0])
        p.arc(sk.head_c, hr * 1.02, ang - 1.0, ang + 1.0, hr * 0.085,
              tuple(rimc), alpha=alpha * clamp(r), depth=depth, glow=r * 0.22 * look.glow,
              glow_color=tuple(rimc), world=True)

    # 5. eye -----------------------------------------------------------------
    if eye_glow > 0:
        ex = cx + f * hr * 0.46
        ey = cy - hr * 0.03
        L = hr * 0.30 * (0.8 + 0.2 * clamp(eye_glow))
        p.line([(ex - f * L, ey + hr * 0.03), (ex + f * L, ey - hr * 0.03)],
               hr * 0.13, tuple(look.eye), alpha=alpha * clamp(eye_glow), depth=depth,
               glow=eye_glow * 1.5 * look.glow, glow_color=look.eye, additive=True, taper=0.55)
        # second, fainter line above = the "glare" of an anime eye
        p.line([(ex - f * L * 0.7, ey - hr * 0.13), (ex + f * L * 0.7, ey - hr * 0.15)],
               hr * 0.05, tuple(look.eye), alpha=alpha * 0.55 * clamp(eye_glow), depth=depth,
               glow=eye_glow * 0.6 * look.glow, glow_color=look.eye, additive=True)

def draw_smear(p: "Painter", poses: Sequence[Pose], rig: Rig, look: Look, joint: str,
               depth: float = 1.0, alpha: float = 0.55, width: float = 1.0):
    """Swept-arc smear for a fast limb/hand — the classic anime motion streak."""
    pts = []
    for pose in poses:
        sk = solve(pose, rig)
        pts.append(getattr(sk, joint))
    if len(pts) < 2:
        return
    n = len(pts)
    cols = []
    for i in range(n):
        f = i / max(n - 1, 1)
        c = np.asarray(look.trail, np.float32) * (1.0 - f) + np.asarray(look.color, np.float32) * f
        cols.append(tuple(c))
    widths = [look.w_scale * rig.w_fore * width * (0.5 + 0.5 * (i / max(n - 1, 1))) for i in range(n)]
    p.ribbon(pts, widths, cols, alpha=alpha, depth=depth, glow=0.35)


def draw_afterimage(p: "Painter", pose: Pose, rig: Rig, look: Look, alpha: float, depth: float = 1.0,
                    color: tuple | None = None):
    sk = solve(pose, rig)
    c = color or look.trail
    for a, b, wd in ((sk.shoulder, sk.elbow_f, rig.w_arm), (sk.elbow_f, sk.hand_f, rig.w_fore),
                     (sk.hip, sk.knee_f, rig.w_leg), (sk.knee_f, sk.foot_f, rig.w_shin),
                     (sk.pelvis, sk.chest, rig.w_spine)):
        p.line([a, b], wd * 2, c, alpha=alpha, depth=depth, glow=0.25, additive=False)
    p.circle(sk.head_c, sk.head_r, c, alpha=alpha, depth=depth, ring=rig.w_spine * 0.4)


# --------------------------------------------------------------------- props
def staff_line(sk: Skeleton, angle_deg: float, length: float = 210.0, grip: float = 0.34):
    """End points of a staff/bokken held in the front hand at an absolute angle."""
    h = sk.hand_f
    dx, dy = dirv(angle_deg)
    a = (h[0] - dx * length * grip, h[1] - dy * length * grip)
    b = (h[0] + dx * length * (1 - grip), h[1] + dy * length * (1 - grip))
    return a, b


def draw_staff(p: "Painter", sk: Skeleton, look: Look, angle: float, length: float = 210.0,
               depth: float = 1.0, alpha: float = 1.0, blade: bool = False, glow: float = 0.0):
    """A wooden practice staff (or a blade when ``blade`` is set)."""
    a, b = staff_line(sk, angle, length)
    w = 7.0 * sk.scale * look.w_scale
    if blade:
        col = np.asarray((0.86, 0.92, 1.0), np.float32)
        p.line([a, b], w * 1.5, tuple(np.asarray(look.ink, np.float32)), alpha=alpha, depth=depth,
               taper=0.35)
        p.line([a, b], w * 0.95, tuple(col), alpha=alpha, depth=depth, taper=0.12,
               glow=glow, glow_color=(0.6, 0.85, 1.0))
    else:
        wood = np.asarray((0.44, 0.30, 0.19), np.float32)
        p.line([a, b], w * 1.9, tuple(np.asarray(look.ink, np.float32)), alpha=alpha, depth=depth,
               taper=0.85)
        p.line([a, b], w * 1.25, tuple(wood), alpha=alpha, depth=depth, taper=0.85)
        # highlight along the top edge
        p.line([a, b], w * 0.30, tuple(wood * 1.9 + 0.06), alpha=alpha * 0.8, depth=depth,
               taper=0.85)
    p.circle(sk.hand_f, w * 0.85, tuple(np.asarray(look.ink, np.float32)), alpha=alpha, depth=depth)
    p.circle(sk.hand_f, w * 0.58, tuple(np.asarray(look.color, np.float32)), alpha=alpha, depth=depth)


def draw_sash(p: "Painter", sk: Skeleton, look: Look, color=(0.55, 0.16, 0.12), depth=1.0,
              alpha=1.0, w: float = 1.0):
    """A belt across the hips, plus two hanging tails — reads as a robe at distance."""
    hip = sk.hip
    che = sk.chest
    dx, dy = che[0] - hip[0], che[1] - hip[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L, dx / L
    hw = 17.0 * sk.scale * w
    p.line([(hip[0] - nx * hw, hip[1] - ny * hw), (hip[0] + nx * hw, hip[1] + ny * hw)],
           13.0 * sk.scale * w, color, alpha=alpha, depth=depth, taper=0.95)
    # a knot and two hanging tails (reads as a robe at distance)
    for s in (-1, 1):
        p.line([(hip[0] + nx * hw * 0.35 * s, hip[1] + ny * hw * 0.35 * s + 4),
                (hip[0] + nx * hw * 0.5 * s - sk.facing * 13, hip[1] + 46 * sk.scale)],
               5.0 * sk.scale * w, color, alpha=alpha * 0.92, depth=depth, taper=0.35)
