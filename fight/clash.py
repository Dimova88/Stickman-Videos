"""Clash, 30 s test — choreography (one fight, several sets).

Follows the process used for ``Mountain_Clash_Red_vs_Blue.mp4``:

* two fighters built from the StykAnimate Pivot skeleton, red facing right and
  blue facing left (every pose is mirrored for the blue fighter);
* keyframe choreography — each key is ``time · x · pose`` and between keys the
  body, the height and every joint are interpolated with smoothstep;
* a flat list of impacts, each with instant, screen position, colour, type
  (block / hit / clash / final), intensity and damage — that single list drives
  body reactions, particles, camera shake, health bars and audio.

Positions are in the 1280x720 design space: floor at y=590, resting pelvis at
y=480 (that is what ``HIP_SCALE`` works out to for this rig).
"""
from __future__ import annotations

import math

from . import poses as PS
from .core import Pose, solve
from .impact import Clock, add_anticipation, compress, push_at, squash_at
from .poses import fade, mirror, to_pose
from .ragdoll import knockdown, reanchor

FPS = 24
DURATION = 30.0

DESIGN_W, DESIGN_H = 1280, 720
GROUND = 590.0                     # y of the rock platform the fighters stand on
FIG_SCALE = 1.30                   # 1.0 puts the pelvis 129 units above the floor
STANCE = 1.75                      # stance width multiplier: a wide, planted base

# The choreography is the same everywhere; only the set dressing and the words
# change, so a new location is one entry here plus one painted plate.
SETS = {
    "mountain": {"title": "MOUNTAIN CLASH", "sub": "VICTORY ON THE SUMMIT",
                 "hud": "MOUNTAIN  •  ROUND 1"},
    "desert": {"title": "DESERT CLASH", "sub": "VICTORY IN THE DUNES",
               "hud": "DESERT  •  ROUND 1"},
}

RED = (196, 58, 50)
RED_DARK = (138, 36, 31)
BLUE = (44, 92, 166)
BLUE_DARK = (28, 60, 118)
INK = (26, 24, 24)

EASE = {
    "smooth": lambda u: u * u * (3 - 2 * u),      # u^2 * (3 - 2u)
    "out": lambda u: 1 - (1 - u) ** 3,
    "snap": lambda u: 1 - (1 - u) ** 5,
    "in": lambda u: u ** 3,
    "linear": lambda u: u,
}


class Track:
    """One fighter: keys of (time, pose, x, ease), sampled with smoothstep."""

    def __init__(self, name: str, facing: int, colour, dark):
        self.name, self.facing = name, facing
        self.colour, self.dark = colour, dark
        self.keys: list[tuple[float, dict, float, str]] = []

    def key(self, t: float, pose: dict, x: float, ease: str = "smooth") -> "Track":
        self.keys = [k for k in self.keys if abs(k[0] - t) > 1e-6]
        self.keys.append((float(t), dict(pose), float(x), ease))
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
                return a, b, EASE.get(b[3], EASE["smooth"])(u)
        return ks[-1], ks[-1], 0.0

    def sample(self, t: float):
        a, b, u = self._pair(t)
        pa, pb = a[1], b[1]
        keys = set(pa) | set(pb)
        pose = {}
        for k in keys:
            if k == "hip":                       # optional pinned hip height
                va, vb = pa.get("hip"), pb.get("hip")
                if va is None or vb is None:
                    pose[k] = (va if vb is None else vb)
                else:
                    pose[k] = va + (vb - va) * u
                continue
            if k in ("foot_l", "foot_r"):
                a0 = pa.get(k, (0.0, 0.0))
                b0 = pb.get(k, (0.0, 0.0))
                pose[k] = (a0[0] + (b0[0] - a0[0]) * u, a0[1] + (b0[1] - a0[1]) * u)
            else:
                pose[k] = pa.get(k, 0.0) + (pb.get(k, 0.0) - pa.get(k, 0.0)) * u
        x = a[2] + (b[2] - a[2]) * u
        return pose, x

    def pose_at(self, t: float) -> Pose:
        p, x = self.sample(t)
        return to_pose(p, x, GROUND, facing=self.facing, scale=FIG_SCALE,
                       widen=STANCE)

    def skel(self, t: float):
        return solve(self.pose_at(t))


