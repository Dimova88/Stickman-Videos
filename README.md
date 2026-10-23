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
with a **written pose library**. Every stance, punch, block, kick and stumble is
authored once as a small set of body angles, the leg solver turns a foot position
into hip/knee/ankle angles, and the fight is those poses keyed over time.

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
| `fight/poses.py` | the pose library: 25 poses (guard, jab, cross, hook, uppercut, kicks, knee, clinch, hit reactions, airborne, tired) |
| `fight/choreo.py` | the 30 s fight — pose keys + root path per fighter, spacing rules, camera, hit/hurt events |
| `fight/film.py` | frame loop, impact stars, speed streaks, dust, shake, synthesised audio, MP4 encode |
| `tools/pose_sheet.py` | renders the whole pose library to one contact sheet — the tool used to check anatomy |

### The choreography, beat by beat

| time | beat |
| --- | --- |
| 0 – 2.2 | stand-off, both settle into guard, camera creeps in |
| 2.5 – 4.4 | red's jab is blocked, red's cross slips past blue's head |
| 4.6 – 7.0 | blue's body kick lands on red's block, then two quick jabs |
| 7.3 – 9.0 | blue's hook over the top, red ducks under it and lands an uppercut |
| 9.3 – 10.9 | clinch, chest to chest, then shoved apart |
| 11.2 – 12.8 | red's knee, red's hook into blue's guard |
| 13.2 – 16.2 | blue sweeps low, red jumps it, blue's head kick is ducked, red counters |
| 16.2 – 18.4 | circling |
| 18.4 – 21.4 | exchange: jab/counter jab, then a fast 1-2 |
| 21.4 – 23.4 | both reload, settle, breathe |
| 23.4 – 25.0 | both throw a cross at the same instant — **fists clash**, both snap back |
| 25.4 – 27.6 | last exchange, both land a rising blow together |
| 27.8 – 30.0 | both step back, breathe, fade to black |

### Why the motion reads as human (v3)

The second pass tried to animate *channels* — a hand target per fighter plus a
footwork simulation. It still looked wrong, because a hand target says nothing
about where the elbow or the knee is, and the two-bone solver was free to choose
a sideways knee or a forearm folded into the face.

The current version authors **body angles, not targets**:

* **Feet are given as ground-relative offsets** (±30–34 units fore/aft, plus a
  height for kicks). A two-bone solve with a *forced forward knee* turns each
  offset into thigh and shin angles, so a stance always bends the way a stance
  bends instead of splaying into a diamond.
* **Hip height comes from the planted foot**, capped at 94 % of full leg
  extension. That guarantees a visible knee bend without letting the pelvis
  sink. A lifted foot never carries the hips.
* **Arms are authored as upper-arm and forearm angles**, clamped to 96 % of the
  arm's reach. A guard is upper arm ~50°, forearm ~-72°: the fist sits at chin
  height *in front of* the face, not inside it.
* **The head is a segment, not a dot.** Its angle follows the spine, so it sits
  on the neck. This was the single biggest bug in the rejected version: the head
  circle was drawn one head-radius *forward* of the neck, so every guard read as
  "fists in the face".
* **Kicks extend.** A planted leg is solved at 94 % extension, a kicking leg at
  99.5 % with the foot target 90–110 units from the hip — that is the difference
  between a kick and a folded leg.
* **Spacing is enforced, not eyeballed.** The pair is relaxed apart on a 1/10 s
  grid until the two heads are at least ~176 units apart (~138 in the clinch),
  with the attacker stepping in for each kick.
* **Impacts are anchored to the body**, not to empty air: the star is placed on
  the head or torso the nearest limb is attacking, and on the meeting point of
  the fists for the two clashes.
* Audio is synthesised (sub-thump impacts, swept-noise whooshes, a pulse bed) —
  no samples, so nothing to license.

## Status

30-second test, third pass on the motion. Next: longer choreography, more
camera moves, and a second fighter archetype.
