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

## The Clash: how the 30 s test is built

The reference process, reimplemented end to end. The fight is location-agnostic:
one choreography, one HUD, and a painted plate plus three title lines per set.

| set | plate | title / subtitle / HUD |
| --- | --- | --- |
| `mountain` | `assets/mountain_background.png` | MOUNTAIN CLASH / VICTORY ON THE SUMMIT / MOUNTAIN • ROUND 1 |
| `desert` | `assets/desert_background.png` | DESERT CLASH / VICTORY IN THE DUNES / DESERT • ROUND 1 |

```
python tools/render_clash.py --out renders/mountain_clash_720p.mp4
python tools/render_clash.py --set desert --out renders/desert_clash_720p.mp4
```

1. **Background.** One 1376×768 painted plate per set is scaled to 1320×742, and the
   push-in is pre-scaled once into 65 plates (one per zoom step, vignette baked
   in); each frame is then an integer crop of one — or a blend of the two
   neighbouring — plates, offset by a slow camera drift plus the impact shake.
   The landscape never moves in 3D — only the crop does.
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
   impacts get a white flash, a radial star, decaying sparks and seeded
   particles (fixed seeds, so renders are reproducible). Deliberately **no
   expanding ring and no outlined dots**: a coloured hoop crossing a fighter
   reads as a circle stuck to its body, and the request was to keep the body
   clean. 11 dust events throw 14 particles per landing and sweep.
7. **HUD.** Health bars (damage eased over 0.32 s), a timer, MOUNTAIN CLASH /
   RED VS BLUE / FIGHT! / DOWN! / K.O. / BLUE WINS / VICTORY ON THE SUMMIT,
   MOUNTAIN • ROUND 1, thin cinematic bars and fades.
8. **Sound.** Fully synthesised at 44.1 kHz stereo, mixed in three layers so the
   hits cut through:
   * **hits** are built from the four parts a punch has — `body` (a
     pitch-dropping thump, 70–150 Hz), `smack` (a 40 ms band-passed burst at
     700–4200 Hz, the *pak* that makes it read as a fist rather than a door),
     `flesh` (a longer noise tail) and `ring` (bone on bone, blocks and clashes
     only). Every blow has its own noise seed, so the 29 hits are not clones.
     Body shots sit at 82 Hz and are darker, the finisher at 68 Hz with a 1 s
     tail;
   * **the bed** (low pulse, kick on the half-second, snare on the off-beats,
     hats on the sixteenths) is side-chained: every impact ducks it ~8 dB for a
     moment, which is what makes a punch audible instead of buried;
   * **movement** adds a swish before each strike, plus the sweeps.

   Constant-power panning by screen position, and a C–E–G–C major rise after the
   win. Measured on the finished file: peak 0.95, RMS 0.12, and a 2–5x energy
   jump at every one of the 29 impacts.
9. **Encode.** The clip is cut into one contiguous segment per worker; each
   worker draws *and* encodes its own segment (frames never cross a process
   pipe) with libx264 `veryfast` / CRF 16 / `-tune animation`, yuv420p. The
   segments are concatenated with `-c copy`, then the WAV is muxed in as
   192 kbps AAC with `+faststart`. `--preset/--crf/--tune` override the
   defaults.

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

### Performance

The 30 s test renders in **15–17 s on 2 vCPU**, down from 47–51 s, with the
picture verified against the previous master rather than assumed:

| stage | before | after | how |
| --- | --- | --- | --- |
| one frame | 37.8 ms | 9.1 ms | background plates, bounding-box compositing, cached health curve |
| 720 frames, 1 core | 27 s | 6.5 s | |
| encode (720p) | 24.3 s | 10.5 s | `veryfast` + CRF 16 + `-tune animation` |
| whole render, 2 cores | 47–51 s | 15–17 s | one render+encode process per core, no per-frame IPC |

What was actually hot, and what changed:

* **Background, 14.7 ms → 0.6 ms.** A 1280×720 bilinear resample per frame for
  the push-in was 11 ms of it; a full-frame `AFFINE` was *worse* (24.7 ms). So
  the zoom is baked into a ladder of plates at startup (65 × 1320×742 px,
  ~0.7 s, 190 MB) and a frame crops a window out of two neighbours and blends
  them. The vignette is baked into the plates too — the camera can drag it by
  at most the 20×11 px pan margin, which moves the alpha by ~2/255.
* **Compositing, 8.3 ms → 0.5 ms** per translucent batch. Shadows and dust used
  to be a full-frame RGBA layer each; they now share one overlay cropped to the
  bounding box of what is drawn, and the finished crop *becomes* the frame
  instead of being pasted into a fresh canvas.
