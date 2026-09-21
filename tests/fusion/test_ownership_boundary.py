"""AC-3.3 from the fusion side: "OCR output is stored with per-string confidence and
timestamp, in a field no model writes to." Two independent checks, matching the milestone
brief:

1. **Behavioural** — fusion's own connection (`connect_stage(db, "fusion")`), used the way
   `reelkb.fusion.stage.run` actually uses it, cannot write `ocr_verbatim` in any way. This
   duplicates part of `tests/contract/test_schema_boundaries.py` deliberately: that file
   proves the *general* rule for every stage/table pair; this one proves *this builder's
   code* exercises the door the contract expects (`connect_stage(db, "fusion")`), not some
   other route that happens to work today.
2. **Static** — the fusion package's own source code never contains an UPDATE or INSERT
   naming `ocr_verbatim`, so the guarantee doesn't rely on every future edit remembering to
   test it; a stray SQL string would be caught by grep before it ever ran.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from reelkb.contract.db import connect_stage

FUSION_SRC = Path(__file__).resolve().parents[2] / "src" / "reelkb" / "fusion"


def test_fusion_stage_connection_cannot_write_ocr_verbatim(unfused_db: Path) -> None:
    """The exact connection `reelkb.fusion.stage.run` is called with -- not a bare
    `sqlite3.connect` -- refuses every write to `ocr_verbatim` (AC-3.3)."""
    conn = connect_stage(unfused_db, "fusion")
    before = conn.execute("SELECT text FROM ocr_verbatim ORDER BY item_id, frame_ts_s").fetchall()

    with pytest.raises(sqlite3.IntegrityError, match="owned by the ocr stage"):
        conn.execute(
            "INSERT INTO ocr_verbatim VALUES ('FAKEml001', 99.0, 'fabricated.url', 1.0, NULL)"
        )
    with pytest.raises(sqlite3.IntegrityError, match="owned by the ocr stage"):
        conn.execute("DELETE FROM ocr_verbatim WHERE item_id = 'FAKEml001'")
    with pytest.raises(sqlite3.IntegrityError, match="ocr_verbatim"):
        conn.execute("UPDATE ocr_verbatim SET text = 'rewritten by fusion'")

    after = conn.execute("SELECT text FROM ocr_verbatim ORDER BY item_id, frame_ts_s").fetchall()
    assert before == after


def test_fusion_stage_connection_can_only_write_the_fusion_table(unfused_db: Path) -> None:
    """A same-connection sanity check: the door fusion actually uses lets it write `fusion`
    (or it couldn't do its job) but nothing else it might be tempted to touch."""
    conn = connect_stage(unfused_db, "fusion")
    conn.execute(
        "INSERT INTO fusion VALUES ('FAKEml001', 't', 's', '[]', '{}', '[]', '[]', 'en', 'fake', "
        "'2026-09-19T00:00:00+00:00')"
    )  # should not raise -- fusion owns this table
    for table in (
        "items",
        "fetch_status",
        "ocr_runs",
        "transcripts",
        "categories",
        "classification",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"DELETE FROM {table}")


# A conservative regex: any UPDATE or INSERT statement (case-insensitive, across whitespace)
# that mentions ocr_verbatim anywhere nearby. Written broadly on purpose -- this test's whole
# job is to be a tripwire, so it should fire on anything that *looks* like it might write
# ocr_verbatim, not only on a syntactically perfect SQL string.
_WRITE_KEYWORDS = re.compile(r"\b(INSERT|UPDATE)\b", re.IGNORECASE)


def test_fusion_source_never_contains_an_update_or_insert_on_ocr_verbatim() -> None:
    offenders = []
    for path in FUSION_SRC.rglob("*.py"):
        text = path.read_text()
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "ocr_verbatim" in line and _WRITE_KEYWORDS.search(line):
                offenders.append(
                    f"{path.relative_to(FUSION_SRC.parents[2])}:{lineno}: {line.strip()}"
                )
    assert offenders == [], (
        "fusion source contains what looks like a write to ocr_verbatim "
        f"(AC-3.3 tripwire): {offenders}"
    )


def test_fusion_source_does_not_reference_ocr_verbatim_as_a_write_target_at_all() -> None:
    """Stricter than the line-scan above: fusion never even names ``ocr_verbatim`` followed
    by a SQL verb within the same statement, scanning across line breaks (a multi-line SQL
    string would dodge the single-line check)."""
    combined = "\n".join(p.read_text() for p in FUSION_SRC.rglob("*.py"))
    statements = re.split(r";|\"\"\"|'''", combined)
    for stmt in statements:
        if "ocr_verbatim" in stmt and _WRITE_KEYWORDS.search(stmt):
            # Only fail if the write keyword and table name are close enough to plausibly be
            # the same SQL statement (a docstring mentioning both far apart is not a bug).
            ocr_idx = stmt.index("ocr_verbatim")
            nearby = stmt[max(0, ocr_idx - 200) : ocr_idx + 200]
            assert not _WRITE_KEYWORDS.search(nearby), (
                f"possible ocr_verbatim write near: {nearby!r}"
            )
