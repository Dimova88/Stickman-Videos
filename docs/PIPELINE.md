# The Stickman Films pipeline

A from-scratch, fully offline 2D cinematic renderer + procedural soundtrack
generator, built so a stick-figure film can look and sound like a short anime
film — and so every frame, note and pixel is original and safe to monetise.

```
scenes/<film>.py         the film: shots, cameras, poses, effects, music cues
   ↓
pipeline/core/           the engine (render, camera, rig, fx, sets, audio, encode)
   ↓
renders/<film>_1080p.mp4 + renders/<film>.wav
```

## Why an engine instead of the app?

[StykAnimate](https://app.stykanimate.com/) (open source, GPL) is where the
**animation** happens: the poses, timing and camera of a shot are authored and
exported there — or authored directly in `scenes/*.py` with the same keyframe
model. The engine then does what the app does not do:

| Need | StykAnimate | this pipeline |
| --- | --- | --- |
| Shooting a camera move | ✅ keyed camera | ✅ keyed camera + shake/punch/whip |
| Anime rim light + silhouette | per-object effects | ✅ lighting model per light direction |
| Motion smears / afterimages | manual | ✅ solved from consecutive poses |
| HDR post (bloom, CA, anamorphic streak) | 17 effects | ✅ floating-point HDR + tone map |
| Impact frames (inverted polarity) | ❌ | ✅ `Post.invert` |
| Original score + sound design | import only | ✅ synthesised, no samples |
| Batch / resumable / parallel render | — | ✅ PNG-seq renderer + x264 |

## Current status (1.2.5) and what is missing for film work

Investigated from the app itself and from its source
(`github.com/filippocalippo/StykAnimate-App`):

* **Export is video-only** ("Video is currently silent") — sound has to be
  muxed afterwards. This pipeline muxes AAC 320k automatically.
* **No motion blur, no depth of field, no impact/inverted frames**, no
  per-shot grade — all supplied here in `Post`.
* **Effects are per-object or per-scene, not HDR.** Glows clamp at white and
  bloom is threshold-based in LDR, so stacked effects lose colour. The engine
  renders in float and tone-maps at the end (`Post.tone_k`).
* **Camera has no noise/handheld layer**, only fixed shake presets — this engine
  adds a continuous value-noise handheld layer plus decaying impulse shake.
* **Fills use flat colours per object**; the engine adds gradient polygons,
  soft blobs, mist bands and procedurally generated sky/ground plates so
  silhouettes read against something.

Practical conclusion: **author animation in StykAnimate**, then either export
PNG sequences into `renders/frames/` (the encoder can take them) or re-author
the shot in a scene module where full control is needed.

## Engine map

| Module | Responsibility |
| --- | --- |
| `pipeline/core/easing.py` | easings, keyed `Track`, value noise, shake impulses |
| `pipeline/core/camera.py` | camera track (x/y/zoom/roll), parallax, projection, image plates |
| `pipeline/core/character.py` | FK rig, 30-pose library, line-art + rim-light painter, smears |
| `pipeline/core/fx.py` | particles, embers, impacts, shockwaves, speed lines, god rays, rain, lightning |
| `pipeline/core/sets.py` | sky, moon, clouds, mountain ridges, ground, torii, lanterns, stairs, bamboo, skyline |
| `pipeline/core/render.py` | AA vector canvas, HDR post (bloom/streak/CA/tonemap/grain/letterbox) |
| `pipeline/core/film.py` | `Shot`/`Film`, transitions, parallel PNG-sequence render, resume |
| `pipeline/core/audio.py` | synthesis (boom, taiko, braam, riser, whoosh, slash, pad, choir…) |
| `pipeline/core/encode.py` | x264 H.264 MP4 writer, muxing, probe |

## Render

```bash
python -m venv .venv && .venv/bin/pip install numpy scipy pillow imageio-ffmpeg aggdraw

# stills while iterating (fast)
.venv/bin/python tools/preview_frames.py scenes/eighth_gate.py --times 3,9,25.6 --w 960 --contact

# audio only
.venv/bin/python tools/render_film.py scenes/eighth_gate.py --audio-only

# final
.venv/bin/python tools/render_film.py scenes/eighth_gate.py --w 1920 --out renders/eighth_gate_1080p.mp4
```

Frames are written as PNGs and encoded afterwards, so a crash costs one frame
and `resume=True` skips the ones already on disk. 4K is the same command with
`--w 3840`.

## Shot language used in the teaser

`docs/screenplay/the_eighth_gate.md` holds the screenplay; the film modules read
like a shot list:

* **Establish** — wide, slow push-in, tiny figure for scale.
* **Low angle** — camera below the ground line, verticals converging.
* **Macro** — 3–5× zoom on a foot/eye; the world becomes texture.
* **Whip pan** — 0.2 s of `whip_in` motion blur between shots.
* **Impact** — flash + shockwave + speed lines + 2 inverted frames + shake.
* **Settle** — camera drifts back to stillness while embers fall.

## Audio design

Everything is synthesised at 48 kHz from oscillators and filtered noise:

* hits: `boom` (pitch-swept sub), `taiko`, `braam` (detuned saw stack)
* movement: `whoosh` (swept band-pass noise), `slash` (metallic transient)
* tension: `riser`, `heart`, `choir`, `pad`
* space: convolution with a synthetic noise IR (`Mix.reverb`)

The bus is driven into a tanh limiter to a solved target loudness
(-16 LUFS-like RMS, peaks 0.95), which is what makes the beds sit under the
hits the way a trailer mix does.
