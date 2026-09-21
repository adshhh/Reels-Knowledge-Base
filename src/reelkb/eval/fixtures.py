"""Loading ``eval/holdout_v1.jsonl`` and ``eval/queries_v1.jsonl`` (§7).

Both files are produced by the owner's labelling page (a separate Wave 1 component) and are
committed to the public repo with hashed ids (``ids.py``) -- this module only reads them back
into plain Python values. Anything wrong with a fixture file raises ``FixtureError`` with a
message a human can act on; nothing here guesses or silently skips a bad line.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class FixtureError(RuntimeError):
    """A fixture file is missing, unreadable, or malformed."""


@dataclass(frozen=True)
class HoldoutItem:
    hid: str
    category_id: str


@dataclass(frozen=True)
class Query:
    qid: str
    query: str
    judgements: dict[str, int]  # hid -> 2 (exactly this) / 1 (related) / 0 (irrelevant)
    canary: bool = False
    # Hids that MUST appear in this query's top 10, named one by one. AC-5.2 is about a
    # specific reel ("the Flow case is a NAMED canary"), and a query-level boolean cannot
    # express that: the M8 checker showed a canary query passing while the Flow reel was
    # never returned, because some other relevant item was. (M8 checker, finding 2.)
    canary_hids: tuple[str, ...] = ()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FixtureError(f"missing fixture file: {path}")
    rows: list[dict[str, Any]] = []
    for lineno, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise FixtureError(f"{path}:{lineno}: invalid JSON ({e})") from e
    if not rows:
        raise FixtureError(f"{path}: no rows -- fixture file is empty")
    return rows


def load_holdout(path: Path) -> list[HoldoutItem]:
    """Read ``holdout_v1.jsonl``: one ``{"hid": ..., "category_id": ...}`` per line."""
    items = []
    for lineno, row in enumerate(_read_jsonl(path), start=1):
        try:
            items.append(HoldoutItem(hid=str(row["hid"]), category_id=str(row["category_id"])))
        except KeyError as e:
            raise FixtureError(f"{path}:{lineno}: missing field {e}") from e
    return items


def load_queries(path: Path) -> list[Query]:
    """Read ``queries_v1.jsonl``: one query per line, with graded judgements keyed by hid."""
    queries = []
    for lineno, row in enumerate(_read_jsonl(path), start=1):
        try:
            judgements = {str(hid): int(grade) for hid, grade in row.get("judgements", {}).items()}
            queries.append(
                Query(
                    qid=str(row["qid"]),
                    query=str(row["query"]),
                    judgements=judgements,
                    canary=bool(row.get("canary", False)),
                    canary_hids=tuple(str(h) for h in row.get("canary_hids", ())),
                )
            )
        except KeyError as e:
            raise FixtureError(f"{path}:{lineno}: missing field {e}") from e
    return queries
