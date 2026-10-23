# Stickman-Videos

Two stick figures, thirty seconds, one fight. Rendered headless from a
script — no app, no timeline clicking, no stock assets.

**Watch:** [`renders/fight_1080p.mp4`](renders/fight_1080p.mp4) — 1920×1080,
24 fps, 30.0 s, stereo audio.

## What this is

The figures, their proportions, the angle convention and the drawing rules are
taken from **[StykAnimate](https://github.com/filippocalippo/StykAnimate-App)**
(GPL-3.0-or-later) — the same 10-segment Pivot skeleton it ships as its default
"Walker" figure, the same white-filled head with an ink rim, the same round-cap
limbs. The repository is cloned locally into the (git-ignored)
`vendor/stykanimate/` folder for reference.

What is new here is the part the app leaves to the mouse: a headless renderer
with **IK posing by target**. Hands and feet are placed where they should be in
world space, and the solver works out the joint angles, so a punch lands on a
chin instead of near it.

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install numpy scipy pillow aggdraw imageio-ffmpeg

# 30 s film at 1080p (about 80 s on 2 cores)
.venv/bin/python tools/render_fight.py --w 1920 --out renders/fight_1080p.mp4

# stills while iterating
.venv/bin/python tools/render_fight.py --stills 3.05,13.4,28.0 --w 960
```

## How it is built

| File | Role |
| --- | --- |
| `fight/core.py` | StykAnimate figure definition, forward kinematics, two-bone IK, pose tracks, easings |
| `fight/draw.py` | aggdraw renderer: round-cap sticks, flat two-tone backdrop, contact shadows |
| `fight/choreo.py` | the 30 s choreography — pose library, keyed tracks, camera, hit/hurt events |
| `fight/motion.py` | channel animation: spline tracks, footwork simulation, drag/lag, idle layer |
| `fight/film.py` | frame loop, impact stars, whooshes, dust, shake, synthesised audio, MP4 encode |

### The choreography, beat by beat

| time | beat |
| --- | --- |
| 0 – 2 | stand-off, both breathing, camera slowly pushes in |
| 2.7 – 4.6 | red steps in, jab parried, cross slips past |
| 5 – 7.5 | blue's body kick blocked, two quick jabs, both parried |
| 7.8 – 9.2 | blue leaps in with a flying kick, red ducks, blue lands |
| 9.7 – 11.6 | clinch, shove, separation |
| 12 – 14 | red knees, spins a backfist into blue's guard |
| 14.5 – 17.8 | blue sweeps low, red jumps it, blue catches the counter and shoves |
| 18.6 – 22 | circling, then a three-beat exchange |
| 23 – 25.4 | both reload and throw at the same moment — **clash** |
| 26 – 30 | last exchange, both throw a rising blow, freeze, drift apart, fade out |

### Why the motion reads as human (v2)

The first pass animated *poses*: two key poses and a straight blend, which is why
it looked like a puppet. It now animates **channels**, the way a real body is put
together:

* **Feet are simulated, not posed.** Each foot is planted at a spot; when the
  pelvis drifts too far from the stance the far foot swings across in 0.17 s. So
  stepping appears automatically when a fighter advances, retreats or gets
  pushed, and a planted foot never slides.
* **Hip height comes from the stance.** The pelvis sits just inside full leg
  extension over the planted foot (0.985), which is a ~10° knee bend. Earlier
  versions dropped the hips 10–20 units, folded the legs and made a diamond.
* **Knees and elbows are chosen anatomically.** The IK has two solutions; the
  code picks the one whose knee points forward / whose elbow hangs low, instead
  of forcing a bend flag.
* **Drag.** Hands are sampled 1 frame late and the head 2 frames late relative to
  the hips, so fast direction changes whip the head and the hands trail the body.
* **Idle is layered on top.** A 1.15 Hz bounce on the balls of the feet, a slow
  weight shift between the feet and a breath cycle; the hands lag that bounce by
  two frames. Nothing is ever perfectly still.
* **Distance is enforced, not eyeballed.** After the beats are keyed, the pair is
  separated until their heads are at least 150 units apart (baked at 1/20 s so
  the spline cannot dip back through), and every strike target is then resolved
  against the defender's *final* head position with the arm clamped to its real
  reach.
* **Strikes dissolve the pose.** A punch is a hand target plus a root that keeps
  travelling through the contact frame, then recovers; the body never freezes in
  a "punch pose".
* Audio is synthesised (sub-thump impacts, swept-noise whooshes, a pulse bed) —
  no samples, so nothing to license.

## Status

30-second test #1. Next: longer choreography, more camera moves, and a second
fighter archetype.
