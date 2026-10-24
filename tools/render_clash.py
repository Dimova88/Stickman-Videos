"""Render the 30 s Mountains Clash test.

    python tools/render_clash.py --w 1280 --out renders/mountain_clash_720p.mp4
    python tools/render_clash.py --storyboard 12
    python tools/render_clash.py --w 640 --start 0 --end 6      # quick slice
"""
from __future__ import annotations

import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from fight.clash import DURATION  # noqa: E402
from fight.clashfilm import render, storyboard  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=int, default=1280)
    ap.add_argument("--out", default="renders/mountain_clash_720p.mp4")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=DURATION)
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--tune", default="animation")
    ap.add_argument("--storyboard", type=int, default=0,
                    help="render N evenly spaced moments to renders/storyboard.jpg")
    args = ap.parse_args()
    h = int(round(args.w * 9 / 16))
    if args.storyboard:
        n = args.storyboard
        times = [round(0.4 + i * (DURATION - 1.2) / max(n - 1, 1), 2) for i in range(n)]
        storyboard(times, "renders/storyboard.jpg", w=args.w, h=h)
        return
    t0 = time.time()
    render(args.out, w=args.w, h=h, workers=args.workers, audio=not args.no_audio,
           start=args.start, end=args.end, preset=args.preset, crf=args.crf,
           tune=args.tune)
    print(f"total {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
