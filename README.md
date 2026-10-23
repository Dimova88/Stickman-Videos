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

### Motion rules

* every strike is keyed wind-up → 2–3 frame travel (`snap` easing) → recovery;
* feet stay planted through punches and step with them;
* impact stars are not hand-placed — the code measures which fist is nearest the
  other head at the contact frame and draws the star on that point;
* hits add shake, a short zoom kick and a struck-pose on the receiver;
* audio is synthesised (sub-thump impacts, swept-noise whooshes, a pulse bed) —
  no samples, so nothing to license.

## Status

30-second test #1. Next: longer choreography, more camera moves, and a second
fighter archetype.
