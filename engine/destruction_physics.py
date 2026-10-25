"""The ground is a character too, and it loses.

A slam that leaves nothing behind is a pose, not an impact. This module turns
each registered destruction event — a meteor slam, an energy beam hitting the
floor, a body thrown into the dirt — into two things that outlive the frame:

* a **crater** (registered where the floor was hit, drawn by ``fight/vfx.py``,
  permanent for the rest of the film), and
* **debris**: 8 to 16 polygonal chips that fly out along the impact axis, fall
  under gravity, bounce once with restitution and settle at their own angle.

Both are simulated once, on the render frame grid, so a frame can be rendered in
any order — a 10-minute film cannot afford a simulation that depends on having
drawn the previous frame first.
"""
from __future__ import annotations

import math
import random

FPS = 24.0
GRAVITY = 1.35
BOUNCE = 0.34
SETTLE = 0.75        # after this many seconds a chip stops glowing


class DebrisField:
    """Chips of floor, in flight."""

    def __init__(self, events, ground: float = 590.0, duration: float = 30.2,
                 seed: int = 11):
        self.ground = ground
        self.n = int(round(duration * FPS)) + 1
        self.frames: list[list[dict]] = [[] for _ in range(self.n)]
        rng = random.Random(seed)
        for ev in sorted(events, key=lambda e: e["t"]):
            self._spawn(ev, rng)

    def _spawn(self, ev, rng: random.Random) -> None:
        t0 = float(ev["t"])
        power = float(ev.get("power", 1.0))
        x = float(ev["x"])
        y = self.ground - 4.0
        count = int(8 + 8 * min(1.0, power))
        f0 = max(0, int(round(t0 * FPS)))
        for i in range(count):
            ang = -math.pi * (0.18 + 0.64 * rng.random())
            spd = (3.5 + 7.5 * rng.random()) * power
            chip = {
                "x": x + rng.uniform(-26, 26) * power,
                "y": y - rng.uniform(0, 6),
                "vx": math.cos(ang) * spd,
                "vy": math.sin(ang) * spd,
                "angle": rng.uniform(0, math.tau),
                "av": rng.uniform(-0.42, 0.42),
                "size": rng.uniform(3.2, 9.0) * (0.7 + 0.5 * power),
                "bounced": False,
            }
            for f in range(f0, self.n):
                self._advance(chip, f)
                if f - f0 > 4 * FPS:
                    break
                snap = dict(chip, birth=t0, age=(f / FPS) - t0)
                self.frames[f].append(snap)

    def _advance(self, chip, f: int) -> None:
        chip["x"] += chip["vx"]
        chip["y"] += chip["vy"]
        chip["vy"] += GRAVITY
        chip["angle"] += chip["av"]
        if chip["y"] >= self.ground - 3.0:
            chip["y"] = self.ground - 3.0
            if not chip["bounced"]:
                chip["vy"] = -abs(chip["vy"]) * BOUNCE
                chip["vx"] *= 0.72
                chip["bounced"] = True
            else:
                chip["vy"] = 0.0
                chip["vx"] *= 0.62
                chip["av"] *= 0.5

    def at(self, t: float) -> list[dict]:
        f = min(self.n - 1, max(0, int(round(t * FPS))))
        return self.frames[f]


def draw_debris(cv, field: DebrisField, t: float, colour=(84, 72, 64),
                edge=(30, 24, 22)) -> None:
    u = cv.unit()
    for chip in field.at(t):
        s = chip["size"] * u * (0.6 + 0.4 * min(1.0, chip["age"] / SETTLE))
        ca, sa = math.cos(chip["angle"]), math.sin(chip["angle"])
        pts = []
        for k in range(4):
            a = k * math.tau / 4.0 + 0.3
            rr = s * (0.70 + 0.45 * ((k % 2)))
            pts.append(cv.wp((chip["x"] + math.cos(a) * rr * ca - math.sin(a) * rr * sa,
                              chip["y"] + math.cos(a) * rr * sa + math.sin(a) * rr * ca)))
        cv.polygon(pts, colour, alpha=245)
        cv.polyline(pts + [pts[0]], max(1.0, 1.1 * u), edge, alpha=140)
