"""Storage for ``eval/holdout_v1.jsonl``: one ``{"hid": ..., "category_id": ...}`` per line.

Rewritten atomically in full on every save (write a temp file, then ``os.replace``), so a
closed tab or a killed process mid-write never truncates or corrupts the file, and a later
answer for a hid already present replaces its line instead of appending a duplicate.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

FILENAME = "holdout_v1.jsonl"


def load_answers(eval_dir: Path) -> dict[str, str]:
    """hid -> category_id."""
    path = eval_dir / FILENAME
    if not path.exists():
        return {}
    answers: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        answers[str(row["hid"])] = str(row["category_id"])
    return answers


def save_answer(eval_dir: Path, hid: str, category_id: str) -> None:
    """Record (or overwrite) the owner's answer for ``hid``."""
    answers = load_answers(eval_dir)
    answers[hid] = category_id
    _write_all(eval_dir, answers)


def _write_all(eval_dir: Path, answers: dict[str, str]) -> None:
    eval_dir.mkdir(parents=True, exist_ok=True)
    path = eval_dir / FILENAME
    tmp = path.with_name(FILENAME + ".tmp")
    with tmp.open("w") as f:
        for hid, category_id in answers.items():
            f.write(json.dumps({"hid": hid, "category_id": category_id}) + "\n")
    os.replace(tmp, path)
