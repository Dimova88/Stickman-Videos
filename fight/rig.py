"""Turning on the horizontal axis: the 2.5D body turn.

The fighters used to have a ``facing`` that was an **integer** decided once, when
the track was built: red looks right, the rivals look left, for the whole film.
That is fine while the choreography is a single line with one man on each side,
and it falls apart the moment the fight uses the whole arena — after a side swap
the protagonist is standing on the far side of an enemy that is still drawn
facing away from him, so he *moonwalks*: his chest, his guard, his knee bend and
his blade all point at a rival who is now behind his back.

This module makes the turn a **continuous number**, ``facing_scale``:

======================  ==========================================================
``+1.0``                looking right, full width, exactly the authored pose
``0.0``                 edge-on: the shoulders and the stance compress to a strip
``-1.0``                looking left, the same pose mirrored
======================  ==========================================================

A turn takes :data:`FLIP_TIME` — three frames at 24 fps — and interpolates
*through* zero rather than cutting, which is what gives the figure a shoulder
turn instead of a teleport. Three things have to follow the scale, and all three
are here so no call site can get them wrong:

* **angles** — ``theta_world = atan2(sin t, facing_scale * cos t)``. At +1 this
  is the identity, at -1 it is ``pi - t`` (the mirror the renderer already used),
  and in between it foreshortens the horizontal component of every bone, so a
  half-turn is a body seen at 45 degrees.
* **the limbs' bend direction** — the leg and arm chains are solved in the
  canonical right-facing frame and then reflected, so a knee cannot bend
  backwards; the reflection is now just the same angle map.
* **the face** — the lit slits slide to the side the head is actually turned to
  and flatten to a single line as the head passes the profile.
"""
from __future__ import annotations

import math

#: how long a full turn takes, in seconds (three frames at 24 fps)
FLIP_TIME = 3.0 / 24.0

#: a fighter does not change his mind twice a second: after a turn the next one
#: has to be worth it
HOLD_TIME = 0.26

#: below this the body is edge-on and the horizontal extents stop shrinking, so
#: a turn never collapses the figure to a vertical line
MIN_SQUASH = 0.22

#: two fighters within this many pixels of each other are *not* asked to turn:
#: without the dead band a crossing pair flips back and forth every frame
DEADBAND = 20.0


def desired_facing(fighter_x: float, target_x: float, current: float = 1.0) -> int:
    """Which way a fighter should be looking, given where his opponent is."""
    dx = target_x - fighter_x
    if abs(dx) < DEADBAND:
        return 1 if current >= 0.0 else -1
    return 1 if dx > 0.0 else -1


def squash(facing_scale: float) -> float:
    """The signed horizontal compression, |s| clamped so the body stays a body."""
    s = math.copysign(max(MIN_SQUASH, min(1.0, abs(facing_scale))), facing_scale)
    return s


def mirror_angle(angle: float, facing_scale: float) -> float:
    """Map a canonical (right-facing) angle into the world for a given turn."""
    if abs(facing_scale - 1.0) < 1e-6:
        return angle
    s = squash(facing_scale)
    return math.atan2(math.sin(angle), s * math.cos(angle))


def mirror_angles(angles, facing_scale: float):
    if abs(facing_scale - 1.0) < 1e-6:
        return tuple(angles)
    return tuple(mirror_angle(a, facing_scale) for a in angles)


def eye_slits(head, radius: float, facing_scale: float):
    """Where the two lit slits go on the head, and how they slant.

    Returns ``(centre_x, centre_y, slant, width)`` in design units. When the head
    is edge-on both slits sit on the centre line and the width collapses, which
    is the one drawing that reads as a face turning away without adding a nose.
    """
    s = squash(facing_scale)
    side = 1.0 if facing_scale >= 0.0 else -1.0
    cx = head[0] + side * abs(s) * radius * 0.46
    cy = head[1] - radius * 0.10
    slant = -0.30 * side
    width = 0.40 + 0.60 * abs(s)
    return cx, cy, slant, width


