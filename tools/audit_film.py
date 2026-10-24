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
from fight import rig  # noqa: E402

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

# round 8: the horizontal axis, the close fight, the chains and the juggle
MIN_HERO_FLIPS = 6
MIN_ENEMY_FLIPS = 4
#: A three-frame turn cannot be instantly correct: for one or two frames the body
#: is still opening out on the old side. What must never happen is a fighter who
#: *stays* facing away — one who moonwalks through a whole exchange. So the gate
#: is a run length (a quarter of a second) plus a loose total, not a hard count
#: of transition frames.
MAX_MISALIGNED = 45
MAX_MISALIGNED_RUN = 6
MAX_MIN_GAP = 42.0          # the closest the pair ever get - a grapple needs < 42
MIN_CHAINED = 5             # beats with no recovery phase
MIN_DUAL_AIR = 8            # frames with both men off the floor


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
    hero_flips = enemy_flips = misaligned = dual_air = 0
    misalign_run = misalign_worst = 0
    min_gap = 1e9
    prev_hero_sign = None
    prev_enemy_sign = {tr.name: None for tr in sc["tracks"] if tr.name != "red"}

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

        # --- the horizontal axis -----------------------------------------
        # A fighter that never turns is a sprite with a walk cycle. Count the
        # frames where the drawn body points away from the man it is fighting.
        hsign = 1 if hero.facing_at(t) >= 0 else -1
        if prev_hero_sign is not None and hsign != prev_hero_sign:
            hero_flips += 1
        prev_hero_sign = hsign
        for tr in sc["tracks"]:
            if tr.name == "red":
                continue
            esign = 1 if tr.facing_at(t) >= 0 else -1
            if prev_enemy_sign[tr.name] is not None and esign != prev_enemy_sign[tr.name]:
                enemy_flips += 1
            prev_enemy_sign[tr.name] = esign

        live = [tr for tr in sc["tracks"]
                if tr.name != "red" and skels[tr.name].head[1] < GROUND - 55]
        if live:
            # the man he is *engaged with*, not merely the nearest silhouette: a
            # rival can stand closer than the one he is trading with, and turning
            # to face the nearest body is how a fighter ends up with his back to
            # the fight
            engaged = rig.active_opponent(sc, t)
            if engaged is not None:
                by_name = {tr.name: tr for tr in sc["tracks"]}
                if engaged in by_name:
                    # pelvis against pelvis: a body thrown over the attacker's
                    # head has its head on one side of him and its feet on the
                    # other, and it is the body that changed sides
                    dx = pose_of(by_name[engaged], t).x - pose_of(hero, t).x
                    # only a *settled* body has a direction: while the turn is
                    # in progress the figure is edge-on and points nowhere
                    wrong = (abs(dx) > 28.0 and abs(hero.facing_at(t)) > 0.95
                             and (1 if dx > 0 else -1) != hsign)
                    if wrong:
                        misaligned += 1
                        misalign_run += 1
                        misalign_worst = max(misalign_worst, misalign_run)
                    else:
                        misalign_run = 0
            for tr in live:
                min_gap = min(min_gap,
                              abs(skels[tr.name].head[0] - skels["red"].head[0]))

        # both men in the air at the same time: the thing a single jump cannot do
        # 200 px above the floor is well clear of standing (a standing pelvis is
        # about 130): this is a man in the air, not a man on his feet
        if (pose_of(hero, t).y < hero.ground_y() - 200.0 and
                any(pose_of(tr, t).y < tr.ground_y() - 200.0 for tr in live)):
            dual_air += 1

        if vfx.impact_frame_index(sc, t) is not None:
            impacts_frames.add(round(t, 3))
        t += step

    x_span = max(xs) - min(xs)
    y_span = max(ys) - min(ys)
    zoom_range = max(zooms) - min(zooms)
    beats = sc.get("beats", ())
    moves = set(sc.get("move_types", ()))
    side_swaps = sum(1 for b in beats if getattr(b, "side_swap", False))
    chained = sum(1 for b in beats
                  if (0 if getattr(b, "chain", False)
                      else round(getattr(b, "recover", 1.0) * args.fps)) <= 1)
    z_lanes = sorted({round(getattr(tr, "z", 0.0), 2) for tr in sc["tracks"]})
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
    print(f"  turn         hero {hero_flips} flips, rivals {enemy_flips}, "
          f"back-to-front {misaligned} frames, longest run {misalign_worst} "
          f"(max {MAX_MISALIGNED} / run {MAX_MISALIGNED_RUN})")
    print(f"  contact      closest pair {min_gap:.1f} px (need < {MAX_MIN_GAP:.0f})")
    print(f"  rhythm       {chained} chained beats (recovery <= 1 frame, need {MIN_CHAINED})")
    print(f"  air          {dual_air} frames with both men off the floor (need {MIN_DUAL_AIR})")
    print(f"  depth        z lanes {z_lanes}")

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
    if hero_flips < MIN_HERO_FLIPS:
        fails.append(f"the hero turns {hero_flips} times (need {MIN_HERO_FLIPS})")
    if enemy_flips < MIN_ENEMY_FLIPS:
        fails.append(f"the rivals turn {enemy_flips} times in total (need {MIN_ENEMY_FLIPS})")
    if misaligned > MAX_MISALIGNED:
        fails.append(f"{misaligned} frames facing away from the active opponent (max {MAX_MISALIGNED})")
    if misalign_worst > MAX_MISALIGNED_RUN:
        fails.append(f"the hero faces away for {misalign_worst} frames in a row "
                     f"(max {MAX_MISALIGNED_RUN}) - he is moonwalking")
    if min_gap > MAX_MIN_GAP:
        fails.append(f"the pair never get closer than {min_gap:.0f} px (need under {MAX_MIN_GAP:.0f})")
    if chained < MIN_CHAINED:
        fails.append(f"only {chained} beats chain without a recovery (need {MIN_CHAINED})")
    if dual_air < MIN_DUAL_AIR:
        fails.append(f"only {dual_air} frames with both fighters airborne (need {MIN_DUAL_AIR})")
    if len(z_lanes) < 2:
        fails.append("every fighter stands on one depth lane")
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
