"""Sparse weights: the documented storage format round-trips and the dot product is hand-checked."""

from __future__ import annotations

from pathlib import Path

import pytest

from reelkb.search.sparse import SparseIndex, load_sparse_weights, save_sparse_weights, sparse_dot


def test_save_and_load_round_trips(tmp_path: Path) -> None:
    weights = {
        "FAKEmv001": {"flow": 0.9, "cat": 0.4},
        "FAKEml001": {"course": 0.6, "free": 0.2},
    }
    path = tmp_path / "sparse_weights.jsonl"
    save_sparse_weights(path, weights)
    assert load_sparse_weights(path) == weights


def test_file_is_json_lines_one_object_per_item(tmp_path: Path) -> None:
    path = tmp_path / "sparse_weights.jsonl"
    save_sparse_weights(path, {"a": {"x": 1.0}, "b": {"y": 2.0}})
    lines = path.read_text().splitlines()
    assert len(lines) == 2


def test_load_missing_file_is_empty(tmp_path: Path) -> None:
    assert load_sparse_weights(tmp_path / "missing.jsonl") == {}


def test_sparse_dot_hand_computed() -> None:
    # overlap on "flow" (0.5*0.4=0.2) and "cat" (0.5*0.1=0.05); "movie" only in query -> ignored
    query = {"flow": 0.5, "movie": 0.3, "cat": 0.5}
    doc = {"flow": 0.4, "cat": 0.1, "wordless": 0.2}
    assert sparse_dot(query, doc) == pytest.approx(0.2 + 0.05)


def test_sparse_dot_no_overlap_is_zero() -> None:
    assert sparse_dot({"a": 1.0}, {"b": 1.0}) == 0.0


def test_sparse_dot_symmetric() -> None:
    a = {"x": 0.5, "y": 0.25}
    b = {"y": 0.4, "z": 0.1}
    assert sparse_dot(a, b) == pytest.approx(sparse_dot(b, a))


def test_sparse_index_scores_every_document() -> None:
    index = SparseIndex({"a": {"flow": 1.0}, "b": {"cat": 1.0}, "c": {"flow": 1.0, "cat": 1.0}})
    scores = index.score({"flow": 1.0})
    assert scores == {"a": pytest.approx(1.0), "b": pytest.approx(0.0), "c": pytest.approx(1.0)}
    assert len(index) == 3
