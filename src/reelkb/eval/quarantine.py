"""AC-7.2: no holdout item_id may ever appear in a prompt file (§7). If one leaked into a
template or few-shot example, the model could memorise the answer and AC-4.1 would stop being
a real test. A "prompt file" is any file under a directory named ``prompts`` anywhere under a
source root (e.g. `src/reelkb/fusion/prompts/system.txt`) -- every model-calling stage keeps
templates there, so this needs no per-stage configuration.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Leak:
    path: Path
    item_id: str


def find_prompt_files(source_root: Path) -> list[Path]:
    """Every file under any directory named ``prompts`` anywhere below ``source_root``."""
    if not source_root.exists():
        return []
    return sorted(
        p
        for p in source_root.rglob("*")
        if p.is_file() and "prompts" in p.relative_to(source_root).parts
    )


def find_leaks(item_ids: Iterable[str], prompt_files: Iterable[Path]) -> list[Leak]:
    """Which (file, item_id) pairs have a holdout item_id appearing verbatim in a prompt file.

    Empty item_ids are skipped -- an empty string "appears" in every file and would only ever
    produce noise, never a real leak.
    """
    ids = [item_id for item_id in item_ids if item_id]
    leaks: list[Leak] = []
    for path in prompt_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for item_id in ids:
            if item_id in text:
                leaks.append(Leak(path, item_id))
    return leaks


def check_holdout_quarantine(holdout_item_ids: Iterable[str], source_root: Path) -> list[Leak]:
    """Convenience wrapper: ``find_leaks`` over every prompt file under ``source_root``.

    ``source_root`` is normally ``src/reelkb`` -- every pipeline stage's ``prompts/`` lives
    under it (AC-7.2).
    """
    return find_leaks(holdout_item_ids, find_prompt_files(source_root))
