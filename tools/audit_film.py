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
from fight.clashfilm import (DESIGN_H, DURATION, GROUND, camera, pose_of,  # noqa: E402
                            scene, solve)
from fight.core import SEG  # noqa: E402
from fight.poses import ARM_K, LEG_K  # noqa: E402
from fight import rig  # noqa: E402

LEG = (SEG[7][2] + SEG[8][2]) * LEG_K
ARM = (SEG[3][2] + SEG[4][2]) * ARM_K

MIN_BEATS_FLOOR = 12
MIN_MOVES = 5
MIN_SWAPS = 2
MIN_X = 420.0
MIN_Y = 85.0
MIN_ZOOM_RANGE = 0.22
MIN_IMPACT_FRAMES = 2
MAX_STACK = 0.15

# round 8: the horizontal axis, the close fight, the chains and the juggle

#: A three-frame turn cannot be instantly correct: for one or two frames the body
#: is still opening out on the old side. What must never happen is a fighter who
#: *stays* facing away — one who moonwalks through a whole exchange. So the gate
#: is a run length (a quarter of a second) plus a loose total, not a hard count
#: of transition frames.
MAX_MISALIGNED = 18
MAX_MISALIGNED_RUN = 6

# round 9: the range, not just the floor
MIN_HERO_TURNS, MAX_HERO_TURNS = 8, 13
MIN_RIVAL_TURNS, MAX_RIVAL_TURNS = 6, 14
MIN_CONTACT, MAX_CONTACT = 20.0, 38.0
MIN_BEATS, MAX_BEATS = 22, 28
MAX_SCRUM = 24
SCRUM_RADIUS = 175.0
PERIMETER = 210.0
MAX_WAITING_CLOSE = 24     # frames a bystander may crowd the duel
MA_HOLDS = 3               # dramatic pauses before the bursts
MA_FRAMES = (10, 12)       # each one is a beat of held breath
MIN_KNOCK = 280.0
MAX_KNOCK = 360.0
MIN_BIG_KNOCKS = 5         # long knockbacks that clear the frame

# round 10: the fight has to change its *nature*, not just its distance
MIN_WEAPON_CHANGES = 4     # equip -> disarm / break / draw / conjure, per film
MIN_POWERS = 5             # distinct superpower systems on screen
MIN_HIT_ZONES = 3          # head / gut / sweep, each with its own reaction
MIN_UNARMED_FRAMES = 48    # two seconds of fists, knees and throws
MAX_MIN_GAP = 42.0          # the closest the pair ever get - a grapple needs < 42
MIN_CHAINED = 5             # beats with no recovery phase
MIN_DUAL_AIR = 8            # frames with both men off the floor


def drawn_x(sc, tr, t: float) -> float:
    """Where a fighter's pelvis is *on screen*: keys plus the blow's recoil."""
    f = 1 if tr.facing_at(t) >= 0 else -1
    return pose_of(tr, t).x + sc["push_at"](sc["impacts"], tr.name, t, f)


