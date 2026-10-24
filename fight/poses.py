"""The pose library, built so the joints physically cannot look wrong.

Two rules replace the old guesswork:

1. **Legs are solved from where the feet are, and the knee always points
   forward.** A foot is authored as a horizontal offset from the hip; the hip
   height is then the highest position at which *both* feet are still reachable
   with 6 % of slack. That slack is what guarantees a real knee bend (never a
   locked, splayed leg) and makes both knees bend the same, human way.
2. **Arms are authored as absolute angles** (upper arm, then forearm). Folding a
   forearm is a single number, so a guard cannot accidentally clump the hands
   inside the skull.

Angle convention is StykAnimate's: absolute, canvas space, x right / y down, so
0 = right, 90 = down, -90 = up. Poses are authored facing RIGHT; ``mirror()``
reflects them for the other fighter.
"""
from __future__ import annotations

import math

from .core import SEG, Pose, solve

D2R = math.pi / 180.0
L_THIGH = SEG[7][2]
L_SHIN = SEG[8][2]
LEG = L_THIGH + L_SHIN
UPPER_LEN = SEG[3][2]
FORE_LEN = SEG[4][2]
ARM = UPPER_LEN + FORE_LEN
TORSO = SEG[1][2]

#: reach limit — keeps every joint visibly bent
LEG_REACH = 0.94
ARM_REACH = 0.96


def P(torso=-84.0, *, foot_l=(26.0, 0.0), foot_r=(-30.0, 0.0),
      a_up=64.0, a_fore=-14.0, b_up=74.0, b_fore=6.0, head=0.0, crouch=0.0,
      air=0.0, hip=None) -> dict:
    """One pose.

    ``torso``   spine angle (hip -> neck), e.g. -84 is nearly upright, -70 leans in
    ``foot_l``  lead foot as (horizontal offset from the hip, lift above floor);
                lift 0 means planted. A kick is a lifted foot, so the hip height is
                computed only from the planted foot.
    ``a_*``     far arm: upper-arm angle and forearm angle (degrees, absolute)
    ``b_*``     near arm
    ``crouch``  extra hip drop, for ducks and landings
    ``air``     whole-body lift off the floor, for jumps
    ``hip``     pinned hip height above the floor, for a body that has gone down
    """
    out = dict(torso=torso, foot_l=foot_l, foot_r=foot_r, a_up=a_up, a_fore=a_fore,
               b_up=b_up, b_fore=b_fore, head=head, crouch=crouch, air=air)
    if hip is not None:
        out["hip"] = hip
    return out


def fade(p: dict, **kw) -> dict:
    q = dict(p)
    q.update(kw)
    return q


def mirror(p: dict) -> dict:
    """Reflect a facing-right pose (angle -> 180 - angle)."""
    out = dict(p)
    for k in ("torso", "a_up", "a_fore", "b_up", "b_fore"):
        out[k] = 180.0 - p[k]
    out["head"] = -p["head"]
    # the limbs swap sides when mirrored
    out["a_up"], out["b_up"] = 180.0 - p["b_up"], 180.0 - p["a_up"]
    out["a_fore"], out["b_fore"] = 180.0 - p["b_fore"], 180.0 - p["a_fore"]
    out["foot_l"] = (-p["foot_r"][0], p["foot_r"][1])
    out["foot_r"] = (-p["foot_l"][0], p["foot_l"][1])
    return out


