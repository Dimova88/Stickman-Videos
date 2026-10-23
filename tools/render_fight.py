"""Render the 30 s fight.

    python tools/render_fight.py --w 1920 --out renders/fight_1080p.mp4
    python tools/render_fight.py --stills 2.9,6.1,13.4 --w 960
"""
from __future__ import annotations

import argparse
import sys
import time

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from fight.film import render, stills  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--out", default="renders/fight_1080p.mp4")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--stills", default="")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=30.0)
    args = ap.parse_args()
    h = int(round(args.w * 9 / 16))
    if args.stills:
        stills([float(v) for v in args.stills.split(",")], w=args.w, h=h)
        return
    t0 = time.time()
    render(args.out, w=args.w, h=h, workers=args.workers, audio=not args.no_audio,
           start=args.start, end=args.end)
    print(f"total {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
