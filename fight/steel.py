"""STEEL — one blade against three men, 30 s.

This module is deliberately almost empty: the film is a *script*
(``fight/steel_script.py``) and the machinery that turns a script into frames
is ``fight/steelkit.py``. Keeping the two apart is what lets the next film be a
data file instead of a fork of the renderer.
"""
from __future__ import annotations

from .steel_script import STEEL
from .steelkit import assemble
from .steelkit import (BLADE, DUCK, E_BACK, E_CHOP, E_CHOP_END, E_GUARD,  # noqa: F401
                       E_STAG, HIGH, LOCK, LOW, OVER, PARRY, PARRY_LOW, PUSH,
                       READY, SPIN, CUT, CUT_HI, CUT_LO, TEAL, TEAL_DARK,
                       SLATE, SLATE_DARK)


def build(set_name: str = "mountain") -> dict:
    """One scene, ready to render: the steel script, assembled."""
    return assemble(STEEL, set_name)