# --------------------------------------------------------------------- solver
def _leg_ik(hip, foot, facing: int, reach: float = LEG_REACH):
    """Thigh and shin angles for a foot.

    ``reach`` is how much of the leg's length may be used: planted legs stay at
    0.94 so the knee keeps a visible bend; a kicking leg may extend to 0.995,
    which is what makes a kick read as a kick rather than as a folded leg.
    """
    dx, dy = (foot[0] - hip[0]) * facing, foot[1] - hip[1]
    d = math.hypot(dx, dy)
    d = max(min(d, LEG * reach), abs(L_THIGH - L_SHIN) + 0.5)
    base = math.atan2(dy, dx)
    cos_a = (d * d + L_THIGH ** 2 - L_SHIN ** 2) / (2 * d * L_THIGH)
    a = math.acos(max(-1.0, min(1.0, cos_a)))
    best = None
    for sgn in (1.0, -1.0):
        t1 = base + a * sgn
        knee = (hip[0] + math.cos(t1) * L_THIGH * facing,
                hip[1] + math.sin(t1) * L_THIGH)
        # knee forward = larger x in the facing direction
        score = (knee[0] - hip[0]) * facing
        if best is None or score > best[0]:
            shin = math.atan2(foot[1] - knee[1], (foot[0] - knee[0]) * facing)
            best = (score, t1, shin)
    return best[1], best[2]


def _hip_height(foot_l, foot_r) -> float:
    """Hip height above the floor: as tall as the planted foot allows, with the
    leg kept at LEG_REACH of full extension so the knee is always visibly bent."""
    limit = (LEG * LEG_REACH) ** 2
    out = LEG * LEG_REACH
    for fx, lift in (foot_l, foot_r):
        if lift > 0.5:
            continue                      # an airborne foot does not carry the hips
        out = min(out, math.sqrt(max(limit - fx * fx, (LEG * 0.30) ** 2)))
    return out


def _arm_angles(up: float, fore: float, facing: int):
    """Clamp a hand to the arm's reach so an arm can never over-extend."""
    u, f = float(up) * D2R, float(fore) * D2R
    elbow = (math.cos(u) * UPPER_LEN, math.sin(u) * UPPER_LEN)
    hand = (elbow[0] + math.cos(f) * FORE_LEN, elbow[1] + math.sin(f) * FORE_LEN)
    d = math.hypot(*hand)
    if d > ARM * ARM_REACH:
        k = ARM * ARM_REACH / d
        hand = (hand[0] * k, hand[1] * k)
        # re-fold the forearm to land on the clamped hand
        f = math.atan2(hand[1] - elbow[1], hand[0] - elbow[0])
    return u, f


def to_pose(p: dict, x: float, ground: float, facing: int = 1, scale: float = 1.0) -> Pose:
    q = p if facing > 0 else mirror(p)
    f = 1 if facing > 0 else -1
    # a fallen fighter cannot hold its hips up, so a pose may pin the hip height
    hh = (q["hip"] if "hip" in q else _hip_height(q["foot_l"], q["foot_r"])) * scale
    hip_y = ground - hh + q["crouch"] - q.get("air", 0.0)
    hip = (0.0, 0.0)
    # feet are expressed relative to the hip, in facing space
    fl = (q["foot_l"][0] * scale, hh - q["foot_l"][1] * scale)
    fr = (q["foot_r"][0] * scale, hh - q["foot_r"][1] * scale)
    tl, sl = _leg_ik(hip, fl, f, LEG_REACH if q["foot_l"][1] <= 0.5 else 0.995)
    tr, sr = _leg_ik(hip, fr, f, LEG_REACH if q["foot_r"][1] <= 0.5 else 0.995)
    au, af = _arm_angles(q["a_up"], q["a_fore"], f)
    bu, bf = _arm_angles(q["b_up"], q["b_fore"], f)
    torso = q["torso"] * D2R if facing > 0 else (180.0 - q["torso"]) * D2R
    # the head circle is a segment too: its angle decides where the head sits.
    # It must follow the spine (up the neck), otherwise the head is drawn in
    # front of the shoulders — which is what made every guard look like fists
    # folded into the face.
    head_ang = torso + q["head"] * D2R
    ang = (torso, head_ang, au if facing > 0 else math.pi - au, af if facing > 0 else math.pi - af,
           bu if facing > 0 else math.pi - bu, bf if facing > 0 else math.pi - bf,
           tl if facing > 0 else math.pi - tl, sl if facing > 0 else math.pi - sl,
           tr if facing > 0 else math.pi - tr, sr if facing > 0 else math.pi - sr)
    return Pose(x=x, y=hip_y, facing=facing, scale=1.0,
                head_turn=q["head"] * D2R, angles=tuple(ang))