def dual_air_next(sc, hero, live, t) -> bool:
    """Is somebody else off the floor at the same time as the hero?"""
    if pose_of(hero, t).y >= hero.ground_y() - 200.0:
        return False
    return any(pose_of(tr, t).y < tr.ground_y() - 200.0 for tr in live)


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
    scrum_frames = 0
    air_frames = 0
    air_framed = 0
    waiting_close = 0
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
                    dx = drawn_x(sc, by_name[engaged], t) - drawn_x(sc, hero, t)
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
            # the *engaged* pair only: the crowd is allowed to be near the
            # camera, the two men trading blows are not allowed to be inside
            # each other
            for tr in live:
                # an upright pair, not a thrown body on its way to the floor:
                # a ragdoll crossing the attacker is a knockdown, not clipping
                if (engaged == tr.name
                        and pose_of(hero, t).y < hero.ground_y() - 40.0
                        and pose_of(tr, t).y < tr.ground_y() - 40.0):
                    min_gap = min(min_gap,
                                  abs(drawn_x(sc, tr, t) - drawn_x(sc, hero, t)))

        # the aerial frame: the tallest head must be clear of the top edge and the
        # floor must still be in shot, or the jump has no height to read against
        if dual_air_next(sc, hero, live, t):
            air_frames += 1
            top = cam["y"] - (DESIGN_H * 0.5) / max(1e-6, cam["zoom"])
            bottom = cam["y"] + (DESIGN_H * 0.5) / max(1e-6, cam["zoom"])
            hi = min([pose_of(hero, t).y - 96.0] +
                     [pose_of(tr, t).y - 96.0 for tr in live])
            ground_now = min([hero.ground_y()] + [tr.ground_y() for tr in live])
            if hi >= top + 20.0 and ground_now <= bottom - 8.0:
                air_framed += 1

        # both men in the air at the same time: the thing a single jump cannot do
        # 200 px above the floor is well clear of standing (a standing pelvis is
        # about 130): this is a man in the air, not a man on his feet
        if (pose_of(hero, t).y < hero.ground_y() - 200.0 and
                any(pose_of(tr, t).y < tr.ground_y() - 200.0 for tr in live)):
            dual_air += 1

        # --- the perimeter: an enemy who is not in this exchange watches it from
        # outside the duel, not from the protagonist's shoulder
        busy_now = set()
        for b in sc.get("beats", ()):
            t0, _t1, _t2, t_back = b.phases
            if t0 - 0.35 <= t <= t_back + 0.35:
                busy_now.add(b.attacker)
                if b.defender:
                    busy_now.add(b.defender)
        for tr in live:
            if tr.name in busy_now:
                continue
            # a man *walking in* is allowed to cross the perimeter - that is how
            # he enters the fight. A man who is *waiting* is the problem: he
            # stands still inside the duel and the frame becomes a queue.
            v = abs(tr.sample(t + 1.0 / 24.0)[1] - tr.sample(t)[1])
            if v > 6.0 or pose_of(tr, t).y < tr.ground_y() - 40.0:
                continue
            if abs(drawn_x(sc, tr, t) - drawn_x(sc, hero, t)) < PERIMETER:
                waiting_close += 1
                break

        # --- anti-scrum: how often is the middle of the frame a pile of bodies?
        # Three or more living fighters inside a 175 px band is the "four bodies,
        # one knot" shot; it is allowed for the pincer, not for the whole film.
        live_x = sorted(tr.sample(t)[1] for tr in live)
        for i in range(len(live_x) - 1):
            j = i + 1
            while j < len(live_x) and live_x[j] - live_x[i] <= SCRUM_RADIUS:
                j += 1
            if j - i >= 3:
                scrum_frames += 1
                break

        if vfx.impact_frame_index(sc, t) is not None:
            impacts_frames.add(round(t, 3))
        t += step

    x_span = max(xs) - min(xs)
    y_span = max(ys) - min(ys)
    zoom_range = max(zooms) - min(zooms)
    beats = sc.get("beats", ())
    moves = set(sc.get("move_types", ()))
    # sides are counted from the film, not from a flag: every frame the engaged
    # pair swap left/right is a crossing the audience actually sees
    side_swaps = len(swaps)
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
    print(f"  air frame    {air_framed}/{air_frames} airborne frames hold the floor in shot")
    print(f"  depth        z lanes {z_lanes}")
    print(f"  scrum        {scrum_frames} frames with 3+ live bodies inside "
          f"{SCRUM_RADIUS:.0f} px (max {MAX_SCRUM})")
    print(f"  perimeter    waiting enemies crowd the duel in {waiting_close} frames "
          f"(max {MAX_WAITING_CLOSE}, {PERIMETER:.0f} px)")
    print(f"  ma           {len(sc.get('ma') or ())} holds of "
          f"{[round((b - a) * args.fps) for a, b in (sc.get('ma') or ())]} frames")
    # ---- round 10: objects, powers, anatomy ------------------------------
    transitions = list(sc.get("weapon_transitions") or ())
    powers = list(sc.get("powers") or ())
    kinds = {p["kind"] for p in powers}
    systems = set()
    if "flash_step" in kinds:
        systems.add("afterimages")
    if "awakening" in kinds:
        systems.add("lightning")
        systems.add("levitating_rocks")
    if "beam" in kinds:
        systems.add("energy_beam")
    if sc.get("debris") is not None:
        systems.add("debris")
    if any(t[2] == "shattered" for t in transitions):
        systems.add("shattered_steel")
    fields = list(sc.get("props").props) if sc.get("props") is not None else []
    # how long the protagonist fights with nothing in his hands: a taijutsu
    # phase is not a flourish, it needs long enough to be a *phase*
    unarmed_frames = 0
    if sc.get("props") is not None:
        for f in range(int(round(DURATION * args.fps))):
            tt = f / args.fps
            if sc["props"].held_by(tt, hero.name) is None:
                unarmed_frames += 1
    armed_windows = [(p.prop_id, e[0]) for p in fields for e in p.events]
    unarmed = [p for p in fields if p.events and any(e[1] == "hold"
                                                    and e[2].get("owner") is None
                                                    for e in p.events)]
    print(f"  weapons      {len(transitions)} state changes "
          f"({', '.join(sorted({t[2] for t in transitions}))})")
    print(f"  powers       {len(systems)} systems: {', '.join(sorted(systems))}")
    print(f"  anatomy      whip lag on, hit zones {sc.get('hit_zones')}, "
          f"{unarmed_frames} frames with empty hands")
    print(f"  knockback    {len([k for k in [float(b.knock) for b in beats if b.defender] if MIN_KNOCK <= k <= MAX_KNOCK])} "
          f"in {MIN_KNOCK:.0f}-{MAX_KNOCK:.0f} px (need {MIN_BIG_KNOCKS})")

    if worst_leg > 1.0001 or worst_arm > 1.0001:
        fails.append(f"a limb is longer than its bones (leg {worst_leg:.4f}, arm {worst_arm:.4f})")
    if len(beats) < MIN_BEATS_FLOOR:
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
    if not (MIN_HERO_TURNS <= hero_flips <= MAX_HERO_TURNS):
        fails.append(f"the hero turns {hero_flips} times (need {MIN_HERO_TURNS}-{MAX_HERO_TURNS})")
    if not (MIN_RIVAL_TURNS <= enemy_flips <= MAX_RIVAL_TURNS):
        fails.append(f"the rivals turn {enemy_flips} times in total "
                     f"(need {MIN_RIVAL_TURNS}-{MAX_RIVAL_TURNS})")
    if misaligned > MAX_MISALIGNED:
        fails.append(f"{misaligned} frames facing away from the active opponent (max {MAX_MISALIGNED})")
    if misalign_worst > MAX_MISALIGNED_RUN:
        fails.append(f"the hero faces away for {misalign_worst} frames in a row "
                     f"(max {MAX_MISALIGNED_RUN}) - he is moonwalking")
    if not (MIN_CONTACT <= min_gap <= MAX_CONTACT):
        fails.append(f"closest engaged gap {min_gap:.1f} px (need {MIN_CONTACT}-{MAX_CONTACT})")
    if scrum_frames > MAX_SCRUM:
        fails.append(f"{scrum_frames} frames with 3+ live bodies inside {SCRUM_RADIUS:.0f} px "
                     f"(max {MAX_SCRUM}) - that is a scrum, not a fight")
    if len(beats) > MAX_BEATS:
        fails.append(f"{len(beats)} beats (need {MIN_BEATS}-{MAX_BEATS}): the film has no Ma")
    if chained < MIN_CHAINED:
        fails.append(f"only {chained} beats chain without a recovery (need {MIN_CHAINED})")
    if dual_air < MIN_DUAL_AIR:
        fails.append(f"only {dual_air} frames with both fighters airborne (need {MIN_DUAL_AIR})")
    # --- the aerial shot must hold the floor in frame -----------------------
    if air_frames and air_framed < 0.8 * air_frames:
        fails.append(f"only {air_framed}/{air_frames} airborne frames keep the floor in shot "
                     f"(need 80 %): the jump has no height to read against")
    if waiting_close > MAX_WAITING_CLOSE:
        fails.append(f"{waiting_close} frames with a waiting enemy inside {PERIMETER:.0f} px "
                     f"of the hero (max {MAX_WAITING_CLOSE}) - that is a pile, not a duel")
    # --- the Ma holds -------------------------------------------------------
    ma = list(sc.get("ma") or ())
    if len(ma) != MA_HOLDS:
        fails.append(f"{len(ma)} Ma holds (need {MA_HOLDS}): the film has no breathing room")
    for a, b in ma:
        n = round((b - a) * args.fps)
        if not (MA_FRAMES[0] <= n <= MA_FRAMES[1]):
            fails.append(f"a Ma hold lasts {n} frames (need {MA_FRAMES[0]}-{MA_FRAMES[1]})")
        inside = [be for be in beats if a - 1e-6 <= be.t <= b + 1e-6]
        if inside:
            fails.append(f"{len(inside)} beat(s) land inside the Ma hold at {a:.2f}s")
    # --- the knockbacks that are meant to clear the frame -------------------
    knocks = [float(be.knock) for be in beats if be.defender]
    big = [k for k in knocks if MIN_KNOCK <= k <= MAX_KNOCK]
    if len(big) < MIN_BIG_KNOCKS:
        fails.append(f"only {len(big)} knockbacks in the {MIN_KNOCK:.0f}-{MAX_KNOCK:.0f} px band "
                     f"(need {MIN_BIG_KNOCKS})")
    if knocks and max(knocks) > MAX_KNOCK:
        fails.append(f"a knockback throws a body {max(knocks):.0f} px (max {MAX_KNOCK:.0f})")
    if len(transitions) < MIN_WEAPON_CHANGES:
        fails.append(f"only {len(transitions)} weapon state changes "
                     f"(need {MIN_WEAPON_CHANGES}): the object is welded to the hand")
    if not any(t[2] in ("airborne_spinning", "shattered", "stuck_in_ground")
               for t in transitions):
        fails.append("no weapon is ever dropped, thrown or broken")
    if not sc.get("whip_lag"):
        fails.append("whip lag is off: every joint moves on the same frame")
    zones = set(sc.get("hit_zones") or ())
    if unarmed_frames < MIN_UNARMED_FRAMES:
        fails.append(f"only {unarmed_frames} frames fought empty-handed "
                     f"(need {MIN_UNARMED_FRAMES}): no taijutsu phase")
    if len(zones) < MIN_HIT_ZONES:
        fails.append(f"{len(zones)} localised hit reactions (need {MIN_HIT_ZONES})")
    if len(systems) < MIN_POWERS:
        fails.append(f"only {len(systems)} superpower systems on screen "
                     f"(need {MIN_POWERS}): {', '.join(sorted(systems)) or 'none'}")
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
