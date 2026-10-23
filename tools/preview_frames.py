#!/usr/bin/env python3
"""Render still frames from a scene for fast visual iteration.

    python tools/preview_frames.py scenes/eighth_gate.py --times 1,4,8 --w 960
"""
import argparse, importlib.util, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image

def load_scene(path: str):
    spec = importlib.util.spec_from_file_location("scene_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene")
    ap.add_argument("--times", default="")
    ap.add_argument("--w", type=int, default=960)
    ap.add_argument("--out", default="renders/preview")
    ap.add_argument("--contact", action="store_true", help="also build a contact sheet")
    a = ap.parse_args()
    mod = load_scene(a.scene)
    film = mod.build()
    h = int(a.w * film.height / film.width) // 2 * 2
    film.width, film.height = a.w, h
    times = [float(x) for x in a.times.split(",")] if a.times else \
        [round(i * film.duration / 12, 2) for i in range(12)]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    frames = []
    for t in times:
        idx = int(round(t * film.fps))
        t0 = time.time()
        fr = film.render_frame(idx)
        print(f"t={t:6.2f}  {time.time()-t0:5.2f}s")
        p = out / f"t{t:06.2f}.jpg"
        Image.fromarray(fr).save(p, quality=92)
        frames.append(p)
    if a.contact:
        cols = 3
        rows = (len(frames) + cols - 1) // cols
        sheet = Image.new("RGB", (a.w * cols, h * rows))
        for i, p in enumerate(frames):
            sheet.paste(Image.open(p), ((i % cols) * a.w, (i // cols) * h))
        sheet.save(out / "contact.jpg", quality=90)
        print("contact:", out / "contact.jpg")

if __name__ == "__main__":
    main()