def feet_of(p: dict):
    return p["foot_l"], p["foot_r"]


def lerp_deg(a: dict, b: dict, u: float) -> dict:
    return {k: a[k] + (b[k] - a[k]) * u for k in a}


# =========================================================== the pose library
# Arm notation: upper arm from the shoulder, forearm from the elbow, absolute.
#   60 / -90  = upper arm down-forward, forearm folded up  -> fist at chin height
#    0 /  -6  = arm straight out to the side the fighter faces -> punch
#   90 /  90  = arm hanging straight down
GUARD = P(torso=-80, foot_l=(32, 0), foot_r=(-30, 0),
          a_up=50, a_fore=-72, b_up=44, b_fore=-60, head=-2)

TIGHT = P(torso=-78, foot_l=(30, 0), foot_r=(-32, 0),
          a_up=56, a_fore=-86, b_up=48, b_fore=-74, head=3)

IDLE = P(torso=-83, foot_l=(24, 0), foot_r=(-30, 0),
         a_up=72, a_fore=-30, b_up=64, b_fore=-18)

JAB = P(torso=-74, foot_l=(44, 0), foot_r=(-26, 0),
        a_up=-4, a_fore=-2, b_up=52, b_fore=-80)

CROSS = P(torso=-70, foot_l=(48, 0), foot_r=(-22, 0),
          a_up=56, a_fore=-78, b_up=4, b_fore=-4)

HOOK = P(torso=-76, foot_l=(38, 0), foot_r=(-26, 0),
         a_up=14, a_fore=-42, b_up=48, b_fore=-70)

UPPERCUT = P(torso=-88, foot_l=(32, 0), foot_r=(-28, 0),
             a_up=44, a_fore=-104, b_up=52, b_fore=-84)

BLOCK_HI = P(torso=-79, foot_l=(28, 0), foot_r=(-30, 0),
             a_up=26, a_fore=-104, b_up=40, b_fore=-118)

BLOCK_MID = P(torso=-80, foot_l=(30, 0), foot_r=(-30, 0),
              a_up=58, a_fore=-96, b_up=54, b_fore=-86)

BLOCK_LO = P(torso=-76, foot_l=(42, 0), foot_r=(-26, 0),
             a_up=76, a_fore=-92, b_up=64, b_fore=-80, crouch=8)

SLIP = P(torso=-96, foot_l=(20, 0), foot_r=(-36, 0),
         a_up=54, a_fore=-80, b_up=46, b_fore=-66)

DUCK = P(torso=-70, foot_l=(36, 0), foot_r=(-34, 0),
         a_up=48, a_fore=-76, b_up=42, b_fore=-64, crouch=22)

# a kick: the rear foot leaves the floor, so give it lift as the second value
KICK_MID = P(torso=-95, foot_l=(20, 0), foot_r=(88, 150),
             a_up=58, a_fore=-62, b_up=72, b_fore=-50, head=6)

KICK_LOW = P(torso=-92, foot_l=(22, 0), foot_r=(104, 52),
             a_up=66, a_fore=-56, b_up=80, b_fore=-44)

KICK_HI = P(torso=-100, foot_l=(18, 0), foot_r=(78, 200),
            a_up=56, a_fore=-60, b_up=68, b_fore=-48, head=8)

KNEE = P(torso=-86, foot_l=(24, 0), foot_r=(62, 62),
         a_up=40, a_fore=-92, b_up=52, b_fore=-80, crouch=-10)

CLINCH = P(torso=-72, foot_l=(36, 0), foot_r=(-28, 0),
           a_up=30, a_fore=-96, b_up=42, b_fore=-104)

SHOVE = P(torso=-64, foot_l=(42, 0), foot_r=(-34, 0),
          a_up=2, a_fore=-8, b_up=16, b_fore=-22)

HIT_HEAD = P(torso=-100, foot_l=(18, 0), foot_r=(-34, 0),
             a_up=74, a_fore=-44, b_up=64, b_fore=-30, head=-12)

