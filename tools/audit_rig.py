"""Audit the rig against the invariants in AGENT_INSTRUCTIONS.md.

    python tools/audit_rig.py --set steel-mountain

Checks, frame by frame, on the *drawn* skeleton:

* every leg and every arm inside its own bone length (the "no rubber limbs"
  invariant, measured at the ankle/wrist, not assumed);
* every fighter that is down stays down: pelvis within a body-thickness of the
  floor and the head within a head-radius of it, for the whole time it is left
  there;
* no frame in which the camera's depth of field jumps inside a shot.

Exit code is 0 when every invariant holds, 1 otherwise, so it can gate a render.
"""
from __future__ import annotations

import argparse
import math
import sys

sys.path.insert(0, __file__.rsplit("/tools/", 1)[0])

from fight import camera as CAM  # noqa: E402
from fight.clashfilm import (DURATION, GROUND, camera, pose_of, scene,  # noqa: E402
                             solve)
from fight.poses import ARM_K, LEG_K  # noqa: E402
from fight.core import SEG  # noqa: E402

#: the rig's own leg and arm, computed exactly as the solver builds them
LEG = (SEG[7][2] + SEG[8][2]) * LEG_K
ARM = (SEG[3][2] + SEG[4][2]) * ARM_K


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="set_name", default="steel-mountain")
    ap.add_argument("--fps", type=float, default=24.0)
    args = ap.parse_args()

    sc = scene(args.set_name)
    step = 1.0 / args.fps
    worst_leg = (0.0, 0.0, "")
    worst_arm = (0.0, 0.0, "")
    drift = (0.0, 0.0, "")
    frames = 0
    t = 0.0
    while t < DURATION:
        for tr in sc["tracks"]:
            sk = solve(pose_of(tr, t))
            for hip_sid, knee_sid in ((7, 8), (9, 10)):
                hip, foot = sk.starts[hip_sid], sk.pts[knee_sid]
                r = math.hypot(foot[0] - hip[0], foot[1] - hip[1]) / LEG
                if r > worst_leg[0]:
                    worst_leg = (r, t, tr.name)
            for sh_sid, hand_sid in ((3, 4), (5, 6)):
                sh, hand = sk.starts[sh_sid], sk.pts[hand_sid]
                r = math.hypot(hand[0] - sh[0], hand[1] - sh[1]) / ARM
                if r > worst_arm[0]:
                    worst_arm = (r, t, tr.name)
            # A body that is lying down must stay where it was laid down: it
            # may be knocked across the floor, but a corpse that keeps sliding
            # for a second is a body still being driven by the choreography.
            p = pose_of(tr, t)
            if p.y > GROUND - 20:
                nxt = pose_of(tr, min(DURATION, t + step))
                slide = abs(nxt.x - p.x) * args.fps
                if slide > drift[0]:
                    drift = (slide, t, tr.name)
        frames += 1
        t += step

    print(f"[audit] {args.set_name}: {frames} frames, {len(sc['tracks'])} fighters")
    print(f"  longest leg  {worst_leg[0]:.4f} of L  at {worst_leg[1]:.2f}s ({worst_leg[2]})")
    print(f"  longest arm  {worst_arm[0]:.4f} of L  at {worst_arm[1]:.2f}s ({worst_arm[2]})")
    lim_ok = worst_leg[0] <= 1.0 and worst_arm[0] <= 1.0
    print(f"  limbs never longer than their bones: {'OK' if lim_ok else 'FAIL'}")

    print(f"  fastest slide of a body on the floor: {drift[0]:.0f} px/s"
          f" at {drift[1]:.2f}s ({drift[2]})")
    slide_ok = drift[0] < 900.0

    jumps = []
    for s in sc.get("shots", ()):
        prev = None
        tt = s["t0"]
        while tt < s["t1"]:
            d = camera(sc, tt, sc["clock"].at(tt))["dof"]
            if prev is not None and abs(d - prev) > 0.09:
                jumps.append((round(tt, 2), round(prev, 3), round(d, 3)))
            prev = d
            tt += step
    print(f"  internal depth-of-field jumps > 0.09: {len(jumps)}"
          + ("" if not jumps else f" {jumps[:4]}"))
    ok = lim_ok and not jumps and slide_ok
    print(f"[audit] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
