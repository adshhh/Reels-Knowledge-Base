"""DenseIndex: brute-force cosine similarity, checked against hand-computed dot products."""

from __future__ import annotations

import numpy as np
import pytest

from reelkb.search.dense import DenseIndex


def _unit(vec: list[float]) -> np.ndarray:
    arr = np.array(vec, dtype=np.float32)
    return arr / np.linalg.norm(arr)


def test_score_hand_computed_cosine_similarity() -> None:
    matrix = np.stack([_unit([1.0, 0.0]), _unit([0.0, 1.0]), _unit([1.0, 1.0])])
    index = DenseIndex(["a", "b", "c"], matrix)
    scores = index.score(_unit([1.0, 0.0]))
    assert scores["a"] == pytest.approx(1.0)
    assert scores["b"] == pytest.approx(0.0, abs=1e-6)
    assert scores["c"] == pytest.approx(1 / (2**0.5))


def test_score_normalises_an_unnormalised_query() -> None:
    matrix = np.stack([_unit([1.0, 0.0])])
    index = DenseIndex(["a"], matrix)
    scores = index.score(np.array([5.0, 0.0], dtype=np.float32))  # not unit length
    assert scores["a"] == pytest.approx(1.0)


def test_mismatched_lengths_rejected() -> None:
    with pytest.raises(ValueError):
        DenseIndex(["a", "b"], np.zeros((1, 4), dtype=np.float32))


def test_empty_index_scores_empty() -> None:
    index = DenseIndex([], np.zeros((0, 4), dtype=np.float32))
    assert index.score(np.zeros(4, dtype=np.float32)) == {}
    assert len(index) == 0
