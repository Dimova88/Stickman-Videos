"""Motion realism helpers — posing, timing and secondary motion.

The rig is 2-D, so everything that reads as weight has to come from *timing and
overlap*, not from physics simulation:

* poses are blended (``mix``) and sampled along a spline (``PoseTrack``), never
  snapped from one static pose to the next;
* every action has anticipation (a small counter-move before it), an impact
  (fastest frame, widest silhouette) and a settle (overshoot that damps out);
* parts that are not driven by the skeleton — staff tip, sash, hair, hem — lag
  the body by a few frames and overshoot afterwards (``Spring``, ``lag``).

Everything here is deterministic: no random state, so a frame can be rendered
on its own.
"""
from __future__ import annotations

import math

import numpy as np

from .character import Pose, POSES, Rig, solve

# --------------------------------------------------------------------- posing


def mix(a: Pose, b: Pose, u: float) -> Pose:
    """Blend two poses. ``u`` outside 0..1 extrapolates (used for overshoot)."""
    v = a.vec() + (b.vec() - a.vec()) * float(u)
    return Pose.from_vec(v, a.facing if u < 0.5 else b.facing)


def P(name: str, **kw) -> Pose:
    return POSES[name].copy(**kw)


# -------------------------------------------------------------------- timing
def phase(t: float, period: float) -> float:
    """Normalised position in a repeating cycle, 0..1."""
    return (t / period) % 1.0


def pulse(u: float, a: float, b: float) -> float:
    """0 outside [a, b], 1 inside, with eased shoulders. For hit windows."""
    if u <= a or u >= b:
        return 0.0
    x = (u - a) / max(b - a, 1e-6)
    return math.sin(math.pi * x) ** 0.7


# ------------------------------------------------------------------ secondary
class Spring:
    """A damped follower for secondary motion (sash, tip, hem).

    ``step`` is time-based so it behaves the same at 24 fps and at 60 fps.
    ``omega`` sets how lazily it follows, ``zeta`` how much it rings.
    """

    def __init__(self, omega: float = 26.0, zeta: float = 0.75, value: float = 0.0):
        self.omega = omega
        self.zeta = zeta
        self.x = float(value)
        self.v = 0.0

    def step(self, target: float, dt: float) -> float:
        w, z = self.omega, self.zeta
        # semi-implicit integration, stable for dt < 2/w
        self.v += (w * w * (target - self.x) - 2.0 * z * w * self.v) * dt
        self.x += self.v * dt
        return self.x

    def reset(self, value: float = 0.0) -> None:
        self.x = float(value)
        self.v = 0.0


def lag(seq, t: float, delay_frames: float = 3.0, fps: float = 24.0):
    """Sample a time-varying quantity a few frames late (cheap overlap)."""
    return seq(t - delay_frames / fps)


# ---------------------------------------------------------------- staff cycle
class StaffCycle:
    """A trained staff repetition: anticipation → cut → follow-through → settle.

    Phase map (fractions of one cycle):

        0.00  ready      weight settled, staff at rest angle
        0.16  wind       hips settle back, shoulders coil (small counter-rotation)
        0.26  coil peak  the moment of hesitation before release
        0.44  impact     fastest frame, hips drive, lead foot plants
        0.58  follow     staff has travelled past the target, torso overshoots
        0.74  settle     body recovers, staff drifts back up
        1.00  ready

    ``intensity`` scales both the amplitude of the pose blend and the speed of
    the settle, so the same class can drive a slow lesson or a fast exchange.
    """

    #: staff angle (degrees, world) at each phase key
    ANGLES = (118.0, 144.0, 154.0, 98.0, 84.0, 78.0, 94.0, 118.0)
    #: phase positions of those keys
    PHASES = (0.00, 0.16, 0.26, 0.44, 0.58, 0.70, 0.86, 1.00)

    def __init__(self, period: float = 1.15, intensity: float = 1.0, rest: str = "staff_guard",
                 wind: str = "staff_wind", swing: str = "staff_swing",
                 follow: str = "staff_follow", settle: float = 1.0):
        self.period = period
        self.intensity = intensity
        self.rest, self.wind, self.swing, self.follow = rest, wind, swing, follow
        self.settle = settle

    # -- pose at a phase ------------------------------------------------
    def pose(self, u: float) -> Pose:
        k = self.intensity
        ready = P(self.rest, py=4 * k)
        wind = P(self.wind, py=2 * k, spine=176 - 4 * k, arm_f=(132 + 8 * k, 168 + 4 * k))
        coil = mix(wind, P(self.swing), 0.16)          # held coil, slight release
        swing = P(self.swing, py=8 * k, spine=200 + 4 * k, lean_off=2 * k)
        impact = mix(swing, P(self.follow), 0.45)      # body keeps driving through
        follow = P(self.follow, py=14 * k, spine=206 + 3 * k, lean_off=-2 * k)
        settle = mix(follow, ready, 0.55)
        # hips drop on the drive, rise on the recovery (weight shift)
        keys = ((0.00, ready), (0.16, wind), (0.26, coil), (0.44, swing),
                (0.58, impact), (0.70, follow), (0.86, settle), (1.00, ready))
        for i in range(len(keys) - 1):
            (t0, a), (t1, b) = keys[i], keys[i + 1]
            if t0 <= u <= t1:
                x = (u - t0) / max(t1 - t0, 1e-6)
                return mix(a, b, x)
        return ready

    # -- staff angle at a phase (leads the body slightly on the cut) -----
    def angle(self, u: float) -> float:
        ph = self.PHASES
        for i in range(len(ph) - 1):
            if ph[i] <= u <= ph[i + 1]:
                x = (u - ph[i]) / max(ph[i + 1] - ph[i], 1e-6)
                # the tip is fastest through the middle of the cut: ease the
                # approach, let it run linear-to-fast at the impact
                x = x * x * (3 - 2 * x) if x < 0.5 else 0.5 + (x - 0.5) * 1.6
                x = min(x, 1.0)
                a, b = self.ANGLES[i], self.ANGLES[i + 1]
                return a + (b - a) * x
        return self.ANGLES[0]

    # -- convenience ----------------------------------------------------
    def sample(self, t: float) -> tuple[Pose, float, float]:
        """(pose, staff angle, cycle phase) at absolute time ``t``."""
        u = phase(t, self.period)
        return self.pose(u), self.angle(u), u

    def speed(self, t: float, dt: float = 1 / 48) -> float:
        """Normalised angular speed of the staff at ``t`` (0..1), for smears."""
        a = self.angle(phase(t - dt, self.period))
        b = self.angle(phase(t, self.period))
        return min(abs(b - a) / (420.0 * dt), 1.0)

    @property
    def impact_phase(self) -> float:
        return 0.44