#: the lane a fighter stands in *now*: the engaged pair share the fighting
#: plane, so their blades meet in the same depth and neither is drawn over the
#: other for a reason the audience cannot see
ENGAGED_Z = 0.0


def lane_of(scene, track, t: float) -> float:
    engaged = active_opponent(scene, t)
    if engaged is not None and track.name in ("red", engaged):
        return ENGAGED_Z
    return getattr(track, "z", 0.0)


def is_engaged(scene, track, t: float) -> bool:
    engaged = active_opponent(scene, t)
    return engaged is not None and track.name in ("red", engaged)


def active_opponent(scene, t: float):
    """Who the hero is *engaged with* at ``t``, from the beat sheet.

    "Nearest" is not the same question. A rival can be standing closer to him
    than the man he is actually trading with — that is what a 1-vs-3 looks like
    from the inside — and a fighter who turned to face the nearest silhouette
    instead of his opponent would be turning his back on the fight.
    """
    for t0, t1, name in scene.get("engagements") or ():
        if t0 <= t <= t1:
            return name
    return None


def _alive(track, t: float) -> bool:
    """A fighter on the floor is not someone to keep looking at."""
    pose = track.sample(t)[0]
    # a man thrown through the air is still the man he is fighting: only a body
    # settled on the floor stops being worth a look
    return pose.get("hip", 999.0) > 22.0 or pose.get("air", 0.0) > 40.0


#: A turn is only worth making when the man he is fighting has really changed
#: side: 26 px of dead band is about a shoulder's width, which is the smallest
#: crossing that is not just two grappled bodies overlapping.
TURN_DEADZONE = 22.0

#: and no fighter changes his mind faster than this: 16 frames at 24 fps is two
#: thirds of a second. Round 8 turned 26 times in 30 s because every crossing of
#: a grapple fired a three-frame turn, which read as a weathervane.
MIN_FRAMES_BETWEEN_TURNS = 17

#: a turn is three frames, and it has to be *finished* by the frame the new side
#: is needed, so it is scheduled to begin two frames early
TURN_FRAMES = 3


def build_facing_schedule(track, wanted, *, deadzone: float | None = None,
                          cooldown: int | None = None,
                          turn_frames: int = TURN_FRAMES,
                          confirm: int = 3, step: int = 2,
                          urgent: float = 180.0,
                          force: set | None = None) -> tuple[list[float], int]:
    """The turn schedule for one fighter, frame by frame.

    ``wanted`` is the per-frame *target x* he should be looking at (the man he is
    engaged with, or None). A turn is a decision, so it is not taken from a
    single frame:

    * **the dead band** (22 px) — two men 30 px apart in a collar grab are not
      "crossing", they are holding each other;
    * **the confirmation** — the new side has to still be the new side three
      frames later, which is what a grapple, a throw and a juggle never do twice
      in a row;
    * **the cool-down** (14 frames) — nothing changes its mind faster than that;
    * **the urgency** — a man who is 110 px the wrong side of him is not a
      wobble, he is *behind him*, and that turn is taken at once (with a short
      four-frame guard) even inside the cool-down. Without this the schedule is
      technically right and the audience still sees twenty-one frames of the
      protagonist facing a man who has already been thrown past his shoulder.

    The ramp then starts two frames early, so the body arrives on the new side on
    the frame it is needed rather than four frames after it.
    """
    n = len(wanted)
    if n == 0:
        return [], 0
    deadzone = TURN_DEADZONE if deadzone is None else deadzone
    cooldown = MIN_FRAMES_BETWEEN_TURNS if cooldown is None else cooldown
    force = force or set()
    xs = [track.sample(i / 24.0)[1] for i in range(n)]

    def side_at(f):
        tx = wanted[f]
        if tx is None:
            return None, 0.0
        dx = tx - xs[f]
        if abs(dx) <= deadzone:
            return None, dx
        return (1 if dx >= 0 else -1), dx

    sign = side_at(0)[0] or (1 if (wanted[0] is None or wanted[0] >= xs[0]) else -1)
    decisions: list[tuple[int, int]] = []      # (frame, new sign)
    pending, run, last = None, 0, -999
    for f in range(n):
        s, dx = side_at(f)
        if s is None:
            pending, run = None, 0
            continue
        if s != pending:
            pending, run = s, 1
        else:
            run += 1
        if s == sign:
            continue
        big = abs(dx) >= urgent
        fire = (big and run >= 3 and (f - last) >= 8) or \
               (run >= confirm and (f - last) >= cooldown)
        if fire and not big:
            # look before turning: if he will want the old side back inside
            # four tenths of a second, this is a twitch, not a turn. Skipping it
            # is what turns three flips at 7.0/7.5/7.9 into one.
            soon = sum(1 for k in range(f, min(n, f + 10))
                       if side_at(k)[0] == sign)
            if soon >= 4:
                fire = False
        if fire or f in force:
            sign = s
            last = f
            decisions.append((f, s))

    out = [0.0] * n
    cur = side_at(0)[0] or (1 if (wanted[0] is None or wanted[0] >= xs[0]) else -1)
    turns = 0
    filled = 0
    for f, s in decisions:
        start = max(filled, f - (turn_frames - 1))
        for k in range(filled, min(n, start)):
            out[k] = float(cur)
        for k in range(start, min(n, start + turn_frames)):
            u = (k - start + 1) / float(turn_frames)
            out[k] = cur + (s - cur) * u
        filled = min(n, start + turn_frames)
        cur = s
        turns += 1
    for k in range(filled, n):
        out[k] = float(cur)
    return out, turns


