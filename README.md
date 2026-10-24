# Stickman-Videos

Two stick figures, one mountain summit, one fight. Rendered headless from a
script — no editor, no timeline clicking, no stock assets.

**Watch:**

| file | what it is |
| --- | --- |
| [`renders/mountain_clash_720p.mp4`](renders/mountain_clash_720p.mp4) | **Mountains Clash**, 30 s test: 1280×720, 24 fps, HUD, procedural soundtrack |
| [`renders/storyboard.jpg`](renders/storyboard.jpg) | 12-moment storyboard of the same fight |
| [`renders/fight_1080p.mp4`](renders/fight_1080p.mp4) | the earlier clean-background 1080p fight (no HUD) |


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
.venv/bin/pip install numpy pillow aggdraw imageio-ffmpeg

# Mountains Clash, 30 s, 1280x720 (about 47 s on 2 cores)
.venv/bin/python tools/render_clash.py --w 1280 --out renders/mountain_clash_720p.mp4

# 12-moment storyboard, and a fast low-res slice while iterating
.venv/bin/python tools/render_clash.py --storyboard 12 --w 960
.venv/bin/python tools/render_clash.py --w 640 --start 18 --end 24 --out /tmp/slice.mp4

# the earlier clean-background fight at 1080p (about 85 s)
.venv/bin/python tools/render_fight.py --w 1920 --out renders/fight_1080p.mp4
```

## How it is built

| File | Role |
| --- | --- |
| `fight/core.py` | StykAnimate figure definition, forward kinematics, two-bone IK, pose tracks, easings |
| `fight/draw.py` | aggdraw renderer: round-cap sticks, flat two-tone backdrop, contact shadows |
| `fight/poses.py` | the pose library: 25 poses (guard, jab, cross, hook, uppercut, kicks, knee, clinch, hit reactions, airborne, tired) |
| `fight/choreo.py` | the 30 s fight — pose keys + root path per fighter, spacing rules, camera, hit/hurt events |
| `fight/film.py` | frame loop, impact stars, speed streaks, dust, shake, synthesised audio, MP4 encode |
| `fight/clash.py` | **Mountains Clash** choreography: keyed poses + 29 impacts + camera + on-screen text |
| `fight/clashfilm.py` | the Mountains Clash renderer: landscape crop, trails, impacts, dust, HUD, procedural audio, FFmpeg pipe |
| `tools/pose_sheet.py` | renders the whole pose library to one contact sheet — the tool used to check anatomy |
| `assets/mountain_background.png` | 1376×768 painted mountain arena (generated for this project, no third-party art) |

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

## Mountains Clash: how the 30 s test is built

The reference process, reimplemented end to end:

1. **Background.** One 1376×768 painted plate is scaled to 1320×742; each frame
   crops a 1280×720 window from it, offset by a slow camera drift plus the
   impact shake, and a soft vertical/radial vignette is laid over the top. The
   landscape never moves in 3D — only the crop does.
2. **Figures.** The 10-segment Pivot skeleton from StykAnimate, drawn as flat
   coloured silhouettes: no outline, no joint circles (each limb is a tapered
   capsule and the joint discs match the bone width, so a knee or an elbow is
   just a bend in a smooth tube), a solid head in the fighter's colour, and a
   contact shadow that widens and fades while the fighter is airborne. The rig is stretched to the reference stickman's
   proportions (`ARM_K 1.24`, `LEG_K 1.10`, `HEAD_K 1.42`) so the head reads as
   a head and an extended punch fills the gap between the two fighters.
3. **Mirroring.** A pose is always solved in a canonical right-facing frame and
   the finished body is reflected once about the hips for the left-facing
   fighter. Reflecting the *solved* figure (not the input angles twice) is what
   keeps blue's guard, punches and kicks aimed at its opponent.
4. **Keyframes.** Red faces right, blue faces left; every pose is mirrored for
   blue. A key is `time · x · pose`, interpolated with smoothstep
   (`u²·(3−2u)`) on the root, the height and every joint.
5. **Impacts.** 29 entries, each with instant, screen position, colour, type
   (`block` / `hit` / `clash` / `final`), intensity and damage. That one list
   drives body reactions, stars, rings, particles, sparks, camera shake, health
   bars and the soundtrack — nothing is hand-placed twice.
6. **Effects.** Trails compare each hand and foot with where it was 0.075 s ago;
   impacts get a white flash, an expanding ring, a radial star, decaying sparks
   and seeded particles (fixed seeds, so renders are reproducible); 11 dust
   events throw 12+ particles per landing and sweep.
7. **HUD.** Health bars (damage eased over 0.32 s), a timer, MOUNTAIN CLASH /
   RED VS BLUE / FIGHT! / DOWN! / K.O. / BLUE WINS / VICTORY ON THE SUMMIT,
   MOUNTAIN • ROUND 1, thin cinematic bars and fades.
8. **Sound.** Fully synthesised at 44.1 kHz stereo, mixed in three layers so the
   hits cut through:
   * **hits** are built from their parts — a pitch-dropping body tone (40–130 Hz),
     a band-passed noise burst for the slap of skin (320–2600 Hz), a 6 ms tick
     that carries the transient on phone speakers, and a short ring for blocks
     and clashes. Body shots sit lower and longer, the finisher lower and longer
     still;
   * **the bed** (low pulse, kick on the half-second, snare on the off-beats,
     hats on the sixteenths) is side-chained: every impact ducks it ~8 dB for a
     moment, which is what makes a punch audible instead of buried;
   * **movement** adds a swish before each strike, plus the sweeps.

   Constant-power panning by screen position, and a C–E–G–C major rise after the
   win. Measured on the finished file: peak 0.95, RMS 0.12, and a 2–5x energy
   jump at every one of the 29 impacts.
9. **Encode.** 720 frames go straight into FFmpeg as raw RGB (no PNG dump),
   libx264 CRF 18 yuv420p, then the WAV is muxed in as 192 kbps AAC with
   `+faststart`.

### Beat sheet

| time | beat |
| --- | --- |
| 0–2.4 | title, both step in, FIGHT! |
| 2.6–5.0 | red jabs and crosses, blue slips and counters with a jab-cross that lands |
| 5.0–7.6 | blue's body kick is blocked, high kick slips past, red sweeps, blue jumps it |
| 7.6–9.6 | red's uppercut drops blue — DOWN! — blue gets up |
| 9.6–12.4 | blue's jab-cross, then a flying kick that puts red on the floor |
| 12.5–16.4 | exchange, fists clash, blue's high kick and sweep, uppercut drops red again |
| 16.8–19.6 | red's comeback: cross, high kick, aerial kick — blue goes down |
| 20.2–23.4 | both up, second clash, blue's jab-cross-kick sequence |
| 23.4–25.4 | blue's aerial kick and the finishing uppercut — K.O. |
| 25.4–30 | blue's victory pose, BLUE WINS, fade to black |

## Status

30-second tests, two of them: the clean 1080p fight, and Mountains Clash on the
landscape set with the full HUD and soundtrack. Next: the one-minute version
with the same pipeline, then longer choreography and more camera angles.