HIT_BODY = P(torso=-62, foot_l=(26, 0), foot_r=(-32, 0),
             a_up=60, a_fore=-14, b_up=70, b_fore=-4)

LANDED = P(torso=-74, foot_l=(30, 0), foot_r=(-32, 0),
           a_up=56, a_fore=-64, b_up=48, b_fore=-52, crouch=26)

AIRBORNE = P(torso=-82, foot_l=(30, 58), foot_r=(-18, 72),
             a_up=50, a_fore=-74, b_up=42, b_fore=-62, air=88)

ONE_LEG = P(torso=-86, foot_l=(26, 0), foot_r=(10, 45),
            a_up=56, a_fore=-74, b_up=48, b_fore=-62)

TIRED = P(torso=-64, foot_l=(24, 0), foot_r=(-30, 0),
          a_up=66, a_fore=-52, b_up=58, b_fore=-40, crouch=12)

SQUARE = P(torso=-84, foot_l=(30, 0), foot_r=(-30, 0),
           a_up=48, a_fore=-70, b_up=42, b_fore=-58)

# the finish: dropping to the knees, slumping forward, and standing over it
KNEEL = P(torso=-58, hip=60, foot_l=(62, 0), foot_r=(-64, 8),
          a_up=84, a_fore=-10, b_up=92, b_fore=2, head=16)

SLUMP = P(torso=-36, hip=44, foot_l=(70, 0), foot_r=(-76, 12),
          a_up=96, a_fore=20, b_up=104, b_fore=30, head=34)

VICTORY = P(torso=-92, foot_l=(34, 0), foot_r=(-36, 0),
            a_up=-112, a_fore=-98, b_up=-70, b_fore=-104, head=-16, crouch=-8)


# ---------------------------------------------------------- fight-finish poses
# a sweep: the leg goes out low and long, the body sits behind it
SWEEP = P(torso=-64, foot_l=(24, 0), foot_r=(120, 10),
          a_up=60, a_fore=-58, b_up=90, b_fore=-6, head=12, crouch=34)

# a flying kick: both feet off the floor, the lead leg extended
AERIAL_KICK = P(torso=-92, foot_l=(112, 72), foot_r=(-20, 44),
                a_up=48, a_fore=-58, b_up=20, b_fore=-26, head=4, air=86)

# going down: the knees give, the spine tips back
FALL = P(torso=-52, hip=96, foot_l=(-26, 0), foot_r=(-58, 0),
         a_up=26, a_fore=-62, b_up=38, b_fore=-50, head=-12)

# on the floor: hips low, torso along the ground, arms slack
DOWN = P(torso=-8, hip=34, foot_l=(-100, 0), foot_r=(-122, 0),
         a_up=18, a_fore=-64, b_up=4, b_fore=-38, head=-10)

# pushing back up off the floor
RECOVER = P(torso=-62, hip=74, foot_l=(-20, 0), foot_r=(-66, 0),
            a_up=52, a_fore=-64, b_up=64, b_fore=-46, head=8)


LIBRARY = {
    "idle": IDLE, "guard": GUARD, "tight": TIGHT, "jab": JAB, "cross": CROSS,
    "hook": HOOK, "upper": UPPERCUT, "block_hi": BLOCK_HI, "block_mid": BLOCK_MID,
    "block_lo": BLOCK_LO, "slip": SLIP, "duck": DUCK, "kick_mid": KICK_MID,
    "kick_low": KICK_LOW, "kick_hi": KICK_HI, "knee": KNEE, "clinch": CLINCH,
    "shove": SHOVE, "hit_head": HIT_HEAD, "hit_body": HIT_BODY, "land": LANDED,
    "air": AIRBORNE, "one_leg": ONE_LEG, "tired": TIRED, "square": SQUARE,
    "kneel": KNEEL, "slump": SLUMP, "victory": VICTORY, "sweep": SWEEP,
    "aerial": AERIAL_KICK, "fall": FALL, "down": DOWN, "recover": RECOVER,
}