* **Health bars, 1.1 ms → ~0.** The two bars re-integrated the damage curve from
  t=0 at 120 Hz twice per frame; the integrator now keeps its state between
  calls, with bit-identical results.
* **Encode.** At equal quality `veryfast`/CRF 16/`-tune animation` measures the
  same PSNR as `slow`/CRF 18 (36.92 vs 36.93 dB on a 240-frame lossless
  reference) in a third of the time, for 17 % more bytes (2.72 vs 2.32 MB per
  10 s — irrelevant at this length).
* **Pipeline.** Frames are no longer pickled through the parent: each worker
  owns a segment and an encoder. The 2 s soundtrack is synthesised in its own
  process while the frames are drawn instead of afterwards.

Quality, measured:

* Reference frames against the pre-refactor renderer: mean |Δ| 0.6–2.2/255,
  p99 ≤ 28, and only where a sharp edge in the *photographic* background lands
  on a different sub-pixel sampling phase. On the fighters and the HUD —
  everything that is drawn, not resampled — the maximum difference is 16 levels,
  on antialiased fringes.
* Sharpness: edge energy of the finished frame is 1.3 % below the old render,
  i.e. under a quarter of a pixel of softening (a 0.3 px Gaussian measures
  −1.1 %). Dropping the blend between plate levels would recover it but make the
  push-in step once a second, which is the worse trade.
* Finished 30 s master against the previous one: **PSNR 39.3 dB, SSIM 0.980**
  (chroma 48 dB), and the soundtrack is identical — peak and RMS match to three
  decimals. The join between the two encoded segments (frame 360) sits inside
  the normal frame-to-frame spread, so there is no seam.

The same run now also fixes previews: `--w 960/640` used to show an upper-left
crop of the 1280 background with the HUD type unchanged, so the storyboard had
its title and health bars running off the frame. Frames are now always composed
at 1280×720 and the finished frame is resampled, which makes a small size an
exact preview of the master (`--w 960` differs from the downscaled master by 0
levels) rather than a second layout.

### Anatomy, rig and deformation

A clean stickman was what made the fight *readable*; it is not what makes it
cinematic. Four changes close the gap with the hand-drawn reference — and they
live entirely in the painting of the skeleton, so the IK, the pose table and the
choreography are untouched and the motion is exactly the motion that was tuned
before.

| | what it is | where |
| --- | --- | --- |
| **articulated spine** | the back is never a straight line. `Pose.spine` bows the trunk through a curve from hip to neck — negative to load a punch and dodge, positive to drive an uppercut, deeply negative for a body shot — and the shoulders ride the tangent so the upper body rotates with it | `core.Pose`, `core.solve` |
| **feet, hands, thickness** | a foot is a wedge with a heel and a toe, hinged at the ankle, planted flat when the sole is down and pointed when the foot leaves the floor; a fist is a knuckled knob at the end of the forearm, an open hand carries four fingers; arms, forearms, thighs, shins and spine all taper | `clashfilm._foot`, `_hand`, `_tube` |
| **a face** | a jaw pushed toward the facing direction, a nose notch in profile, and a dark eye socket with a lit amber iris under a brow that slants down toward the nose. The iris blooms with limb speed, the brow steepens with the spine — so anger and pain are geometry, not a new asset | `clashfilm._head` |
| **squash, stretch, smear** | limb tips stretch along their own velocity, the joints behind them drag the other way, and a fast limb sweeps a tinted fan between where it was and where it is. Under ~300 units/s nothing moves; at 1150 the arm is visibly longer | `clashfilm.draw_fighter`, `trails` |

Two rules keep that rig honest, and both were learned the hard way:

* The floor test is `pose.lift_*` — how far the foot anchor sits *above* its
  resting height — never the ankle's distance to `GROUND`: posed feet stand
  30–40 units above the ground line, so an ankle test calls every foot planted.
* A foot facing left is **mirrored**, never rotated by π: the rotation flips it
  upside down, which is exactly what blue's raised foot did for one build.

Per-pose tuning (spine bow, toe pitch, grip) lives in one `_TUNE` table that is
applied to the pose globals themselves, so `PS.GUARD` and `LIBRARY["guard"]`
cannot drift apart.

Cost and verification: 9.1 → **10.4 ms** per frame on the mountain set (10.0 on
the desert) and a full 30 s render of **15.2 s** — the anatomy costs about a
millisecond a frame and nothing else. Against the previous master the finished
film measures
**SSIM 0.996**, the sky 44 dB — the background survived the animation change
untouched — and 32.4 dB overall, which is the fighters: every one of those
levels is the new anatomy, not an artefact.

