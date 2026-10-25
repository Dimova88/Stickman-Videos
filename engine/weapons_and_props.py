"""Objects that are not welded to a hand.

Round 9's fighters held one katana each, from the first frame to the last. A
blade that is never dropped, thrown, broken or replaced is a costume, not a
weapon, and the audience stops believing in it about four seconds in.

Here a weapon is a **body**: it has an owner or it does not, it falls under
gravity, it spins, it sticks in the ground, it shatters into pieces that bounce
and settle, and it can be picked up again by whoever is standing there. The
fighter, meanwhile, is sometimes holding nothing at all — and a man with empty
hands has to fight with elbows, knees, sweeps and throws, which is the whole
reason taijutsu reads as more physical than fencing.

Everything is a pure function of the timeline: :class:`PropField` simulates the
flight once, at 24 fps, and the renderer only *samples* it. A frame can be
rendered in any order, twice, or on another machine, and the sword lands in the
same place.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

FPS = 24.0
FRAME = 1.0 / FPS
GRAVITY = 1.35          # design px per frame squared, tuned to the ragdoll's fall
BOUNCE = 0.34
FRICTION = 0.72

#: how long a broken blade's four pieces keep moving before they are just marks
DEBRIS_LIFE = 1.6

#: the ground the props fall to (the fighting plane; the plate is painted to it)
GROUND = 590.0

STEEL = (232, 238, 246)
HILT = (52, 44, 46)
ENERGY = (120, 236, 255)


@dataclass
class WorldProp:
    """One object in the world, and the story of what happened to it."""

    prop_id: str
    kind: str = "katana"          # katana | energy_spear | boulder
    owner: str | None = "red"
    length: float = 96.0
    colour: tuple = STEEL
    glow: float = 0.0
    #: state at t=0: held | sheathed
    state: str = "held_lead"
    #: (time, event, payload) — see :meth:`PropField.step`
    events: list = field(default_factory=list)

    def hold(self, t: float, owner: str | None) -> "WorldProp":
        """Give the prop to ``owner`` (or to nobody, at ``None``)."""
        self.events.append((float(t), "hold", {"owner": owner}))
        return self

    def launch(self, t: float, x: float, y: float, vx: float, vy: float,
               av: float = 0.42, kind: str = "disarm") -> "WorldProp":
        """``disarm``: it leaves the hand spinning and sticks in the ground."""
        self.events.append((float(t), "launch", {"x": x, "y": y, "vx": vx,
                                                 "vy": vy, "av": av, "why": kind}))
        return self

    def shatter(self, t: float, x: float, y: float, pieces: int = 4) -> "WorldProp":
        self.events.append((float(t), "shatter", {"x": x, "y": y, "pieces": pieces}))
        return self

    def conjure(self, t: float, owner: str, glow: float = 1.0,
                t_end: float | None = None) -> "WorldProp":
        """An energy weapon is *made* rather than drawn: it has no scabbard.

        ``t_end`` is when the power lets go of it — a blade of light is not
        carried out of the arena, it goes out with the fight.
        """
        self.events.append((float(t), "conjure",
                            {"owner": owner, "glow": glow, "t_end": t_end}))
        return self


class PropField:
    """Every prop in the film, sampled per frame.

    The simulation is integrated once, in frame order, on the render grid — the
    same discipline the capsule solver had to learn: a body that is keyed at
    24.583 does not exist at frame 24.542.
    """

    def __init__(self, props, duration: float = 30.2, ground: float = GROUND):
        self.props = list(props)
        self.duration = duration
        self.ground = ground
        self.n = int(round(duration * FPS)) + 1
        self.frames: list[list[dict]] = [[] for _ in range(self.n)]
        self._simulate()

    # ------------------------------------------------------------------ set-up
    def _events_for(self, prop) -> dict[int, list[tuple[str, dict]]]:
        out: dict[int, list[tuple[str, dict]]] = {}
        for t, name, payload in sorted(prop.events, key=lambda e: e[0]):
            f = min(self.n - 1, max(0, int(round(t * FPS))))
            out.setdefault(f, []).append((name, payload))
        return out

    def _simulate(self) -> None:
        state = {}
        for prop in self.props:
            state[prop.prop_id] = {
                "state": prop.state, "owner": prop.owner,
                "x": 0.0, "y": 0.0, "angle": 0.0,
                "vx": 0.0, "vy": 0.0, "av": 0.0,
                "glow": prop.glow, "frags": [],
            }
        scripts = {prop.prop_id: self._events_for(prop) for prop in self.props}
        for f in range(self.n):
            for prop in self.props:
                st = state[prop.prop_id]
                for name, payload in scripts[prop.prop_id].get(f, ()):
                    self._apply(prop, st, name, payload)
                self._advance(prop, st)
                self.frames[f].append(dict(st, prop_id=prop.prop_id, kind=prop.kind,
                                           length=prop.length, colour=prop.colour))

    def _apply(self, prop, st, name: str, payload: dict) -> None:
        if name == "hold":
            owner = payload["owner"]
            st["owner"] = owner
            st["state"] = "held_lead" if owner else "unarmed"
            st["vx"] = st["vy"] = st["av"] = 0.0
        elif name == "launch":
            st["state"] = "airborne_spinning"
            st["owner"] = None
            st["x"], st["y"] = float(payload["x"]), float(payload["y"])
            st["vx"], st["vy"] = float(payload["vx"]), float(payload["vy"])
            st["av"] = float(payload["av"])
            st["why"] = payload.get("why", "disarm")
        elif name == "shatter":
            st["state"] = "shattered"
            st["owner"] = None
            pieces = int(payload.get("pieces", 4))
            st["frags"] = [
                {"x": float(payload["x"]) + (i - 1.5) * 9.0,
                 "y": float(payload["y"]),
                 "vx": -7.0 + i * 4.6,
                 "vy": -12.0 - (i % 2) * 4.0,
                 "angle": i * 0.76, "av": 0.30 * (1 if i % 2 == 0 else -1),
                 "len": prop.length * 0.30}
                for i in range(pieces)
            ]
        elif name == "conjure":
            st["state"] = "held_lead"
            st["owner"] = payload["owner"]
            st["glow"] = float(payload.get("glow", 1.0))
            st["energy"] = True
            st["t_end"] = payload.get("t_end")

    def _advance(self, prop, st) -> None:
        if st["state"] == "airborne_spinning":
            st["x"] += st["vx"]
            st["y"] += st["vy"]
            st["vy"] += GRAVITY
            st["angle"] += st["av"]
            if st["y"] >= self.ground - 12.0:
                st["y"] = self.ground - 12.0
                # it does not lie flat: it bites the dirt at an angle
                st["angle"] = 0.62 if st["vx"] >= 0 else math.pi - 0.62
                st["state"] = "stuck_in_ground"
                st["vx"] = st["vy"] = st["av"] = 0.0
        elif st["state"] == "shattered":
            for fr in st["frags"]:
                if fr["y"] < self.ground - 4.0:
                    fr["x"] += fr["vx"]
                    fr["y"] += fr["vy"]
                    fr["vy"] += GRAVITY
                    fr["angle"] += fr["av"]
                else:
                    fr["y"] = self.ground - 4.0
                    fr["x"] += fr["vx"] * 0.35
                    fr["vx"] *= FRICTION
                    fr["av"] = 0.0

    # ----------------------------------------------------------------- sampling
    def at(self, t: float) -> list[dict]:
        f = min(self.n - 1, max(0, int(round(t * FPS))))
        return self.frames[f]

    def held_by(self, t: float, name: str):
        """The prop in ``name``'s hand at ``t``, or ``None``."""
        for snap in self.at(t):
            if (snap["owner"] == name and snap["state"] == "held_lead"
                    and (snap.get("t_end") is None or t <= float(snap["t_end"]))):
                return snap
        return None

    def loose(self, t: float) -> list[dict]:
        """Everything that is not in a hand: in the air, planted, or in pieces."""
        return [s for s in self.at(t)
                if s["state"] in ("airborne_spinning", "stuck_in_ground", "shattered")]

    def transitions(self) -> list[tuple[float, str, str]]:
        """``(time, prop_id, new_state)`` for every change of state in the film."""
        out, prev = [], {}
        for f in range(self.n):
            for snap in self.frames[f]:
                key = snap["prop_id"]
                cur = (snap["state"], snap["owner"])
                if key in prev and prev[key] != cur:
                    out.append((f / FPS, key, snap["state"]))
                prev[key] = cur
        return out


