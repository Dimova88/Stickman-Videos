"""The physics of a blow: hitstop, compression, anticipation.

Three ideas from hand-drawn fight animation, all of them timing rather than
drawing, so they sit on top of the existing ``time · x · pose`` choreography
instead of rewriting it:

``Clock``
    Real time -> animation time. At every contact the animation clock stops for
    2-4 frames (the hitstop), then runs at double speed for the same number of
    frames, so nothing drifts: over the whole 30 s the map is the identity, yet
    the instant of impact holds still while the camera shakes and the flash
    plays. A punch that was a single frame of contact now reads as a blow.

``compress``
    At that frozen instant the fighter being hit is a little shorter and folds
    around the fist: knees buckle, chest caves, the body is pushed off its feet
    in the direction of the blow. It is a pose delta, so it works for every pose
    without authoring a second one.

``coil``
    In the key just before a strike the attacking limb is pulled back, cocked,
    the weight dropped. The wind-up was already in the timeline as a guard pose;
    this turns the same key into an actual coil.
"""
from __future__ import annotations

import math

FPS = 24.0
FRAME = 1.0 / FPS


# --------------------------------------------------------------------- clock
#: frames the world holds still, by kind of contact
HOLD_FRAMES = {"block": 1, "hit": 2, "clash": 2, "final": 3}


class Clock:
    """Piecewise time map: freeze at a contact, then catch the time back up.

    For one contact at ``t0`` with a hold of ``h`` seconds the animation clock
    runs at 0 for ``[t0, t0+h]`` and at 2x for ``[t0+h, t0+2h]``. The integral
    over that window is exactly ``h * 0 + h * 2 = 2h``, so after ``2h`` the map
    is back on the real clock: every later key, cut and sound stays where it was
    authored. Contacts that land on a frame boundary are used as they are.
    """

    def __init__(self, impacts, fps: float = FPS):
        self.fps = fps
        self.holds: list[tuple[float, float]] = []
        for e in impacts:
            frames = HOLD_FRAMES.get(e["kind"], 1)
            if e["kind"] == "hit" and e.get("size", 1.0) >= 1.0:
                frames = 3
            if e["kind"] == "final":
                frames = 4
            start = round(e["t"] * fps) / fps
            self.holds.append((start, frames / fps))
        self.holds.sort()

    @staticmethod
    def _delta(t: float, start: float, h: float) -> float:
        if t <= start:
            return 0.0
        if t < start + h:                       # frozen
            return -(t - start)
        if t < start + 2.0 * h:                 # catching up at 2x
            return 2.0 * (t - start - h) - h
        return 0.0

    def at(self, t: float) -> float:
        """Animation time for a real time."""
        a = t
        for start, h in self.holds:
            a += self._delta(t, start, h)
        return max(0.0, min(a, t))

    def holding(self, t: float) -> bool:
        """Is the world frozen at this real time? (used by the VFX layer)"""
        return any(s <= t < s + h for s, h in self.holds)


# ------------------------------------------------------------------ squash
#: how long the body stays folded after the instant of contact, in anim seconds
SQUASH_DECAY = 0.17
SQUASH_RISE = 0.10


def _victims(e) -> tuple[str, ...]:
    on = e.get("on")                 # explicit victim, for more than two fighters
    if on:
        return (on,)
    by = e["by"]
    if by == "red":
        return ("blue",)
    if by == "blue":
        return ("red",)
    return ("red", "blue")


def squash_at(impacts, who: str, t: float) -> float:
    """0..1 compression of one fighter at animation time ``t``."""
    k = 0.0
    for e in impacts:
        if who not in _victims(e):
            continue
        r = t - e["t"]
        if -SQUASH_RISE <= r <= 0.0:
            k = max(k, (r + SQUASH_RISE) / SQUASH_RISE)
        elif 0.0 < r < SQUASH_DECAY:
            k = max(k, 1.0 - r / SQUASH_DECAY)
    return min(1.0, k)