### One piece: limbs, feet and hands

The first anatomy pass had a flaw you could see at a glance: the arm and its
fist, the leg and its foot, were drawn as two shapes that merely *met* at the
joint. The thin end of one landed against the wide end of the other and left a
notch — a seam where a body should be continuous.

A limb is now a single swept polygon (`_limb`): down one side of the joint
chain, around the hand or the foot, and back up the other side. The fist is the
cap of the arm, the foot is the cap of the leg, and the last width of the chain
is the first width of the cap, so there is nothing to seam.

The feet were also hovering. The IK could not reach the ground line — the leg
segments are shorter than the hip height the poses are authored against — so
every planted foot floated ~30 units above its own shadow. A planted foot now
puts its **sole** on the floor line, whatever the IK left, and the shin is
carried down to meet it. It is the silhouette that reads as standing, not the
joint position.

| before | after |
| --- | --- |
| arm + fist as two shapes, notch at the wrist | one polygon, fist is the arm's cap |
| leg + foot as two shapes, notch at the ankle | one polygon, foot is the leg's cap |
| sole wherever the IK put the ankle | sole on the floor line when planted |
| splayed claw for every hand | fist when the pose grips, open hand otherwise |
| smear fan from the hip | fan from the knee or elbow, and none near the floor |

### The close-up register

A stickman reads a fight at a distance; a body blow at full speed does not. So
the film cuts — **on the exact frame the blow lands**, not near it — and for half
a second the simple figure is gone: a face, or on the finisher the skull
(`fight/insert.py`).

| cut | at | what it shows |
| --- | --- | --- |
| face | 13.44 s | red at the fist clash, jaw clenched, teeth bared |
| face | 18.40 s | blue takes red's aerial kick on the head: eyes wide, mouth open, sweat thrown off |
| X-ray | 24.72 s | red eats the finisher: skull in bone, the crack opening, a red bloom at the point of impact |

The cut begins on the impact frame itself, so the blow and the close-up are the
same instant. Everything inside it is in slow motion: the head is thrown to full
recoil on the first frame, **holds** there while the camera pushes in, and only
then settles. The music ducks away entirely under the hold, so the hit is the
only thing left in the room.

The face is built from proportions, not detail: eyes on the vertical centre one
eye apart, tall almonds with a heavy upper lash, amber iris with a dark rim,
brows riding down toward the nose, mouth low, chin tapered, jaw shadow on the
neck. The first version shaded the head with soft polygons and read as an
amorphous blob; there is now exactly one shadow plane and it is under the jaw.

The X-ray draws the same head as bone — cranium, orbits, nasal aperture,
zygomatic arch, a row of teeth, a mandible hung under the maxilla, cervical
bodies running off the bottom of the frame — and a hairline crack that opens from
the point of impact.

**The sound.** A close-up gets its own blow (`critical_hit`): a sub that drops an
octave, the crack of first contact, and a bone ring that hangs while the picture
holds. Measured on the finished mix, the three close-ups sit ~6 dB (face) and
~9 dB (X-ray) above an ordinary landed punch, and the music is 70 % down under
each of them.

### The blow has weight: hitstop, compression, anticipation (*fight/impact.py*)

A hit is not a fast movement, it is a *stopped* movement. Three timing layers do
that on top of the existing `time · x · pose` timeline, without re-keying it:

**Hitstop — a clock, not a keyframe.** `Clock` is a piecewise map from real time
to animation time: for every contact it runs at **0** for 2–4 frames, then at
**2x** for the same number of frames. The integral of that window is exactly the
window's length, so after two holds' worth of frames the map is the identity
again — every later key, cut, title and sound stays exactly where it was
authored, and the film is still 30.00 s. Frames held: 1 for a block, 2 for a
landed hit (3 when the hit is a full-strength one), 2 for a clash, 4 for the
finisher. Measured on the master, the three frames around the 10.94 s kick
differ by 0.2 / 255 on average (only the impact star develops) while the frame
before and after it differ by 20 and 9.

The whole painted world rides that clock — bodies, contact shadow, smear,
dust, the landscape crop and the camera shake — so the instant of contact is
one held frame. The impact flash and the HUD stay on the real clock, so the
world freezes while the blow rings out.

