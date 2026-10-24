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
    return track.sample(t)[0].get("hip", 999.0) > 60.0


def drive_facings(scene, t0: float = 0.0, t1: float = 30.2,
                  dt: float = 1.0 / 24.0) -> int:
    """Give every fighter a turn schedule from the geometry of the fight.

    The rule is the one a camera operator would use: the protagonist watches the
    man he is *engaged with* — the beat sheet knows who that is — and every
    rival watches the protagonist. Walk the timeline, and whenever that answer
    changes start a three-frame turn.

    The schedule is built in one pass and written straight into each track's
    facing keys instead of being requested beat by beat: an event-driven version
    dropped turns whenever two of them arrived close together, and a dropped
    turn is a fighter facing the wrong way for a second.

    Returns the number of turns written, which is what ``audit_film`` counts.
    """
    hero = scene.get("hero") or scene["tracks"][0]
    tracks = list(scene["tracks"])
    names = {tr.name: tr for tr in tracks}
    lead = FLIP_TIME
    turns = 0

    def target_x(tr, t):
        """Where the man this fighter should be watching is standing."""
        if tr is hero:
            engaged = active_opponent(scene, t)
            if engaged in names and _alive(names[engaged], t):
                return names[engaged].sample(t)[1]
            best = None
            for other in tracks:
                if other is tr or not _alive(other, t):
                    continue
                d = abs(other.sample(t)[1] - tr.sample(t)[1])
                if best is None or d < best[0]:
                    best = (d, other)
            return None if best is None else best[1].sample(t)[1]
        if not _alive(hero, t):
            return None
        return hero.sample(t)[1]

    for tr in tracks:
        keys: list[tuple[float, float]] = [(t0, float(tr.facing_at(t0)))]
        cur = float(tr.facing_at(t0))
        last_turn = -99.0
        t = t0
        while t <= t1:
            tx = tr.sample(t)[1]
            look = min(t1, t + lead)
            ox = target_x(tr, look)
            if ox is not None and abs(ox - tx) > DEADBAND:
                want = 1.0 if ox > tx else -1.0
                # if the man he is *trading with* has changed sides, there is
                # nothing to deliberate about: turning his back on the attack
                # for a quarter of a second is the exact defect this exists for
                engaged_now = tr is hero and active_opponent(scene, look) is not None
                settled = engaged_now or (t - last_turn) > HOLD_TIME
                # the other side has to *stay* the other side: in a juggle the
                # bodies cross two or three times in half a second, and a turn
                # on each crossing is a head on a swivel
                persists = all(
                    (((target_x(tr, min(t1, t + FLIP_TIME + k * dt)) or tx) > tx)
                     == (want > 0))
                    for k in (1, 2)
                )
                if want != math.copysign(1.0, cur) and settled and (persists or engaged_now):
                    # the ramp starts one frame early, so that no rendered frame
                    # is still fully turned the old way when the turn begins
                    keys.append((max(t0, t - dt), cur))
                    cur = want
                    keys.append((t + FLIP_TIME - dt, cur))
                    turns += 1
                    last_turn = t
                    t += FLIP_TIME + HOLD_TIME * 0.5
                    continue
            t += dt
        tr.facing_keys = sorted(keys)
    return turns
