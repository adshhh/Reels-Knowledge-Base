"""The embed stage, driven end-to-end with FakeEncoder -- never loads BGE-M3 (AC-6.2).

The CLI itself (``main``) is exercised only for its argument handling and the missing-db
message; the encoding path is exercised through ``run_embed`` with an injected encoder, which
is exactly the seam ``run_embed`` documents for this purpose.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from reelkb.search.embed import main, run_embed
from reelkb.search.encoder import FakeEncoder
from reelkb.search.sparse import load_sparse_weights
from reelkb.testing.fake_db import REELS, build


def test_run_embed_writes_dense_matrix_matching_card_count(tmp_path: Path) -> None:
    build(tmp_path)
    n = run_embed(tmp_path, encoder=FakeEncoder(dim=32))
    assert n == len(REELS)
    matrix = np.load(tmp_path / "embeddings.npy")
    assert matrix.shape == (len(REELS), 32)


def test_run_embed_writes_sparse_weights_for_every_item(tmp_path: Path) -> None:
    build(tmp_path)
    run_embed(tmp_path, encoder=FakeEncoder(dim=32))
    weights = load_sparse_weights(tmp_path / "sparse_weights.jsonl")
    assert set(weights) == {r.item_id for r in REELS}


def test_run_embed_populates_embedding_rows_in_card_order(tmp_path: Path) -> None:
    build(tmp_path)
    run_embed(tmp_path, encoder=FakeEncoder(dim=32))
    conn = sqlite3.connect(tmp_path / "kb.db")
    rows = conn.execute("SELECT row, item_id FROM embedding_rows ORDER BY row").fetchall()
    expected_order = sorted(r.item_id for r in REELS)
    assert [item_id for _, item_id in rows] == expected_order
    assert [row for row, _ in rows] == list(range(len(REELS)))


def test_run_embed_is_safe_to_run_twice(tmp_path: Path) -> None:
    build(tmp_path)
    run_embed(tmp_path, encoder=FakeEncoder(dim=16))
    n_second = run_embed(tmp_path, encoder=FakeEncoder(dim=16))
    assert n_second == len(REELS)
    conn = sqlite3.connect(tmp_path / "kb.db")
    (count,) = conn.execute("SELECT COUNT(*) FROM embedding_rows").fetchone()
    assert count == len(REELS)


def test_dense_rows_are_normalised(tmp_path: Path) -> None:
    build(tmp_path)
    run_embed(tmp_path, encoder=FakeEncoder(dim=32))
    matrix = np.load(tmp_path / "embeddings.npy")
    norms = np.linalg.norm(matrix, axis=1)
    for norm in norms:
        assert norm == 0.0 or abs(norm - 1.0) < 1e-5


def test_main_reports_missing_database_and_exits_nonzero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(["--data-dir", str(tmp_path)])
    assert code != 0
    out = capsys.readouterr().out
    assert "kb.db" in out