def baton(p, sk, look, angle: float, length: float, smear: float = 0.0,
          weight: float = 0.0, depth: float = 1.0, alpha: float = 1.0):
    """Draw a staff, with a swept crescent when it is moving fast.

    The smear is one polygon spanning the arc the staff head just travelled —
    the classic anime motion arc — instead of a stack of offset lines, which
    reads as a solid beam.
    """
    import math as _m
    from .character import draw_staff

    if smear > 0.03:
        span = _m.radians(30.0 * smear + 8.0)
        h = sk.hand_f
        a0 = _m.radians(angle)
        n = 6
        outer, inner = [], []
        for i in range(n + 1):
            th = a0 + span * (i / n)          # trailing arc, tip leads
            r_out = length * (1.0 - 0.10 * (i / n))
            r_in = length * (0.40 + 0.22 * (i / n))
            outer.append((h[0] + _m.cos(th) * r_out, h[1] + _m.sin(th) * r_out))
            inner.append((h[0] + _m.cos(th) * r_in, h[1] + _m.sin(th) * r_in))
        p.polygon_world(outer + inner[::-1], tuple(look.trail),
                        alpha=alpha * 0.16 * smear, depth=depth, additive=True)
    draw_staff(p, sk, look, angle, length=length, depth=depth, alpha=alpha)


def stamp_foot(p, sk, t_since: float, color=(0.65, 0.8, 1.0), scale: float = 1.0,
               depth: float = 1.0, which: str = "to_f"):
    """Impact ring + thrown water where a foot just landed."""
    import math
    from . import fx
    pt = getattr(sk, which)
    if t_since < 0 or t_since > 0.6:
        return
    u = t_since / 0.6
    p.circle((pt[0], pt[1] + 3), (14 + 110 * (1 - (1 - u) ** 3)) * scale, color,
             alpha=(1 - u) ** 2 * 0.5, ring=1.6, additive=True, depth=depth,
             glow=0.2 * (1 - u), glow_color=color)
    if t_since < 0.35:
        fx.Particles(x=pt[0], y=pt[1], t0=0.0, count=18, speed=(120, 520),
                     angle=(math.pi * 1.08, math.pi * 1.92), gravity=1500,
                     life=(0.16, 0.5), size=(0.7, 1.7), color=(0.8, 0.92, 1.0),
                     color_end=(0.4, 0.6, 1.0), seed=3, glow=0.7).draw(p, t_since)


def breath(amount: float, t: float, period: float = 3.4) -> float:
    """Vertical chest offset for idle breathing (world units)."""
    return amount * math.sin(2 * math.pi * t / period)


def ground_of(sk) -> float:
    return max(sk.to_f[1], sk.to_b[1])


def solve_grounded(pose: Pose, rig: Rig, ground: float):
    """Solve with the lowest foot pinned to ``ground`` (no slide, no hover)."""
    return solve(pose, rig, ground=ground)