def drive_facings(scene, t0: float = 0.0, t1: float = 30.2,
                  dt: float = 1.0 / 24.0) -> int:
    """Give every fighter a turn schedule from the geometry of the fight.

    The rule is the one a camera operator would use: the protagonist watches the
    man he is *engaged with* — the beat sheet knows who that is — and every
    rival watches the protagonist. ``build_facing_schedule`` then applies the
    dead band and the cool-down, so a fighter turns a handful of times because
    the fight changed shape, not because two pelvis coordinates crossed.
    """
    hero = scene.get("hero") or scene["tracks"][0]
    tracks = list(scene["tracks"])
    names = {tr.name: tr for tr in tracks}
    n = int(round((t1 - t0) / dt)) + 1
    turns = 0

    swaps = set()
    for b in scene.get("beats", ()):
        if getattr(b, "side_swap", False):
            swaps.add(int(round((b.t - t0) / dt)))

    def wanted_for(tr):
        out = []
        for i in range(n):
            t = t0 + i * dt
            if tr is hero:
                engaged = active_opponent(scene, t)
                if engaged in names and _alive(names[engaged], t):
                    out.append(names[engaged].sample(t)[1])
                    continue
                best = None
                for other in tracks:
                    if other is tr or not _alive(other, t):
                        continue
                    d = abs(other.sample(t)[1] - tr.sample(t)[1])
                    if best is None or d < best[0]:
                        best = (d, other)
                out.append(None if best is None else best[1].sample(t)[1])
            else:
                out.append(hero.sample(t)[1] if _alive(hero, t) else None)
        return out

    for tr in tracks:
        # a rival only has to keep the protagonist in front of him, and he is
        # often standing still while the duel moves: he is allowed to be slower
        # to change his mind than the man who is fighting for his life
        plan, k = build_facing_schedule(tr, wanted_for(tr),
                                        cooldown=(MIN_FRAMES_BETWEEN_TURNS if tr is hero
                                                  else 2 * MIN_FRAMES_BETWEEN_TURNS),
                                        # a rival standing off at the perimeter does
                                        # not re-face every time the duel drifts past
                                        # him: he holds his stance until the hero is
                                        # properly behind his shoulder
                                        deadzone=(TURN_DEADZONE if tr is hero else 90.0),
                                        # the urgent turn is a *fighting* reflex:
                                        # the man in the exchange cannot wait a
                                        # third of a second to turn round. A
                                        # rival sliding along the perimeter can.
                                        urgent=(110.0 if tr is hero else 1e9),
                                        force=swaps if tr is hero else None)
        tr.facing_keys = [(t0 + i * dt, v) for i, v in enumerate(plan)]
        turns += k
    return turns
