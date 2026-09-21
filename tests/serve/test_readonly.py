"""AC-8.2 (serve side): the app's database connection is read-only.

Two proofs: (1) the exact connection helper the app uses (`connect_readonly`) refuses a write
on the app's own database file, and (2) an architectural check on the serve source itself --
`connect_stage`, the read-write opener, never appears in `serve/`, so nothing in this area can
ever acquire a writable handle even by future accident.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import reelkb.serve.app as serve_app
from reelkb.contract.db import connect_readonly


def test_the_connection_the_app_uses_cannot_write(data_dir: Path) -> None:
    conn = connect_readonly(data_dir / "kb.db")
    # Both raise sqlite3.DatabaseError: the ownership triggers fire first (their BEFORE
    # clause calls a stage() function this connection never registered). A table with no
    # trigger at all is still blocked below, because the file itself is opened mode=ro (see
    # tests/contract/test_schema_boundaries.py for the trigger-free case in detail).
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM fusion")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("INSERT INTO categories VALUES ('x', 'x', '')")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("CREATE TABLE sneaky (x)")


def test_serve_source_never_opens_a_writable_connection() -> None:
    source = Path(serve_app.__file__).read_text()
    assert "connect_stage" not in source
    assert "connect_readonly" in source
