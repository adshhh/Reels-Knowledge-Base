"""How every part of the system opens the database.

Pipeline code calls ``connect_stage(path, "ocr")`` and can then write only the tables the OCR
stage owns. The web app calls ``connect_readonly(path)`` and can write nothing. Both rules
are enforced by SQLite itself, not by convention, so a bug elsewhere cannot break them.
"""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path
from typing import Literal

Stage = Literal["ingest", "fetch", "ocr", "speech", "fusion", "classify", "embed"]
STAGES: tuple[Stage, ...] = ("ingest", "fetch", "ocr", "speech", "fusion", "classify", "embed")

# The one place that says who may write what.
TABLE_OWNERS: dict[str, Stage] = {
    "items": "ingest",
    "fetch_status": "fetch",
    "ocr_verbatim": "ocr",
    "ocr_runs": "ocr",
    "transcripts": "speech",
    "fusion": "fusion",
    "categories": "classify",
    "classification": "classify",
    "embedding_rows": "embed",
}

# Tables whose rows may be added or removed by their owner but never changed in place.
WRITE_ONCE = {"ocr_verbatim"}


def _ownership_triggers() -> str:
    parts = []
    for table, owner in TABLE_OWNERS.items():
        for op in ("INSERT", "UPDATE", "DELETE"):
            parts.append(
                f"CREATE TRIGGER IF NOT EXISTS own_{table}_{op.lower()} "
                f"BEFORE {op} ON {table} WHEN stage() IS NOT '{owner}' "
                f"BEGIN SELECT RAISE(ABORT, '{table} is owned by the {owner} stage'); END;"
            )
    for table in WRITE_ONCE:
        parts.append(
            f"CREATE TRIGGER IF NOT EXISTS write_once_{table} BEFORE UPDATE ON {table} "
            f"BEGIN SELECT RAISE(ABORT, '{table} is write-once and cannot be updated'); END;"
        )
    return "\n".join(parts)


def init_db(path: Path) -> None:
    """Create the database file, tables and triggers. Safe to run twice."""
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = resources.files("reelkb.contract").joinpath("schema.sql").read_text()
    with sqlite3.connect(path) as conn:
        conn.executescript(schema)
        conn.executescript(_ownership_triggers())


def connect_stage(path: Path, stage: Stage) -> sqlite3.Connection:
    """Open a read-write connection that may write only the tables ``stage`` owns."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.create_function("stage", 0, lambda: stage, deterministic=True)
    return conn


def connect_readonly(path: Path) -> sqlite3.Connection:
    """Open a connection that cannot write anything (the serving layer, AC-8.2)."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