**Compression — a pose delta, not a second pose.** At the frozen instant the
fighter being hit is folded around the fist: `compress(pose, k)` drops the hips
17 units, caves the spine 11°, pulls the head 7° over the back shoulder and
drives the guard 12° into the chest, then shoves the body 13 px away from the
blow. It rises over the last 2.5 frames before contact and decays over 0.17 s
after, so it is already full on the frame the world freezes on. Because it is a
delta on top of whatever pose the choreography had, it works for every one of
the nine landed blows plus the clash, with no authoring.

**Anticipation — the loaded key.** Every landed blow already had a key ~0.26 s
before it, holding a guard. `add_anticipation` finds that key (never moving it,
only changing its pose) and coils the limb that is about to strike, chosen from
the contact pose itself: a punch pulls the elbow back and loads the fist at the
shoulder, a kick chambers the knee with the heel under the hip; in both cases
the weight drops 6 units and the body turns 5° away. Ten landed blows plus the
two clashes re-pose a key on each side, 20 keys in all, and the wind-up adds no
time to the beat: it only makes the frame that was already there read as a
load. Because it happens before the spacing and reach
solvers run, the gap between the pair is still solved against the coiled pose.

### The knockdown: it flies, bounces, skids, and climbs back up (*fight/ragdoll.py*)

The old fall was three keys — hit, `FALL`, `DOWN` — so a fighter was rotated flat
and then stood back up in guard. There are five knockdowns in the fight and each
one is now a short arc of seven beats plus a rise:

| | what happens |
| --- | --- |
| +0.05 s | the feet leave the floor, body already tipping (`LAUNCH`) |
| +0.13 s | airborne, turning over, limbs trailing (`FLIGHT`) |
| +0.21 s | first landing, hips to 27 units, **three dust puffs** (`SLAM`) |
| +0.27 s | it bounces 15 units back up (`BOUNCE`) |
| +0.33 s | second landing, two more puffs |
| +0.40 → 0.52 s | the skid runs out, it settles flat (`SPRAWL`) |
| then | roll, hands and knees, **the arms give out once**, push up, sway onto the feet, spent |

Two details make it read as weight rather than as a pose change. The contact
shadow is derived from the feet, so an airborne pose floats its shadow for free.
And getting up is not a single interpolation: `ROLL → ALL_FOURS → GIVE →
ALL_FOURS → PUSHUP → STAGGER → SPENT` is seven keys over ~1.1 s, with the chest
dropping back to the floor on the `GIVE` beat, which is what a hurt body does.

**Where it lands is solved, not keyed.** The throw is a distance, but the spacing
solvers move the contact position, so the flight keys are placed *after* them
(`reanchor`): the body lands `throw` pixels from where the blow actually landed,
and the get-up walks back from there to wherever the next key of the choreography
is — with a small sway so the rise does not read as a slide. While a fighter is
down, the gap solvers only push the one still standing, so a thrown body never
gets nudged sideways while it is lying still (that was the first version, and it
looked like the floor was a conveyor belt).

Only the body's *times* are authored. Everything about the horizontal path is a
consequence of the blow, which is why four knockdowns and the finisher all have
the same weight and only their power differs (34 / 32 / 30 / 36 px, and 55 px for
the knockout).

### A second set: the desert

The same fight re-staged on a new plate (`--set desert`), with its own title
card. Nothing in the renderer is mountain-specific — the plate, the pan range
and the zoom range are all derived from the scene.

| | mountain | desert |
| --- | --- | --- |
| frame (720p, one core) | 10.4 ms | 10.0 ms |
| full render, 2 cores | 15.2 s | **15.6 s** |
| encode, same settings | 10.0 s | 10.4 s |
| master size | 9.28 MB | 12.39 MB |
| per-frame PSNR vs lossless source | median 47.9 dB | median 46.9 dB |
| SSIM vs lossless source | 0.981 | 0.976 |
| soundtrack | — | bit-identical to the mountain master |

The desert plate carries more fine detail (sand grain, rock strata, stars), so
the same CRF spends 30 % more bits and lands ~1 dB lower — that is the content,
not the pipeline: dropping to CRF 14 on the desert buys +0.05 dB for +33 % bytes,
so the setting stays put. Both are ~2.4–3.2 Mbps at 720p.

## Status

30-second tests: the clean 1080p fight, then the Clash on two sets — mountain
and desert — with the full HUD and soundtrack, both rendered in ~16 s, and the
figures carrying a bowed spine, articulated feet and hands, a face and speed
deformation, three close-up inserts on the heaviest impacts (one of them an
X-ray of the skull), hitstop and compression on every contact, a coiled wind-up
before every landed blow, and knockdowns that fly, bounce, skid and climb back
up. Next: footwork (real steps instead of pivots), then the one-minute version
with chained choreography, weapons and a 1-vs-many round.
