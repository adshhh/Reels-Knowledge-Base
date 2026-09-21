"""The owner's hand edits: hide, edit and recategorise (D15, §4.5).

Stored as two append-only JSON-lines files next to the database, never inside it:

- ``curation.jsonl``: ``{"action": "hide" | "unhide", "item_id": ...}`` and
  ``{"action": "edit", "item_id": ..., "field": "title" | "summary", "value": ...}``
- ``corrections.jsonl``: ``{"item_id": ..., "category_id": ...}``

Later lines win. No pipeline stage ever writes these files, so a re-run cannot undo them;
they are laid over the database whenever cards are read (see cards.py).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

EditableField = Literal["title", "summary"]
EDITABLE_FIELDS: tuple[EditableField, ...] = ("title", "summary")


@dataclass
class Curation:
    hidden: set[str] = field(default_factory=set)
    edits: dict[str, dict[str, str]] = field(default_factory=dict)  # item_id -> field -> value
    categories: dict[str, str] = field(default_factory=dict)  # item_id -> category_id
    # Lines that could not be read, so the UI can say so instead of dying or pretending.
    problems: list[str] = field(default_factory=list)


def _read_lines(path: Path) -> tuple[list[tuple[int, dict[str, object]]], list[str]]:
    """Parse a curation log, returning (events, complaints).

    A single unparseable line must not take the whole product down. ``_append`` is a plain
    non-atomic append, so a disk-full, an interrupted write or a hand-edit can leave a torn
    last line -- and the M7 checker showed that one such line turned EVERY route of the app
    into HTTP 500: the landing page, search, every category, every item, and /eval with it.
    The owner would face a completely dead knowledge base with no clue which file to look at.

    A bad line is skipped and reported, never rewritten: these files are the owner's own
    words and this layer is append-only, so nothing here ever edits or truncates them.
    """
    if not path.exists():
        return [], []
    events: list[tuple[int, dict[str, object]]] = []
    complaints: list[str] = []
    for lineno, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as e:
            complaints.append(f"{path.name}:{lineno}: unreadable line skipped ({e.msg})")
            continue
        if not isinstance(event, dict):
            complaints.append(f"{path.name}:{lineno}: expected an object, skipped")
            continue
        events.append((lineno, event))
    return events, complaints


def load_curation(data_dir: Path) -> Curation:
    cur = Curation()
    events, complaints = _read_lines(data_dir / "curation.jsonl")
    cur.problems.extend(complaints)
    for lineno, event in events:
        item_id = event.get("item_id")
        action = event.get("action")
        if not isinstance(item_id, str) or action not in ("hide", "unhide", "edit"):
            cur.problems.append(f"curation.jsonl:{lineno}: no usable action, skipped")
            continue
        if action == "hide":
            cur.hidden.add(item_id)
        elif action == "unhide":
            cur.hidden.discard(item_id)
        elif action == "edit":
            field_name, value = event.get("field"), event.get("value")
            if not isinstance(field_name, str) or value is None:
                cur.problems.append(f"curation.jsonl:{lineno}: incomplete edit, skipped")
                continue
            cur.edits.setdefault(item_id, {})[field_name] = str(value)

    events, complaints = _read_lines(data_dir / "corrections.jsonl")
    cur.problems.extend(complaints)
    for lineno, event in events:
        item_id, category_id = event.get("item_id"), event.get("category_id")
        if not isinstance(item_id, str) or not isinstance(category_id, str):
            cur.problems.append(f"corrections.jsonl:{lineno}: incomplete correction, skipped")
            continue
        cur.categories[item_id] = category_id
    return cur


def _append(path: Path, event: dict[str, object]) -> None:
    event = {**event, "at": datetime.now(UTC).isoformat(timespec="seconds")}
    # If the previous write was cut short it left no trailing newline, and appending straight
    # onto it would glue the new event to the broken one -- corrupting a second line, and
    # silently losing the edit the owner just made. Found by the test below, not by reading.
    needs_newline = path.exists() and path.stat().st_size > 0
    if needs_newline:
        with path.open("rb") as f:
            f.seek(-1, 2)
            needs_newline = f.read(1) != b"\n"
    with path.open("a") as f:
        if needs_newline:
            f.write("\n")
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def hide(data_dir: Path, item_id: str) -> None:
    _append(data_dir / "curation.jsonl", {"action": "hide", "item_id": item_id})


def unhide(data_dir: Path, item_id: str) -> None:
    _append(data_dir / "curation.jsonl", {"action": "unhide", "item_id": item_id})


def edit(data_dir: Path, item_id: str, field_name: EditableField, value: str) -> None:
    if field_name not in EDITABLE_FIELDS:
        raise ValueError(f"cannot edit {field_name!r}")
    _append(
        data_dir / "curation.jsonl",
        {"action": "edit", "item_id": item_id, "field": field_name, "value": value},
    )


def correct_category(data_dir: Path, item_id: str, category_id: str) -> None:
    _append(data_dir / "corrections.jsonl", {"item_id": item_id, "category_id": category_id})