# ------------------------------------------------------------------- rendering
def draw_loose(cv, field: PropField, t: float) -> None:
    """Draw every prop that is not in a hand, plus the pieces of the broken ones."""
    from fight import steelblade
    from engine import superpowers as _sp
    u = cv.unit()
    for snap in field.loose(t):
        if snap["state"] == "shattered":
            for fr in snap["frags"]:
                if "x" not in fr:
                    continue
                p0 = cv.wp((fr["x"], fr["y"]))
                p1 = cv.wp((fr["x"] + math.cos(fr["angle"]) * fr["len"],
                            fr["y"] + math.sin(fr["angle"]) * fr["len"]))
                cv.line(p0, p1, max(1.5, 3.4 * u), (206, 214, 226), alpha=235)
            continue
        x, y = snap["x"], snap["y"]
        if not (-120.0 < x < 1400.0 and -200.0 < y < 900.0):
            continue
        if snap.get("kind") == "energy_spear":
            _sp.energy_lance(cv, (x, y), snap["angle"], snap["length"], glow=1.0)
            continue
        steelblade.draw_blade(cv, (x, y), snap["angle"], snap["length"],
                              glow=0.0, handle=True)
        if snap["state"] == "stuck_in_ground":
            # the ground bites back: a small scuff at the point where it landed
            gx, gy = cv.wp((x, field.ground - 2.0))
            cv.line((gx - 16 * u, gy), (gx + 16 * u, gy), max(1.4, 2.6 * u),
                    (24, 20, 22), alpha=110)
