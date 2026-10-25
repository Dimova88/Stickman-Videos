"""Biomechanics: the reason a body does not move like a marionette.

The old renderer moved **every** joint of a fighter between frame A and frame B
at the same instant. That is not how a limb works. A punch is a wave: the pelvis
starts, the spine follows a frame later, the shoulder a frame after that, the
elbow after that, and the fist arrives last, slightly overshooting. Each link is
driven by the one before it through muscle and tendon, and every link has mass,
so it lags.

This module adds that lag **after** the choreography has been authored, so the
beat sheet keeps describing intent ("he swings from the hip") and the rig is
what turns intent into weight:

===================  ==========================================================
``whip_lag``         per-joint delay along the chain: pelvis 0 frames, spine 1,
                     shoulder 2, elbow and fist 3, with a small angular
                     overshoot so the tip does not stop dead
``squash_stretch``   vertical give on landing and take-off, with the horizontal
                     widening that conserves mass
``localized_hit``    the body reacts to *where* it was hit — a head shot snaps
                     the neck, a gut shot folds the spine into a C, a sweep
                     takes the feet out from under him
===================  ==========================================================
"""
from __future__ import annotations

import math

FRAME = 1.0 / 24.0

#: index map into ``Pose.angles`` (the 10 segment angles, in solve order)
SEG_TORSO, SEG_HEAD = 0, 1
SEG_FAR_UP, SEG_FAR_FORE = 2, 3
SEG_NEAR_UP, SEG_NEAR_FORE = 4, 5
SEG_LEG_L, SEG_LEG_R = (6, 7), (8, 9)

#: how many frames behind the pelvis each link is
#: Each link is delayed as a *unit* with the link before it inside the same
#: chain. The elbow is a hinge: give the forearm its own delay and it inverts,
#: because the two angles are absolute and one frame apart is enough to fold the
#: arm the wrong way round. A real arm lags at the shoulder and the elbow follows
#: the upper arm, not the clock.
LAG = {
    SEG_TORSO: 1,
    SEG_HEAD: 1,
    SEG_FAR_UP: 2,
    SEG_NEAR_UP: 2,
    SEG_FAR_FORE: 2,
    SEG_NEAR_FORE: 2,
    SEG_LEG_L[0]: 0, SEG_LEG_L[1]: 0,
    SEG_LEG_R[0]: 0, SEG_LEG_R[1]: 0,
}

#: the tip of the chain overshoots the pose it was heading for by this fraction
#: of the frame-to-frame change: a wrist does not stop where the arm stops
OVERSHOOT = 0.12

#: below this root speed (design px per frame) the lag is switched off: a man
#: standing still has no inertia to show, and delaying a held guard pose only
#: makes the guard look broken
IDLE_SPEED = 2.0
FULL_SPEED = 26.0

#: angular blend ceiling: even at full speed the chain keeps most of the
#: authored pose, because a pose that is 100 % lagged is a pose nobody drew
MAX_BLEND = 0.45


def _lerp_angle(a: float, b: float, u: float) -> float:
    """Blend two angles the short way around the circle."""
    d = (b - a + math.pi) % (2.0 * math.pi) - math.pi
    return a + d * u


def blend_strength(speed_px_per_frame: float) -> float:
    """How much of the lag to apply at this speed, 0 to :data:`MAX_BLEND`."""
    if speed_px_per_frame <= IDLE_SPEED:
        return 0.0
    u = (speed_px_per_frame - IDLE_SPEED) / max(1e-6, FULL_SPEED - IDLE_SPEED)
    u = min(1.0, u)
    # ease in: the first few pixels of movement are not a whip, they are a step
    return MAX_BLEND * (u * u * (3.0 - 2.0 * u))


def whip_angles(now, older: dict[int, tuple[float, ...]], k: float) -> list[float]:
    """Mix the current angles with the ones each joint *should* be lagging.

    ``older`` maps lag-in-frames to the angle tuple from that many frames back.
    Joints whose lag is 0 keep the current angle exactly — a pelvis is not
    dragged behind itself.
    """
    out = list(now)
    if k <= 0.0:
        return out
    for idx, lag in LAG.items():
        if lag <= 0:
            continue
        src = older.get(lag)
        if src is None or idx >= len(src):
            continue
        ahead = older.get(max(0, lag - 1), src)
        # the joint is heading from where it was (src) to where it is (now);
        # lagging means "still nearer src", and the overshoot pushes the far end
        # of the chain past the pose so a blade does not stop dead in the air
        tip = idx in (SEG_HEAD,)
        target = (_lerp_angle(src[idx], now[idx], 1.0 + OVERSHOOT) if tip
                  else src[idx])
        out[idx] = _lerp_angle(now[idx], target, k)
    return out


def contact_taper(t: float, hit_times, window: float = 0.09) -> float:
    """Pull the lag out around the instant a blow lands.

    The lag exists so the *travel* looks like a body with mass. At the contact
    frame the chain has arrived — that is what contact means — so the pose has
    to be the authored one, or the spark burst hangs in the air beside a fist
    that never got there.
    """
    for h in hit_times or ():
        if abs(t - h) <= window:
            u = abs(t - h) / window
            return u * u
    return 1.0


def squash_stretch(vy: float, k: float = 1.0) -> tuple[float, float]:
    """Vertical give and horizontal spread from vertical velocity.

    ``vy`` is the pelvis velocity in design px per frame (positive = descending).
    Returns ``(spine_scale_y, stance_scale_x)``; landing compresses, take-off
    stretches, and the stance widens to keep the volume.
    """
    s = max(-0.16, min(0.20, vy * 0.010 * k))
    return 1.0 - s, 1.0 + s * 0.55


# --------------------------------------------------------------------- impacts
#: a hit is not one animation, it is an anatomy: the place it landed decides
#: which link of the chain breaks first
HIT_ZONES = ("head", "gut", "sweep", "guard")


def localized_hit(zone: str, impact_dir: int, intensity: float = 1.0) -> dict:
    """The pose deltas of a blow that landed on ``zone``.

    Returned as overrides for :func:`fight.poses.fade`, so a head shot bends the
    neck and lifts the front foot, a gut shot folds him into a C over the blow,
    and a sweep takes both feet out from under him while the torso rotates.
    """
    i = float(intensity)
    if zone == "head":
        return {"head": -26.0 * impact_dir * i, "spine": -13.0 * i,
                "torso": -96.0, "crouch": 10.0, "foot_l": (34.0, 26.0)}
    if zone == "gut":
        return {"spine": 16.0 * i, "torso": -66.0, "crouch": 30.0,
                "head": 14.0 * impact_dir, "foot_l": (16.0, 0.0),
                "foot_r": (-64.0, 0.0)}
    if zone == "sweep":
        return {"torso": -40.0, "spine": -6.0, "crouch": 44.0,
                "foot_l": (58.0, 54.0), "foot_r": (-30.0, 40.0),
                "head": 18.0 * impact_dir}
    return {"spine": -5.0, "torso": -101.0, "crouch": 6.0}
