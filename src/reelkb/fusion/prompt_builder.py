"""Builds the two prompt strings sent to the model from one item's `FusionInput`.

The templates themselves live as plain text in `prompts/system.txt` and `prompts/user.txt` —
no archive content in either file, only placeholders filled in at run time. Loaded the same
way `contract/db.py` loads `schema.sql`, via `importlib.resources`, so this works whether the
package is run from source or installed.
"""

from __future__ import annotations

from importlib import resources
from string import Template

from reelkb.fusion.types import FusionInput

_SYSTEM_PROMPT = resources.files("reelkb.fusion.prompts").joinpath("system.txt").read_text()
_USER_TEMPLATE = Template(resources.files("reelkb.fusion.prompts").joinpath("user.txt").read_text())


def system_prompt() -> str:
    return _SYSTEM_PROMPT


def _notes(inp: FusionInput) -> str:
    notes = []
    if inp.lyric_like:
        notes.append("the transcript is sung / lyric-like (low confidence)")
    if inp.unreadable_text:
        notes.append("unreadable text was present on screen but not recovered")
    return "; ".join(notes) if notes else "none"


def user_prompt(inp: FusionInput) -> str:
    return _USER_TEMPLATE.substitute(
        caption=inp.caption or "(none)",
        ocr_text="\n".join(inp.ocr_texts) if inp.ocr_texts else "(none)",
        transcript=inp.transcript or "(none)",
        notes=_notes(inp),
    )
