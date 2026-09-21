"""Database-level boundaries (M1 rule: silent-breakers are proven first).

AC-3.3: ocr_verbatim is written by the OCR stage only, and never updated.
AC-8.2: the serving layer's connection cannot write anything.
Plus: every table refuses writes from any stage but its owner.
"""

import hashlib
import sqlite3
from pathlib import Path

import pytest

from reelkb.contract.db import TABLE_OWNERS, Stage, connect_readonly, connect_stage, init_db
from reelkb.testing.fake_db import build


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return build(tmp_path)


def _ocr_text(db: Path) -> list[str]:
    return [r[0] for r in connect_readonly(db).execute("SELECT text FROM ocr_verbatim")]


def test_fusion_stage_cannot_change_ocr_verbatim_in_any_way(db: Path) -> None:
    before = _ocr_text(db)
    conn = connect_stage(db, "fusion")
    with pytest.raises(sqlite3.IntegrityError, match="ocr_verbatim"):
        conn.execute("UPDATE ocr_verbatim SET text = 'coursera.org/fake'")
    with pytest.raises(sqlite3.IntegrityError, match="owned by the ocr stage"):
        conn.execute("DELETE FROM ocr_verbatim")
    with pytest.raises(sqlite3.IntegrityError, match="owned by the ocr stage"):
        conn.execute("INSERT INTO ocr_verbatim VALUES ('FAKEml001', 9.0, 'fake.url', 1.0, NULL)")
    assert _ocr_text(db) == before


def test_ocr_stage_itself_cannot_update_ocr_verbatim(db: Path) -> None:
    conn = connect_stage(db, "ocr")
    with pytest.raises(sqlite3.IntegrityError, match="write-once"):
        conn.execute("UPDATE ocr_verbatim SET text = 'changed'")


def test_ocr_stage_can_insert_and_redo_an_item(db: Path) -> None:
    with connect_stage(db, "ocr") as conn:
        conn.execute("DELETE FROM ocr_verbatim WHERE item_id = 'FAKEml001'")
        conn.execute(
            "INSERT INTO ocr_verbatim VALUES ('FAKEml001', 0.0, 'course.fast.ai', 0.9, NULL)"
        )
    rows = connect_readonly(db).execute("SELECT text FROM ocr_verbatim WHERE item_id = 'FAKEml001'")
    assert [r[0] for r in rows] == ["course.fast.ai"]


@pytest.mark.parametrize("table", sorted(TABLE_OWNERS))
def test_every_table_refuses_inserts_from_other_stages(db: Path, table: str) -> None:
    owner = TABLE_OWNERS[table]
    intruder: Stage = "fusion" if owner != "fusion" else "ocr"
    conn = connect_stage(db, intruder)
    # The ownership trigger fires before any column constraint is checked.
    with pytest.raises(sqlite3.IntegrityError, match=f"owned by the {owner} stage"):
        conn.execute(f"INSERT INTO {table} DEFAULT VALUES")


@pytest.mark.parametrize("table", sorted(TABLE_OWNERS))
@pytest.mark.parametrize("verb", ["UPDATE", "DELETE"])
def test_every_table_refuses_updates_and_deletes_from_other_stages(
    db: Path, table: str, verb: str
) -> None:
    """INSERT was the only verb covered. UPDATE and DELETE destroy data; INSERT does not.

    The M3 checker, probing ownership from the fetch stage, noticed that a BEFORE UPDATE or
    BEFORE DELETE trigger never fires against an EMPTY table -- zero rows, zero firings, so
    the statement 'succeeds' harmlessly and a probe reports a hole that isn't one. The flip
    side is the real gap: the committed test only ever tried INSERT, so nothing here proved
    that a stage cannot UPDATE or DELETE another stage's rows.

    This test guarantees a row exists (inserted as the rightful owner) before the intruder
    tries anything, so the row-level triggers genuinely fire.
    """
    owner = TABLE_OWNERS[table]
    intruder: Stage = "fusion" if owner != "fusion" else "ocr"
    if table == "embedding_rows":
        # The one table the fake database leaves empty (embeddings are built in M8), so it
        # needs a row before a row-level trigger can fire at all.
        with connect_stage(db, owner) as setup:
            setup.execute("INSERT INTO embedding_rows (row, item_id) VALUES (0, 'FAKEml001')")
    read = connect_readonly(db)
    assert read.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] > 0, (
        f"{table} is empty, so a BEFORE UPDATE/DELETE trigger would never fire and this "
        f"test would pass without proving anything"
    )
    first_column = read.execute(f"SELECT * FROM {table} LIMIT 0").description[0][0]

    before = hashlib.sha256(db.read_bytes()).hexdigest()
    conn = connect_stage(db, intruder)
    statement = (
        f"DELETE FROM {table}"
        if verb == "DELETE"
        else f"UPDATE {table} SET {first_column} = {first_column}"
    )
    with pytest.raises(sqlite3.IntegrityError, match=table):
        conn.execute(statement)
    conn.close()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_connection_without_a_stage_cannot_write(db: Path) -> None:
    conn = sqlite3.connect(db)
    with pytest.raises(sqlite3.OperationalError, match="stage"):
        conn.execute("DELETE FROM fusion")


@pytest.mark.parametrize("table", sorted(TABLE_OWNERS))
def test_serving_connection_cannot_write_any_table(db: Path, table: str) -> None:
    """The write must be refused AND the file must be byte-identical afterwards.

    The M1 checker showed the earlier version of this test (assert DatabaseError only) passed
    against a fully WRITABLE connection: the error it actually caught was the ownership
    trigger's 'no such function: stage', not read-only mode. Hashing the file closes that
    hole -- a writable connection would change the bytes.
    """
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    conn = connect_readonly(db)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute(f"INSERT INTO {table} DEFAULT VALUES")
    conn.close()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before


def test_serving_connection_is_read_only_even_without_the_triggers(db: Path) -> None:
    """Read-only mode is a second, independent wall: it refuses writes the triggers don't see."""
    digest = hashlib.sha256(db.read_bytes()).hexdigest()
    conn = connect_readonly(db)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("CREATE TABLE sneaky (x)")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DROP TRIGGER own_fusion_update")
    conn.close()
    assert hashlib.sha256(db.read_bytes()).hexdigest() == digest


def test_init_db_is_idempotent(tmp_path: Path) -> None:
    init_db(tmp_path / "kb.db")
    init_db(tmp_path / "kb.db")