def push_at(impacts, who: str, t: float, facing: int) -> float:
    """How far the blow shoves the body backwards, in screen pixels."""
    k = squash_at(impacts, who, t)
    return -facing * 13.0 * k


def compress(pose: dict, k: float) -> dict:
    """Fold a pose around the fist that just landed (``k`` = 0..1)."""
    if k <= 0.002:
        return pose
    q = dict(pose)
    q["crouch"] = q.get("crouch", 0.0) + 17.0 * k
    # the chest caves in, the head goes back over the shoulder
    q["spine"] = q.get("spine", 0.0) - 11.0 * k
    q["torso"] = q.get("torso", -80.0) - 5.0 * k
    q["head"] = q.get("head", 0.0) - 7.0 * k
    # the guard is driven back into the chest
    for side in ("a", "b"):
        q[f"{side}_fore"] = q.get(f"{side}_fore", 0.0) - 12.0 * k
        q[f"{side}_up"] = q.get(f"{side}_up", 0.0) + 7.0 * k
    return q


# -------------------------------------------------------------- anticipation
def _extension(pose: dict, side: str) -> float:
    """How far forward a fist is: 1 = straight out at the target."""
    up = math.radians(pose.get(f"{side}_up", 90.0))
    fore = math.radians(pose.get(f"{side}_fore", 90.0))
    return math.cos(up) * 0.4 + math.cos(fore) * 0.6


def _lifted_foot(pose: dict):
    for name in ("foot_l", "foot_r"):
        f = pose.get(name, (0.0, 0.0))
        if f[1] > 12.0:
            return name
    return None


def coil(strike: dict, before: dict) -> dict:
    """Turn the key before a strike into a coil for the limb that will strike.

    ``strike`` is the pose at the moment of contact — it says *what* is coming;
    ``before`` is the pose already keyed a quarter of a second earlier, which is
    what actually gets pulled back.
    """
    q = dict(before)
    # the weight drops and the body turns slightly away from the target first
    q["crouch"] = q.get("crouch", 0.0) + 6.0
    q["torso"] = q.get("torso", -80.0) - 5.0
    q["spine"] = q.get("spine", 0.0) + 4.0

    foot = _lifted_foot(strike)
    arm = "b" if _extension(strike, "b") >= _extension(strike, "a") else "a"
    if foot is not None:
        # a kick chambers: knee up, heel under the hip, before it fires
        fx, lift = q.get(foot, (0.0, 0.0))
        q[foot] = (fx - 26.0 if strike.get("torso", -80) < -40 else fx - 26.0,
                   max(lift, 0.0) + 26.0)
        q["toe_l" if foot == "foot_l" else "toe_r"] = 18.0
    else:
        # a punch cocks: the elbow comes back, the fist loads at the shoulder
        q[f"{arm}_up"] = 58.0
        q[f"{arm}_fore"] = -72.0
        q[f"grip_{arm}"] = 0.95
    return q


def add_anticipation(track, impacts, reach: float = 0.36) -> int:
    """Bend the keys just before every landed blow into a wind-up.

    Only the *pose* of the existing key changes, never its time, so the spacing
    solver downstream still sees the same skeleton of the choreography.
    """
    changed = 0
    for e in impacts:
        if e["kind"] not in ("hit", "final") and e["kind"] != "clash":
            continue
        by = e["by"]
        if by not in ("both", track.name):
            continue
        t = e["t"]
        keys = track.keys
        i = min(range(len(keys)), key=lambda j: abs(keys[j][0] - t))
        if abs(keys[i][0] - t) > 0.05 or i == 0:
            continue
        strike = keys[i][1]
        # the key that was already there to load the blow
        j = i - 1
        if t - keys[j][0] > reach:
            continue
        # don't touch a key that is itself the previous blow's contact
        if any(abs(keys[j][0] - o["t"]) < 0.05 for o in impacts):
            continue
        t0, p0, x0, e0 = keys[j]
        track.keys[j] = (t0, coil(strike, p0), x0, e0)
        changed += 1
    return changed
