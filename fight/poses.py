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

from . import rig
from .core import SEG, Pose, solve, _bent

D2R = math.pi / 180.0
ARM_K = 1.24          # limb proportions of the reference stickman
LEG_K = 1.10
HEAD_K = 1.42

L_THIGH = SEG[7][2] * LEG_K
L_SHIN = SEG[8][2] * LEG_K
LEG = L_THIGH + L_SHIN
UPPER_LEN = SEG[3][2] * ARM_K
FORE_LEN = SEG[4][2] * ARM_K
ARM = UPPER_LEN + FORE_LEN
TORSO = SEG[1][2]

#: reach limit — keeps every joint visibly bent
LEG_REACH = 0.94
ARM_REACH = 0.96


def P(torso=-84.0, *, foot_l=(26.0, 0.0), foot_r=(-30.0, 0.0),
      a_up=64.0, a_fore=-14.0, b_up=74.0, b_fore=6.0, head=0.0, crouch=0.0,
      air=0.0, hip=None, spine=0.0, toe_l=0.0, toe_r=0.0,
      grip_a=0.92, grip_b=0.92) -> dict:
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
    ``spine``   how far the back bows off the hip->neck chord (+ = the chest
                opens forward, - = the belly caves in); ``toe_*`` pitches a foot
                that is off the floor; ``grip_*`` is 0 for an open hand and 1 for
                a fist.
    """
    out = dict(torso=torso, foot_l=foot_l, foot_r=foot_r, a_up=a_up, a_fore=a_fore,
               b_up=b_up, b_fore=b_fore, head=head, crouch=crouch, air=air,
               spine=spine, toe_l=toe_l, toe_r=toe_r, grip_a=grip_a, grip_b=grip_b)
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
    out["spine"] = -p.get("spine", 0.0)
    out["toe_l"], out["toe_r"] = p.get("toe_r", 0.0), p.get("toe_l", 0.0)
    out["grip_a"], out["grip_b"] = p.get("grip_b", 0.92), p.get("grip_a", 0.92)
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
    """Clamp a hand to the arm's reach so an arm can never over-extend.

    Aiming the forearm at a nearer point is not enough: on a *straight* arm the
    forearm direction is the same as the upper arm's, so the wrist stays at
    ``UPPER + FORE`` however far the target was pulled in — which is exactly how
    a fully extended arm was passing the "never longer than its bones" audit at
    ratio 1.0000. When the clamp fires the pair is re-solved as a real two-bone
    chain, so the reach is the clamped distance and the elbow has an angle.
    """
    u, f = float(up) * D2R, float(fore) * D2R
    elbow = (math.cos(u) * UPPER_LEN, math.sin(u) * UPPER_LEN)
    hand = (elbow[0] + math.cos(f) * FORE_LEN, elbow[1] + math.sin(f) * FORE_LEN)
    d = math.hypot(*hand)
    if d > ARM * ARM_REACH:
        k = ARM * ARM_REACH / max(d, 1e-6)
        hand = (hand[0] * k, hand[1] * k)
        u, f = _bent((0.0, 0.0), hand, UPPER_LEN, FORE_LEN, "elbow", facing)
    return u, f


def to_pose(p: dict, x: float, ground: float, facing: float = 1.0,
            scale: float = 1.0, widen: float = 1.0) -> Pose:
    """Turn one pose into a drawable Pose.

    The pose is always solved in a canonical right-facing frame (a positive foot
    offset means "in front of the fighter"), and the finished body is then
    reflected once about the hips by ``facing``. Reflecting the solved figure
    instead of the inputs is what keeps a left-facing fighter's arms in front of
    it: mirroring the input angles and *also* negating the resulting angles
    cancelled out, which left blue punching away from its opponent.

    ``facing`` is a *continuous* scale, not a sign: +1 is the authored pose, -1
    is its mirror, and anything in between foreshortens the body through the
    profile (see ``fight/rig.py``). Reflecting after the solve is also what makes
    the knee bend flip with the turn for free — the chain is never solved
    backwards, only drawn from the other side.

    ``widen`` stretches both planted feet apart for a wider stance; the leg
    solver then drops the hips as far as the new stance allows.
    """
    # a fallen fighter cannot hold its hips up, so a pose may pin the hip height
    fl_x = p["foot_l"][0] * (widen if p["foot_l"][1] <= 0.5 else 1.0)
    fr_x = p["foot_r"][0] * (widen if p["foot_r"][1] <= 0.5 else 1.0)
    hh = (p["hip"] if "hip" in p else _hip_height((fl_x, p["foot_l"][1]),
                                                  (fr_x, p["foot_r"][1]))) * scale
    hip_y = ground - hh + p["crouch"] - p.get("air", 0.0)

    # feet, relative to the hip, in the canonical frame (+x = in front)
    fl = (fl_x * scale, hh - p["foot_l"][1] * scale)
    fr = (fr_x * scale, hh - p["foot_r"][1] * scale)
    tl, sl = _leg_ik((0.0, 0.0), fl, 1, LEG_REACH if p["foot_l"][1] <= 0.5 else 0.995)
    tr, sr = _leg_ik((0.0, 0.0), fr, 1, LEG_REACH if p["foot_r"][1] <= 0.5 else 0.995)

    au, af = _arm_angles(p["a_up"], p["a_fore"], 1)
    bu, bf = _arm_angles(p["b_up"], p["b_fore"], 1)

    torso = p["torso"] * D2R
    # the head circle is a segment too: its angle decides where the head sits,
    # so it must follow the spine or the head is drawn in front of the shoulders
    head_ang = torso + p["head"] * D2R
    ang = [torso, head_ang, au, af, bu, bf, tl, sl, tr, sr]

    # one reflection of the solved figure: at -1 this is the old ``pi - angle``,
    # in between it squeezes the horizontal component (a body halfway through a
    # turn is a body seen from the side)
    ang = rig.mirror_angles(ang, facing)
    side = 1.0 if facing >= 0.0 else -1.0
    return Pose(x=x, y=hip_y, facing=float(facing), scale=1.0,
                head_turn=(p["head"] * D2R) * side,
                angles=tuple(ang), arm_k=ARM_K, leg_k=LEG_K, head_k=HEAD_K,
                spine=float(p.get("spine", 0.0)) * scale,
                pitch_a=float(p.get("toe_l", 0.0)) * D2R,
                pitch_b=float(p.get("toe_r", 0.0)) * D2R,
                grip_a=float(p.get("grip_a", 0.92)),
                grip_b=float(p.get("grip_b", 0.92)),
                lift_a=float(p["foot_l"][1]) * scale,
                lift_b=float(p["foot_r"][1]) * scale)


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

# an uppercut ends with the striking arm driven up and forward, not folded
UPPERCUT = P(torso=-86, foot_l=(40, 0), foot_r=(-26, 0),
             a_up=42, a_fore=-96, b_up=-34, b_fore=-26)

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

#: On the floor and staying there. The rigid down state, to the numbers the
#: engine contract asks for: the pelvis a body-thickness above the ground, the
#: shoulders 75 units *behind* it, both feet 80 units in front, and every joint
#: inside its own reach — so the pose cannot splay however long it is held, and
#: two bodies lying next to each other can be spaced from their hip, not their
#: silhouette.
DOWN_HIP = 12.0 / 1.30          # 12 px of ground clearance, in rig units
# The engine contract says "feet 80 px in front of the pelvis", which assumes a
# ~80 px leg. This rig's leg is 142 px (66 + 63, times LEG_K), so a foot only 80
# out leaves the knee no choice but to fold into a 60 px tent. The pose is the
# same idea — pelvis down, legs laid out in front, straight — at this rig's
# proportions: 100 rig units is 96 % of the leg, so the knee has a bend and no
# more, which is what a body on the floor actually looks like.
DOWN_FEET = 108.0
DOWN_SHOULDER = 75.0 / 1.30     # ... and the neck this far behind it

DOWN = P(torso=-176, hip=DOWN_HIP,
         foot_l=(DOWN_FEET, 2.0), foot_r=(DOWN_FEET - 10.0, 7.0),
         a_up=6, a_fore=-4, b_up=20, b_fore=30, head=-4,
         spine=2.0, toe_l=6.0, toe_r=14.0, grip_a=0.12, grip_b=0.12)

# pushing back up off the floor
RECOVER = P(torso=-62, hip=74, foot_l=(-20, 0), foot_r=(-66, 0),
            a_up=52, a_fore=-64, b_up=64, b_fore=-46, head=8)

# ------------------------------------------------------------- the knockdown
# A body that is hit hard does not rotate into a lying pose: it leaves the
# floor, arcs, lands on its back, bounces, skids, and then has to fight its way
# back up. These are the stills of that arc. ``hip`` pins the pelvis, ``air``
# lifts the whole figure off the floor, and every foot is *off* the ground
# (lift > 0) so the foot painter stops snapping the soles to the floor line.
LAUNCH = P(torso=-40, hip=70, foot_l=(-34, 26), foot_r=(-54, 40),
           a_up=10, a_fore=-28, b_up=28, b_fore=-10, head=-18, air=16,
           spine=6.0, grip_a=0.3, grip_b=0.3)

FLIGHT = P(torso=-18, hip=42, foot_l=(-58, 22), foot_r=(-80, 34),
           a_up=-6, a_fore=-16, b_up=18, b_fore=-2, head=-20, air=58,
           spine=9.0, grip_a=0.2, grip_b=0.2)

SLAM = P(torso=-4, hip=15, foot_l=(-92, 2), foot_r=(-116, 7),
         a_up=-16, a_fore=-26, b_up=6, b_fore=22, head=-14, air=0,
         spine=-6.0, toe_l=8.0, toe_r=6.0, grip_a=0.25, grip_b=0.25)

BOUNCE = P(torso=-20, hip=36, foot_l=(-74, 12), foot_r=(-98, 20),
           a_up=-6, a_fore=6, b_up=16, b_fore=34, head=-24, air=15,
           spine=2.0, toe_l=14.0, toe_r=12.0, grip_a=0.2, grip_b=0.2)

#: The sprawl of a body that has just stopped sliding: same rigid state, one
#: knee up and one arm across the ground, so two men on the floor are not the
#: same shape twice.
# The second leg must not fold back across the first: at 64 units out of a
# 142-unit leg the knee has no choice but to make a diamond, and a diamond is
# the shape that reads as "melted". 86 leaves a bend and nothing more, and the
# two legs sit on different lines so the body has depth even flat on its back.
SPRAWL = P(torso=-174, hip=DOWN_HIP,
           foot_l=(DOWN_FEET - 8.0, 2.0), foot_r=(DOWN_FEET - 30.0, 5.0),
           a_up=16, a_fore=-40, b_up=34, b_fore=24, head=-6,
           spine=3.0, toe_l=8.0, toe_r=18.0, grip_a=0.18, grip_b=0.2)

# the body comes back to itself: a roll onto the hip, then hands and knees
ROLL = P(torso=-38, hip=46, foot_l=(-38, 8), foot_r=(-70, 22),
         a_up=42, a_fore=-78, b_up=66, b_fore=-38, head=8,
         spine=-8.0, toe_l=10.0, toe_r=8.0, grip_a=0.4, grip_b=0.4)

ALL_FOURS = P(torso=-46, hip=64, foot_l=(-24, 16), foot_r=(-62, 20),
              a_up=44, a_fore=74, b_up=38, b_fore=66, head=24,
              spine=-10.0, toe_l=10.0, toe_r=12.0, grip_a=0.5, grip_b=0.5)

# the arms give out for a beat: the chest goes back down on the floor
GIVE = P(torso=-30, hip=38, foot_l=(-34, 12), foot_r=(-70, 16),
         a_up=52, a_fore=62, b_up=46, b_fore=54, head=14,
         spine=-4.0, toe_l=8.0, toe_r=10.0, grip_a=0.4, grip_b=0.4)

PUSHUP = P(torso=-58, hip=88, foot_l=(-8, 10), foot_r=(-54, 12),
           a_up=46, a_fore=52, b_up=40, b_fore=44, head=20,
           spine=-12.0, toe_l=6.0, toe_r=8.0, grip_a=0.55, grip_b=0.55)

# halfway up and not steady yet: weight on the front leg, chest still low
STAGGER = P(torso=-68, hip=108, foot_l=(36, 0), foot_r=(-42, 0),
            a_up=78, a_fore=-34, b_up=66, b_fore=-22, head=12, crouch=16,
            spine=-8.0, grip_a=0.5, grip_b=0.5)

# standing again, but spent: hands low, head down, shoulders round
SPENT = P(torso=-70, foot_l=(32, 0), foot_r=(-34, 0),
          a_up=76, a_fore=-46, b_up=68, b_fore=-32, head=10, crouch=10,
          spine=-11.0, grip_a=0.45, grip_b=0.45)


# ---------------------------------------------------------------- curvature
# How each pose carries its weight: the bow of the back (`spine`, rig units at
# mid-back, + = the chest opens forward / - = the body curls), the pitch of a
# foot that leaves the floor (`toe_*`, degrees) and whether a hand is a fist
# (`grip_*`). Authoring these next to the angles is what separates a pose that
# is merely correct from one that is loading, folding or landing.
_TUNE = {
    "IDLE": {}, "GUARD": dict(spine=-3.0), "TIGHT": dict(spine=-5.0),
    "JAB": dict(spine=4.0), "CROSS": dict(spine=6.5), "HOOK": dict(spine=3.0),
    "UPPERCUT": dict(spine=8.5), "BLOCK_HI": dict(spine=-2.0, grip_a=0.8),
    "BLOCK_MID": dict(spine=-3.0, grip_a=0.8), "BLOCK_LO": dict(spine=-4.0, grip_a=0.8),
    "SLIP": dict(spine=-6.0), "DUCK": dict(spine=-9.0),
    "KICK_MID": dict(spine=6.0, toe_r=16.0), "KICK_LOW": dict(spine=4.0, toe_r=10.0),
    "KICK_HI": dict(spine=10.0, toe_r=22.0), "KNEE": dict(spine=-4.0, toe_r=12.0),
    "CLINCH": dict(spine=-6.0), "SHOVE": dict(spine=5.0),
    "HIT_HEAD": dict(spine=11.0, grip_a=0.6, grip_b=0.6),
    "HIT_BODY": dict(spine=-14.0, grip_a=0.5, grip_b=0.5),
    "LANDED": dict(spine=-6.0, grip_a=0.7, grip_b=0.7),
    "AIRBORNE": dict(spine=4.0, toe_l=12.0, toe_r=12.0),
    "ONE_LEG": dict(spine=2.0, toe_r=10.0),
    "TIRED": dict(spine=-9.0, grip_a=0.35, grip_b=0.35),
    "SQUARE": dict(spine=-2.0),
    "KNEEL": dict(spine=-8.0, grip_a=0.3, grip_b=0.3),
    "SLUMP": dict(spine=-13.0, grip_a=0.15, grip_b=0.15),
    "VICTORY": dict(spine=9.0, grip_a=0.05, grip_b=0.05),
    "SWEEP": dict(spine=-8.0, toe_r=8.0),
    "AERIAL_KICK": dict(spine=10.0, toe_l=14.0, toe_r=10.0),
    "FALL": dict(spine=-11.0, grip_a=0.4, grip_b=0.4),
    "DOWN": dict(spine=-4.0, grip_a=0.25, grip_b=0.25),
    "RECOVER": dict(spine=-6.0, grip_a=0.5, grip_b=0.5),
    "LAUNCH": dict(spine=6.0, grip_a=0.3, grip_b=0.3),
    "FLIGHT": dict(spine=9.0, grip_a=0.2, grip_b=0.2),
    "SLAM": dict(spine=-6.0, toe_l=8.0, toe_r=6.0, grip_a=0.25, grip_b=0.25),
    "BOUNCE": dict(spine=2.0, toe_l=14.0, toe_r=12.0, grip_a=0.2, grip_b=0.2),
    "SPRAWL": dict(spine=-3.0, toe_l=6.0, toe_r=4.0, grip_a=0.25, grip_b=0.25),
    "ROLL": dict(spine=-8.0, toe_l=10.0, toe_r=8.0, grip_a=0.4, grip_b=0.4),
    "ALL_FOURS": dict(spine=-10.0, toe_l=6.0, toe_r=8.0, grip_a=0.5, grip_b=0.5),
    "GIVE": dict(spine=-4.0, toe_l=6.0, toe_r=6.0, grip_a=0.4, grip_b=0.4),
    "PUSHUP": dict(spine=-12.0, toe_l=4.0, toe_r=4.0, grip_a=0.55, grip_b=0.55),
    "STAGGER": dict(spine=-8.0, grip_a=0.5, grip_b=0.5),
    "SPENT": dict(spine=-11.0, grip_a=0.45, grip_b=0.45),
}

LIBRARY = {
    "idle": IDLE, "guard": GUARD, "tight": TIGHT, "jab": JAB, "cross": CROSS,
    "hook": HOOK, "upper": UPPERCUT, "block_hi": BLOCK_HI, "block_mid": BLOCK_MID,
    "block_lo": BLOCK_LO, "slip": SLIP, "duck": DUCK, "kick_mid": KICK_MID,
    "kick_low": KICK_LOW, "kick_hi": KICK_HI, "knee": KNEE, "clinch": CLINCH,
    "shove": SHOVE, "hit_head": HIT_HEAD, "hit_body": HIT_BODY, "land": LANDED,
    "air": AIRBORNE, "one_leg": ONE_LEG, "tired": TIRED, "square": SQUARE,
    "kneel": KNEEL, "slump": SLUMP, "victory": VICTORY, "sweep": SWEEP,
    "aerial": AERIAL_KICK, "fall": FALL, "down": DOWN, "recover": RECOVER,
    "launch": LAUNCH, "flight": FLIGHT, "slam": SLAM, "bounce": BOUNCE,
    "sprawl": SPRAWL, "roll": ROLL, "all_fours": ALL_FOURS, "give": GIVE,
    "pushup": PUSHUP, "stagger": STAGGER, "spent": SPENT,
}

# the tuning table mutates the same dicts the library holds, so `PS.GUARD` and
# `LIBRARY["guard"]` can never drift apart
for _name, _kw in _TUNE.items():
    if _kw:
        globals()[_name].update(_kw)
