# Stickman Films

Cinematic, anime-inspired stick-figure films — written, scored, rendered and
stored entirely in this repository.

**Chapter 0 · "The Door"** — 30-second teaser (1920×1080, 24 fps, original score)

* 🎬 `renders/eighth_gate_1080p.mp4`
* 📜 Screenplay & 8-minute roadmap: [`docs/screenplay/the_eighth_gate.md`](docs/screenplay/the_eighth_gate.md)
* 🛠 Engine: [`docs/PIPELINE.md`](docs/PIPELINE.md)

## Quick start

```bash
python -m venv .venv
.venv/bin/pip install numpy scipy pillow imageio-ffmpeg aggdraw

# preview stills
.venv/bin/python tools/preview_frames.py scenes/eighth_gate.py --times 9,25.6 --w 960 --contact

# full render (also synthesises the soundtrack)
.venv/bin/python tools/render_film.py scenes/eighth_gate.py --w 1920
```

## What's here

```
pipeline/core/     renderer, camera, rig, effects, sets, audio synthesis, encoder
scenes/            one module per film: shots, camera moves, timing, music cues
docs/              screenplay, engine reference, production notes
tools/             preview + render entry points
assets/fonts/      bundled typeface (Noto Sans, OFL)
renders/           output
```

Everything is generated locally: no third-party footage, music, samples or
stock imagery — which keeps each upload clean for YouTube monetisation.
