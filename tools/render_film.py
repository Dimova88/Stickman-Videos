#!/usr/bin/env python3
"""Render a scene module to MP4 (and its soundtrack).

    python tools/render_film.py scenes/eighth_gate.py --w 1920 --out renders/eighth_gate_1080p.mp4
    python tools/render_film.py scenes/eighth_gate.py --w 640 --audio-only
"""
import argparse, importlib.util, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def load_scene(path):
    spec = importlib.util.spec_from_file_location("scene_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--out", default=None)
    ap.add_argument("--crf", type=int, default=17)
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--audio-only", action="store_true")
    ap.add_argument("--video-only", action="store_true")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--preview-every", type=int, default=0)
    a = ap.parse_args()

    mod = load_scene(a.scene)
    film = mod.build()
    name = Path(a.scene).stem
    if a.w != film.width:
        film.height = int(a.w * film.height / film.width) // 2 * 2
        film.width = a.w
    out = Path(a.out or f"renders/{name}_{film.height}p.mp4")
    wav = Path(f"renders/{name}.wav")

    t0 = time.time()
    if not a.video_only and not a.no_audio:
        print(f"[audio] synthesising {film.duration:.1f}s ...", flush=True)
        mix = mod.soundtrack(film.duration)
        mix.write_wav(wav, peak=0.95, target_rms_db=-16.0)
        print(f"[audio] -> {wav} in {time.time()-t0:.1f}s")

    if a.audio_only:
        return

    if a.no_audio or a.video_only:
        audio_path = None
    else:
        audio_path = str(wav)

    print(f"[video] {film.width}x{film.height} @ {film.fps}fps -> {out}", flush=True)
    t1 = time.time()
    film.render(out, start=a.start, end=a.end, workers=a.workers or None, crf=a.crf,
                audio=audio_path, preview_every=a.preview_every,
                preview_dir=f"renders/tmp/{name}" if a.preview_every else None)
    print(f"[video] done in {(time.time()-t1)/60:.1f} min -> {out}")

if __name__ == "__main__":
    main()
