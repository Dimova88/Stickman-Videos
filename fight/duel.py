"""THE EMPTY HAND — one blade against one man, 30 s, at the blue hour.

The film is a script (``fight/duel_script.py``); this module only hands it to
the assembler, the same way ``fight/steel.py`` does.
"""
from __future__ import annotations

from .duel_script import DUEL
from .steelkit import assemble


def build(set_name: str = "night") -> dict:
    """One scene, ready to render: the duel script, assembled."""
    return assemble(DUEL, set_name)
