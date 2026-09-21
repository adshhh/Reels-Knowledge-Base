"""Shared fixtures for `tests/fusion/`.

`reelkb.testing.fake_db.build` already prefills a `fusion` row for every fake reel (other
builders need cards to exist end-to-end). The fusion stage itself only processes items with
*no* fusion row yet, so an end-to-end test of the stage has to clear those rows first — done
through `connect_stage(db, "fusion")`, the same door the real stage uses, so the boundary
we're testing (fusion may only touch its own table) is exercised here too, not bypassed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reelkb.contract.db import connect_stage
from reelkb.testing.fake_db import build


@pytest.fixture
def fused_db(tmp_path: Path) -> Path:
    """A fake DB exactly as other builders get it: every item already has a fusion row."""
    return build(tmp_path)


@pytest.fixture
def unfused_db(tmp_path: Path) -> Path:
    """The same fake DB, with every fusion row cleared, so the fusion stage has work to do."""
    db = build(tmp_path)
    with connect_stage(db, "fusion") as conn:
        conn.execute("DELETE FROM fusion")
    return db