# =========================================================== the choreography
def build(set_name: str = "mountain") -> dict:
    words = SETS.get(set_name, SETS["mountain"])
    red = Track("red", 1, RED, RED_DARK)
    blue = Track("blue", -1, BLUE, BLUE_DARK)

    impacts: list[dict] = []
    dusts: list[float] = []
    texts: list[dict] = []

    # ---------------------------------------------------------------- helpers
    def impact(t, kind, size=1.0, dmg_red=0.0, dmg_blue=0.0, anchor=None, by="red"):
        """kind: block | hit | clash | final. By: who throws it (or both)."""
        # the vector of the blow, for the camera: +1 lands to the right, -1 to
        # the left, 0 is a clash straight down the middle
        dx = 1.0 if by == "red" else (-1.0 if by == "blue" else 0.0)
        impacts.append({"t": t, "kind": kind, "size": size, "by": by, "dx": dx,
                        "dmg_red": dmg_red, "dmg_blue": dmg_blue, "anchor": anchor})

    def dust(t):
        dusts.append(t)

    def title(t0, t1, text, style="plain"):
        texts.append({"t0": t0, "t1": t1, "text": text, "style": style})

    I = PS.IDLE
    G = PS.GUARD
    T = PS.TIGHT

    # ---------------------------------------------------------------- 0-2.4 intro
    # entrance: both fighters run in from off-frame and skid to a stop in front
    # of each other. The distance is what makes the feet step (see footwork.py)
    red.key(0.0, I, 402)
    blue.key(0.0, I, 878)
    title(0.35, 2.55, words["title"], "title")
    title(0.95, 2.75, "RED  VS  BLUE", "sub")

    red.key(0.45, fade(I, torso=-8), 412, "out")
    blue.key(0.48, fade(I, torso=-8), 868, "out")
    red.key(1.32, fade(G, torso=-84), 520, "out")
    blue.key(1.36, fade(G, torso=-84), 760, "out")
    red.key(1.78, fade(G, torso=-66, crouch=10), 548)
    blue.key(1.82, fade(G, torso=-66, crouch=10), 738)
    red.key(2.30, G, 545)
    blue.key(2.35, G, 742)
    title(2.15, 2.85, "FIGHT!", "fight")
    dust(2.45)

    # ------------------------------------------------- 2.6-5.0 blue blocks, counters
    red.key(2.62, T, 560, "out")
    blue.key(2.62, PS.BLOCK_HI, 742, "out")
    red.key(2.90, PS.JAB, 588, "snap")
    impact(2.90, "block", 0.45, dmg_blue=0.0, by="red")
    red.key(3.16, G, 570, "out")

    red.key(3.40, fade(T, torso=-76), 574, "out")
    red.key(3.66, PS.CROSS, 604, "snap")
    blue.key(3.45, PS.SLIP, 748, "out")
    impact(3.66, "block", 0.35, dmg_blue=2.0, by="red")

    blue.key(3.92, fade(T, torso=-76), 730, "out")
    blue.key(4.16, PS.JAB, 706, "snap")
    red.key(4.10, PS.BLOCK_HI, 592, "snap")
    impact(4.16, "block", 0.5, by="blue")
    blue.key(4.42, T, 716, "out")
    blue.key(4.66, PS.CROSS, 694, "snap")
    impact(4.66, "hit", 0.7, dmg_red=6.0, by="blue")
    red.key(4.68, PS.HIT_HEAD, 596, "snap")
    red.key(4.98, G, 584, "out")

    # ------------------------------------------------- 5.0-7.4 red's answer
    blue.key(4.96, fade(T, torso=-74), 700, "out")
    blue.key(5.16, PS.KICK_MID, 678, "snap")
    red.key(5.14, PS.BLOCK_MID, 588, "snap")
    impact(5.16, "block", 0.75, dmg_red=1.0, by="blue")
    blue.key(5.42, fade(T, torso=-74), 700, "out")
    blue.key(5.70, PS.KICK_HI, 676, "snap")
    red.key(5.68, PS.SLIP, 588, "snap")
    impact(5.70, "block", 0.8, by="blue")
    blue.key(6.02, G, 712, "out")

    red.key(6.10, fade(T, torso=-76), 600, "out")
    red.key(6.36, PS.HOOK, 634, "snap")
    blue.key(6.36, PS.BLOCK_HI, 714, "snap")
    impact(6.36, "block", 0.6, dmg_blue=3.0, by="red")
    red.key(6.62, T, 612, "out")

    red.key(6.90, PS.SWEEP, 640, "snap")
    blue.key(6.88, PS.AIRBORNE, 726, "snap")
    blue.key(7.22, PS.LANDED, 722, "snap")
    dust(7.24)
    blue.key(7.46, G, 716, "out")

    red.key(7.58, fade(T, torso=-78), 636, "out")
    red.key(7.86, PS.UPPERCUT, 664, "snap")
    blue.key(7.88, PS.HIT_HEAD, 726, "snap")
    impact(7.86, "hit", 1.0, dmg_blue=9.0, by="red")
    knockdown(blue, 7.86, 9.62, throw=34.0, dust=dust)
    title(8.20, 8.60, "DOWN!", "small")
    red.key(8.70, G, 640, "out")

    # ------------------------------------------------- 9.6-12.4 blue's counter
    blue.key(9.66, fade(T, torso=-78), 716, "out")
    blue.key(9.92, PS.JAB, 692, "snap")
    red.key(9.92, PS.BLOCK_HI, 646, "snap")
    impact(9.92, "block", 0.5, by="blue")
    blue.key(10.16, T, 704, "out")
    blue.key(10.40, PS.CROSS, 680, "snap")
    red.key(10.40, PS.BLOCK_HI, 654, "snap")
    impact(10.40, "block", 0.55, by="blue")
    blue.key(10.66, T, 700, "out")
    blue.key(10.94, PS.AERIAL_KICK, 676, "snap")
    impact(10.94, "hit", 1.0, dmg_red=9.0, by="blue")
    red.key(10.96, PS.HIT_HEAD, 656, "snap")
    blue.key(11.28, PS.LANDED, 700, "snap")
    dust(11.30)
    blue.key(11.60, G, 706, "out")

    # ------------------------------------------------- 11.0-12.6 red recovers
    knockdown(red, 10.94, 12.55, throw=32.0, dust=dust)
    blue.key(12.30, fade(G, torso=-82), 700)

    # ------------------------------------------------- 12.5-15.0 exchange
    red.key(12.66, T, 660, "out")
    blue.key(12.66, T, 694, "out")
    red.key(12.92, PS.JAB, 686, "snap")
    blue.key(12.92, PS.BLOCK_HI, 696, "snap")
    impact(12.92, "block", 0.45, by="red")
    blue.key(13.18, PS.JAB, 676, "snap")
    red.key(13.18, PS.BLOCK_HI, 664, "snap")
    impact(13.18, "block", 0.45, by="blue")
    red.key(13.44, PS.CROSS, 690, "snap")
    blue.key(13.44, PS.CROSS, 672, "snap")
    impact(13.44, "clash", 1.1, anchor="fists", by="both")
    red.key(13.76, PS.HIT_HEAD, 660, "out")
    blue.key(13.76, PS.HIT_HEAD, 690, "out")
    red.key(14.06, G, 656, "out")
    blue.key(14.06, G, 688, "out")

    # ------------------------------------------------- 14.2-16.6 blue takes over
    blue.key(14.30, fade(T, torso=-74), 686, "out")
    blue.key(14.58, PS.KICK_HI, 662, "snap")
    red.key(14.56, PS.DUCK, 656, "snap")
    impact(14.58, "block", 0.45, by="blue")
    blue.key(14.90, T, 674, "out")

    # a chain, not a trade: the high kick is ducked, red comes in underneath it,
    # takes the collar, knees the body and throws blue off him. Each action feeds
    # the next, so the exchange has a shape instead of being separate hits.
    red.key(14.86, PS.CLINCH, 678, "out")
    blue.key(14.92, fade(T, torso=-70), 666, "out")
    impact(14.92, "block", 0.20, by="red")

    red.key(15.14, PS.KNEE, 682, "snap")
    blue.key(15.16, PS.HIT_BODY, 668, "snap")
    impact(15.14, "hit", 0.62, dmg_blue=7.0, by="red")

    red.key(15.42, PS.SHOVE, 690, "snap")
    blue.key(15.46, PS.STAGGER, 702, "out")
    impact(15.44, "hit", 0.55, dmg_blue=5.0, by="red")
    dust(15.48)
    red.key(15.66, PS.TIGHT, 646, "out")

    blue.key(15.80, PS.UPPERCUT, 656, "snap")
    red.key(15.82, PS.HIT_HEAD, 640, "snap")
    impact(15.80, "hit", 1.05, dmg_red=10.0, by="blue")
    blue.key(16.40, G, 668, "out")

    # ------------------------------------------------- 15.8-17.5 red's comeback
    knockdown(red, 15.80, 17.45, throw=30.0, dust=dust)
    blue.key(17.20, fade(T, torso=-80), 678, "out")

    red.key(17.56, PS.JAB, 672, "snap")
    blue.key(17.56, PS.BLOCK_HI, 680, "snap")
    impact(17.56, "block", 0.5, by="red")
    red.key(17.84, PS.CROSS, 700, "snap")
    blue.key(17.84, PS.HIT_HEAD, 690, "snap")
    impact(17.84, "hit", 0.9, dmg_blue=8.0, by="red")
    red.key(18.12, fade(T, torso=-74), 690, "out")
    red.key(18.40, PS.KICK_HI, 700, "snap")
    blue.key(18.40, PS.HIT_HEAD, 690, "snap")
    impact(18.40, "hit", 1.0, dmg_blue=9.0, by="red")
    red.key(18.72, fade(T, torso=-82), 682, "out")

    red.key(18.98, PS.AERIAL_KICK, 690, "snap")
    blue.key(19.00, PS.HIT_HEAD, 700, "snap")
    impact(18.98, "hit", 1.1, dmg_blue=11.0, by="red")
    red.key(19.30, PS.LANDED, 676, "snap")
    dust(19.32)
    red.key(19.60, G, 668, "out")

    # ------------------------------------------------- 19.0-20.4 blue gets up
    knockdown(blue, 18.98, 20.38, throw=36.0, dust=dust)
    red.key(20.30, fade(G, torso=-80), 672)

    # ------------------------------------------------- 20.6-23.4 final exchange
    red.key(20.62, T, 680, "out")
    blue.key(20.62, T, 700, "out")
    red.key(20.88, PS.JAB, 700, "snap")
    blue.key(20.88, PS.BLOCK_HI, 704, "snap")
    impact(20.88, "block", 0.5, by="red")
    blue.key(21.14, PS.JAB, 684, "snap")
    red.key(21.14, PS.BLOCK_HI, 668, "snap")
    impact(21.14, "block", 0.5, by="blue")
    red.key(21.40, PS.CROSS, 706, "snap")
    blue.key(21.40, PS.CROSS, 678, "snap")
    impact(21.40, "clash", 1.2, anchor="fists", by="both")
    red.key(21.72, PS.HIT_HEAD, 676, "out")
    blue.key(21.72, PS.HIT_HEAD, 700, "out")
    red.key(22.00, G, 672, "out")
    blue.key(22.00, G, 702, "out")

    # ------------------------------------------------- 22.2-24.6 blue finishes
    red.key(22.10, PS.HOOK, 674, "snap")
    blue.key(22.10, PS.BLOCK_HI, 702, "snap")
    impact(22.10, "block", 0.6, dmg_blue=2.0, by="red")
    blue.key(22.24, T, 700, "out")
    blue.key(22.50, PS.JAB, 678, "snap")
    red.key(22.50, PS.BLOCK_HI, 678, "snap")
    impact(22.50, "block", 0.5, by="blue")
    blue.key(22.76, PS.CROSS, 660, "snap")
    red.key(22.76, PS.HIT_HEAD, 668, "snap")
    impact(22.76, "hit", 0.9, dmg_red=8.0, by="blue")
    blue.key(23.02, fade(T, torso=-74), 668, "out")
    blue.key(23.28, PS.KICK_MID, 660, "snap")
    red.key(23.28, PS.HIT_BODY, 664, "snap")
    impact(23.28, "hit", 1.0, dmg_red=10.0, by="blue")
    blue.key(23.58, T, 674, "out")
    blue.key(23.84, PS.AERIAL_KICK, 690, "snap")
    red.key(23.86, PS.HIT_HEAD, 668, "snap")
    impact(23.84, "hit", 1.1, dmg_red=12.0, by="blue")
    blue.key(24.14, PS.LANDED, 682, "snap")
    dust(24.16)
    red.key(24.16, PS.FALL, 660, "out")

    # the finishing blow
    blue.key(24.44, fade(T, torso=-78), 684, "out")
    blue.key(24.72, PS.UPPERCUT, 664, "snap")
    red.key(24.72, PS.HIT_HEAD, 654, "snap")
    impact(24.72, "final", 1.8, dmg_red=100.0, by="blue")
    knockdown(red, 24.72, 30.0, throw=46.0, power=1.2, dust=dust, stay=True)

    # ------------------------------------------------- 25.2-30 K.O. and victory
    blue.key(25.10, fade(G, torso=-84), 690, "out")
    blue.key(25.90, PS.VICTORY, 676, "out")
    blue.key(27.40, fade(PS.VICTORY, torso=-88), 672)
    blue.key(29.20, PS.VICTORY, 668, "smooth")


    title(25.24, 26.85, "K.O.", "ko")
    title(26.85, 29.20, "BLUE WINS", "title")
    title(26.60, 29.30, words["sub"], "sub")
    title(0.0, 30.0, words["hud"], "hud")

    # ---------------------------------------------------------- anticipation
    # the loaded key before every landed blow becomes an actual coil
    for tr in (red, blue):
        add_anticipation(tr, impacts)

    # ---------------------------------------------------------------- spacing
    # the pair must never collapse into one blob: heads stay a fist-and-forearm
    # apart, closer only when someone is on top of the other
    gap_keys = [(0.0, 360.0), (1.6, 330.0), (2.4, 222.0), (7.7, 222.0),
                (8.1, 240.0), (9.3, 250.0), (11.2, 235.0), (12.6, 232.0),
                (13.3, 220.0), (15.9, 220.0), (16.6, 245.0), (19.4, 245.0),
                (20.3, 232.0), (24.4, 220.0), (25.4, 280.0), (30.0, 300.0)]

    def _down(tr, t):
        """Is this fighter off its feet, or inside a knockdown?

        A body that has been knocked down is not nudged to keep the pair apart:
        it is on the floor, and the standing fighter steps around it. Letting the
        spacing solvers loose on those frames is what made a thrown body slide
        sideways while it was lying still.
        """
        if tr.sample(t)[0].get("hip", 999.0) < 95.0:
            return True
        for g in getattr(tr, "_kd", ()):
            if g["t_hit"] <= t <= g["end"]:
                return True
        return False

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

    def relax(iters=14, step=0.30):
        for _ in range(iters):
            t = 0.0
            while t <= DURATION:
                dr, db = _down(red, t), _down(blue, t)
                if dr and db:
                    t += 0.1
                    continue
                g = blue.skel(t).head[0] - red.skel(t).head[0]
                want = gap_at(t)
                if g < want - 0.5:
                    push = (want - g) * 0.5
                    for tr, sgn in ((red, -1.0), (blue, 1.0)):
                        if (tr is red and dr) or (tr is blue and db):
                            continue
                        ks = tr.keys
                        for i in range(len(ks) - 1):
                            t0, p0, x0, e0 = ks[i]
                            t1, p1, x1, e1 = ks[i + 1]
                            if t0 <= t <= t1:
                                u = (t - t0) / max(t1 - t0, 1e-9)
                                w0, w1 = (1 - u) ** 2, u * u
                                ks[i] = (t0, p0, x0 + sgn * push * w0 * step, e0)
                                ks[i + 1] = (t1, p1, x1 + sgn * push * w1 * step, e1)
                                break
                t += 0.1
    relax()

    # the closest the two heads may come, over time: it tightens only for the
    # instant of a strike (the fist has to arrive) and opens again after it
    strike_times = sorted({e["t"] for e in impacts if e["kind"] != "clash"})
    clash_times = sorted({e["t"] for e in impacts if e["kind"] == "clash"})

    def min_gap(t):
        g = 178.0
        for st, dip in ((strike_times, 148.0), (clash_times, 150.0)):
            for ts in st:
                k = abs(t - ts)
                if k < 0.34:
                    g = min(g, dip + (214.0 - dip) * (k / 0.34) ** 1.5)
        return g

    # ------------------------------------------------------------ impact reach
    # A strike only reads if the fist (or foot) actually arrives. For every
    # impact, step the attacker in at that key until the striking limb is on the
    # target, while keeping the pair from collapsing into one silhouette.
    def kd_times(tr):
        out = set()
        for g in getattr(tr, "_kd", ()):
            out.update(t for t, _f, _p in g["fly"])
            if g["guard"] is not None:
                out.add(g["guard"])
        return out

    def _nearest_key(tr, t):
        """The nearest key that is not part of a knockdown.

        A knockdown key sits a frame or two after the contact, so picking the
        nearest key by time used to move the *launch* instead of the fist and
        leave the blow short of the head.
        """
        skip = kd_times(tr)
        cands = [i for i, k in enumerate(tr.keys) if k[0] not in skip]
        return min(cands, key=lambda i: abs(tr.keys[i][0] - t))

    def strike_of(t: float):
        """Who is attacking at t, and with which limb.

        Picking the attacker by proximity alone is ambiguous — a defender's
        guard is also near the other head. The attacker is the one whose limb is
        *closing* on the opponent's head fastest, which is what a strike is.
        """
        best = None
        for tr, other in ((red, blue), (blue, red)):
            now, then = tr.skel(t), tr.skel(t - 0.09)
            target = other.skel(t).head
            for i in (4, 6, 8, 10):
                d_now = math.hypot(target[0] - now.pts[i][0], target[1] - now.pts[i][1])
                d_then = math.hypot(target[0] - then.pts[i][0], target[1] - then.pts[i][1])
                closing = d_then - d_now
                score = closing - d_now * 0.05
                if best is None or score > best[0]:
                    best = (score, d_now, tr, i, target)
        return best[1], best[2], best[3], best[4]

    def reach(iters=9):
      for _ in range(iters):
        for e in impacts:
            t = e["t"]
            gap = abs(blue.skel(t).head[0] - red.skel(t).head[0])
            who = e["by"]
            # a blocked blow has to land on the blocking hands, a landed blow on
            # the head (or torso, for a body kick)
            climbers = (red,) if who == "red" else ((blue,) if who == "blue" else (red, blue))
            if who == "both":
                # the two fists meet: measure the signed overlap, so the pass
                # separates them when the punches have crossed through each other
                fa = max(red.skel(t).pts[4][0], red.skel(t).pts[6][0])
                fb = min(blue.skel(t).pts[4][0], blue.skel(t).pts[6][0])
                err = fa - fb            # > 0 means red's fist is past blue's
                if abs(err) <= 6.0:
                    continue
                shift = err * 0.5
                for tr, sgn in ((red, -1.0), (blue, 1.0)):
                    idx = _nearest_key(tr, t)
                    kt, kp, kx, ke = tr.keys[idx]
                    tr.keys[idx] = (kt, kp, kx + sgn * shift, ke)
                continue
            else:
                own = red.skel(t) if who == "red" else blue.skel(t)
                other = blue.skel(t) if who == "red" else red.skel(t)
                if e["kind"] == "block":
                    targets = [other.pts[4], other.pts[6]]
                    want = 16.0
                elif e["kind"] == "final":
                    targets = [other.head]
                    want = 40.0
                elif e["by"] == "blue" and t in (5.16, 23.28):
                    hip, sh = other.starts[1], other.pts[1]
                    targets = [((hip[0] + sh[0]) * 0.5, (hip[1] + sh[1]) * 0.5)]
                    want = 30.0
                else:
                    targets = [other.head]
                    want = 40.0
                d = min(math.hypot(tg[0] - own.pts[i][0], tg[1] - own.pts[i][1])
                        for i in (4, 6, 8, 10) for tg in targets)
            if d <= want + 2.0:
                continue
            step = min((d - want) * 0.9, max(0.0, gap - min_gap(t)))
            if step <= 0.0:
                continue
            for tr in climbers:
                idx = _nearest_key(tr, t)
                kt, kp, kx, ke = tr.keys[idx]
                tr.keys[idx] = (kt, kp, kx + step * tr.facing, ke)

    def relax_after(iters=6, step=0.30):
        for _ in range(iters):
            t = 0.0
            while t <= DURATION:
                dr, db = _down(red, t), _down(blue, t)
                if dr and db:
                    t += 0.1
                    continue
                g = blue.skel(t).head[0] - red.skel(t).head[0]
                lo = min_gap(t)
                if g < lo - 0.5:
                    push = (lo - g) * 0.5
                    for tr, sgn in ((red, -1.0), (blue, 1.0)):
                        if (tr is red and dr) or (tr is blue and db):
                            continue
                        ks = tr.keys
                        for i in range(len(ks) - 1):
                            t0, p0, x0, e0 = ks[i]
                            t1, p1, x1, e1 = ks[i + 1]
                            if t0 <= t <= t1:
                                u = (t - t0) / max(t1 - t0, 1e-9)
                                w0, w1 = (1 - u) ** 2, u * u
                                ks[i] = (t0, p0, x0 + sgn * push * w0 * step, e0)
                                ks[i + 1] = (t1, p1, x1 + sgn * push * w1 * step, e1)
                                break
                t += 0.1
    # Two passes, because a knockdown and the reach solver share one number:
    # the reach moves the contact, the knockdown hangs off the contact.
    reach()
    for tr in (red, blue):
        reanchor(tr)
    relax_after()
    reach()
    for tr in (red, blue):
        reanchor(tr)

    # ------------------------------------------------------- impact positions
    # the star sits where the attacking limb meets the body it is aimed at
    for e in impacts:
        t = e["t"]
        sa, sb = red.skel(t), blue.skel(t)
        if e["anchor"] == "fists":
            # the two most extended fists: red reaches right, blue reaches left
            fa = max((sa.pts[4], sa.pts[6]), key=lambda p: p[0])
            fb = min((sb.pts[4], sb.pts[6]), key=lambda p: p[0])
            e["x"] = (fa[0] + fb[0]) * 0.5
            e["y"] = (fa[1] + fb[1]) * 0.5
            e["colour"] = (232, 232, 226)
            continue
        cands = []
        for own, other, who in ((sa, sb, "red"), (sb, sa, "blue")):
            hip, sh = own.starts[1], own.pts[1]
            torso = ((hip[0] + sh[0]) * 0.5, (hip[1] + sh[1]) * 0.5)
            for i in (4, 6, 8, 10):
                for target in (other.head, torso):
                    d = math.hypot(target[0] - own.pts[i][0],
                                   target[1] - own.pts[i][1])
                    cands.append((d, own.pts[i], target, who))
        d, limb, target, who = min(cands, key=lambda c: c[0])
        e["x"] = target[0] + (limb[0] - target[0]) / max(d, 1.0) * 26.0
        e["y"] = target[1] + (limb[1] - target[1]) / max(d, 1.0) * 20.0
        e["colour"] = RED if who == "blue" else BLUE   # the colour of the striker

    # ---------------------------------------------------------------- camera
    # slow drift across the landscape plus a push-in on the finish
    camera = [(0.0, 0.0, 0.0, 1.00), (2.6, 6.0, 0.0, 1.02),
              (7.0, 12.0, 1.0, 1.03), (12.0, 16.0, 0.0, 1.04),
              (16.6, 20.0, 2.0, 1.04), (21.5, 24.0, 1.0, 1.06),
              (25.4, 26.0, 0.0, 1.04), (30.0, 30.0, 2.0, 1.05)]

    return {"set": set_name, "red": red, "blue": blue, "impacts": impacts,
            "dust": dusts, "texts": texts, "camera": camera,
            "clock": Clock(impacts), "squash_at": squash_at,
            "push_at": push_at, "compress": compress}
