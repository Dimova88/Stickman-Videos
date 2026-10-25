"""The score, planned by act instead of by scene.

``fight/sound.py`` already synthesises every cue from the scene's own impact
list — no samples, no loops, nothing borrowed. What it cannot know is the shape
of a **ten-minute** film: which act is allowed to be loud, where the music has to
get out of the way, and which two scenes have to be joined by silence rather
than by a downbeat.

That is this module. It returns a *plan*: a list of sections with a target
intensity, the instruments that may play, and the events that must duck the
music to nothing. The synthesiser obeys the plan; the director only has to say
which act the scene belongs to.
"""
from __future__ import annotations

import math

#: intensity is the loudness/urgency budget of a section, 0 to 1
ACTS = {
    "act1": {"name": "the world", "intensity": 0.34, "pulse": 84,
             "voices": ("low strings", "taiko", "wind")},
    "act2": {"name": "escalation", "intensity": 0.58, "pulse": 104,
             "voices": ("strings ostinato", "taiko", "metal hits", "bass")},
    "act3": {"name": "the fall", "intensity": 0.42, "pulse": 68,
             "voices": ("cello", "low pad", "heartbeat")},
    "act4": {"name": "awakening", "intensity": 0.92, "pulse": 132,
             "voices": ("full strings", "taiko", "choir pad", "metal", "sub")},
    "act5": {"name": "resolution", "intensity": 0.30, "pulse": 72,
             "voices": ("solo cello", "pad", "wind")},
}

#: structural silences. In a film with no narration, a hold with the music gone
#: is the only way to make the audience lean in.
DROPS = ("ma", "beam_clash", "final_blow")


def act_profile(act: str) -> dict:
    return dict(ACTS.get(act, ACTS["act2"]))


def plan_scene(act: str, duration: float = 30.2, drops=()) -> list[dict]:
    """The sections of one scene: intro, build, drop, aftermath.

    Each section carries ``t0``/``t1`` in scene time and the intensity it should
    reach at its end. ``sound.py`` uses that as a gain envelope, which is why the
    score does not just loop: it *slopes*.
    """
    prof = act_profile(act)
    i0 = prof["intensity"]
    marks = [(0.0, i0 * 0.55, "intro"),
             (duration * 0.22, i0 * 0.8, "build"),
             (duration * 0.55, i0, "main"),
             (duration * 0.82, i0 * 0.6, "aftermath")]
    if drops:
        marks.insert(2, (duration * 0.42, 0.02, "drop"))
    out = []
    for k, (t0, level, name) in enumerate(marks):
        t1 = marks[k + 1][0] if k + 1 < len(marks) else duration
        out.append({"t0": t0, "t1": t1, "name": name, "intensity": level,
                    "pulse": prof["pulse"], "voices": list(prof["voices"])})
    return out


def envelope(plan: list[dict], t: float) -> float:
    """The intensity the score should be at, at scene time ``t``."""
    for sec in plan:
        if sec["t0"] <= t < sec["t1"]:
            span = max(1e-6, sec["t1"] - sec["t0"])
            u = (t - sec["t0"]) / span
            prev = plan[max(0, plan.index(sec) - 1)]["intensity"]
            level = prev + (sec["intensity"] - prev) * (u * u * (3 - 2 * u))
            if sec["name"] == "drop":
                # a drop is a hole, not a fade: two frames of nothing
                return 0.0 if u > 0.25 else level * (1.0 - u * 3.0)
            return level
    return plan[-1]["intensity"] if plan else 0.0


def heartbeat(plan: list[dict], t: float, seed: int = 3) -> float:
    """A sub-bass thump whose rate follows the section's pulse.

    The rate is read from the plan, so as the act intensifies the score's pulse
    rises with it — the one thing a loop can never do.
    """
    for sec in plan:
        if sec["t0"] <= t < sec["t1"]:
            rate = sec["pulse"] / 60.0
            phase = (t * rate + (seed % 7) * 0.13) % 1.0
            return max(0.0, 1.0 - phase * 6.0) * sec["intensity"]
    return 0.0
