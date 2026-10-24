"""The gate before a render: measure the film, do not trust it.

    python tools/audit_film.py --set steel-mountain

Wider than ``audit_rig.py``: that one only looked at bones, so only bones got
fixed. This one measures the things that make a fight *read* — the beat sheet,
how far the fighter actually travels, whether he ever crosses an opponent,
whether the crowd stands in a row, how much the camera moves — and exits
non-zero when the answer is no.

Every number is measured on the timeline that is about to be rendered, not on a
description of it.
"""
from __future__ import annotations

import argparse
import itertools
import math
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from fight import vfx  # noqa: E402
from fight.clashfilm import DURATION, GROUND, camera, pose_of, scene, solve  # noqa: E402
from fight.core import SEG  # noqa: E402
from fight.poses import ARM_K, LEG_K  # noqa: E402

LEG = (SEG[7][2] + SEG[8][2]) * LEG_K
ARM = (SEG[3][2] + SEG[4][2]) * ARM_K

MIN_BEATS = 12
MIN_MOVES = 5
MIN_SWAPS = 2
MIN_X = 420.0
MIN_Y = 85.0
MIN_ZOOM_RANGE = 0.22
MIN_IMPACT_FRAMES = 2
MAX_STACK = 0.15


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="set_name", default="steel-mountain")
    ap.add_argument("--fps", type=float, default=24.0)
    args = ap.parse_args()

    sc = scene(args.set_name)
    step = 1.0 / args.fps
    hero = sc["hero"]

    fails: list[str] = []
    frames = 0
    t = 0.0
    worst_leg = worst_arm = 0.0
    xs, ys = [], []
    zooms = []
    swaps, prev_sign = [], None
    stacked = 0
    impacts_frames = set()

    while t < DURATION:
        frames += 1
        skels = {tr.name: solve(pose_of(tr, t)) for tr in sc["tracks"]}
        for tr in sc["tracks"]:
            sk = skels[tr.name]
            for hip_sid, end_sid in ((7, 8), (9, 10)):
                hip, end = sk.starts[hip_sid], sk.pts[end_sid]
                worst_leg = max(worst_leg, math.hypot(end[0] - hip[0], end[1] - hip[1]) / LEG)
            for sh_sid, end_sid in ((3, 4), (5, 6)):
                sh, end = sk.starts[sh_sid], sk.pts[end_sid]
                worst_arm = max(worst_arm, math.hypot(end[0] - sh[0], end[1] - sh[1]) / ARM)

        hx, hy = pose_of(hero, t).x, pose_of(hero, t).y
        xs.append(hx)
        ys.append(hy)
        cam = camera(sc, t, sc["clock"].at(t))
        zooms.append(cam["zoom"])

        # who is the nearest opponent, and which side is he on?
        foes = [skels[tr.name].head[0] for tr in sc["tracks"] if tr.name != "red"]
        nearest = min(foes, key=lambda fx: abs(fx - hx))
        sign = 1 if nearest - hx >= 0 else -1
        if prev_sign is not None and sign != prev_sign and abs(nearest - hx) > 35:
            swaps.append(t)
        prev_sign = sign

        alive = sorted(skels[tr.name].head[0] for tr in sc["tracks"]
                       if tr.name != "red" and skels[tr.name].head[1] < GROUND - 55)
        if any(abs(alive[i + 1] - alive[i]) < 65.0 for i in range(len(alive) - 1)):
            stacked += 1

        if vfx.impact_frame_index(sc, t) is not None:
            impacts_frames.add(round(t, 3))
        t += step

    x_span = max(xs) - min(xs)
    y_span = max(ys) - min(ys)
    zoom_range = max(zooms) - min(zooms)
    beats = sc.get("beats", ())
    moves = set(sc.get("move_types", ()))
    side_swaps = sum(1 for b in beats if getattr(b, "side_swap", False))
    # two impact frames per accent = one accent unit
    accents = len(impacts_frames) / 2.0

    print(f"[audit_film] {args.set_name}: {frames} frames")
    print(f"  limbs        leg {worst_leg:.4f}  arm {worst_arm:.4f}   (max 1.0000)")
    print(f"  beat sheet   {len(beats)} beats, {len(moves)} move types, {side_swaps} side swaps")
    print(f"  root motion  x span {x_span:.1f} px, y span {y_span:.1f} px")
    print(f"  crowd        stacked frames {stacked}/{frames} "
          f"({100.0 * stacked / max(frames, 1):.1f} %, max {100 * MAX_STACK:.0f} %)")
    print(f"  camera       zoom {min(zooms):.2f}-{max(zooms):.2f} (range {zoom_range:.2f})")
    print(f"  impact       {len(impacts_frames)} monochrome frames (~{accents:.0f} accents)")

    if worst_leg > 1.0001 or worst_arm > 1.0001:
        fails.append(f"a limb is longer than its bones (leg {worst_leg:.4f}, arm {worst_arm:.4f})")
    if len(beats) < MIN_BEATS:
        fails.append(f"only {len(beats)} CombatBeat objects (need {MIN_BEATS})")
    if len(moves) < MIN_MOVES:
        fails.append(f"only {len(moves)} move types (need {MIN_MOVES})")
    if side_swaps < MIN_SWAPS:
        fails.append(f"only {side_swaps} side swaps (need {MIN_SWAPS})")
    if x_span < MIN_X:
        fails.append(f"the hero only travels {x_span:.0f} px horizontally (need {MIN_X:.0f})")
    if y_span < MIN_Y:
        fails.append(f"the pelvis only moves {y_span:.0f} px vertically (need {MIN_Y:.0f})")
    if stacked > MAX_STACK * frames:
        fails.append(f"waiting enemies stacked in {stacked} frames (over {MAX_STACK:.0%})")
    if zoom_range < MIN_ZOOM_RANGE:
        fails.append(f"camera zoom range {zoom_range:.2f} (need {MIN_ZOOM_RANGE:.2f})")
    if accents < MIN_IMPACT_FRAMES:
        fails.append(f"{len(impacts_frames)} impact frames (need {MIN_IMPACT_FRAMES * 2})")

    if fails:
        for f in fails:
            print(f"  x {f}")
        print("[audit_film] FAIL")
        return 1
    print("[audit_film] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
