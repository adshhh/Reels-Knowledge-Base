"""FakeEncoder: deterministic, no model, no randomness (AC-6.2)."""

from __future__ import annotations

import numpy as np
import pytest

from reelkb.search.encoder import FakeEncoder, tokenize


def test_tokenize_lowercases_and_splits_on_non_alnum() -> None:
    assert tokenize("Attention Is All You Need (2017)!") == [
        "attention",
        "is",
        "all",
        "you",
        "need",
        "2017",
    ]


def test_encode_is_deterministic() -> None:
    enc = FakeEncoder(dim=32)
    a = enc.encode(["course.fast.ai free deep learning"])
    b = enc.encode(["course.fast.ai free deep learning"])
    assert np.array_equal(a.dense, b.dense)
    assert a.sparse == b.sparse


def test_dense_rows_are_l2_normalised() -> None:
    enc = FakeEncoder(dim=32)
    batch = enc.encode(["free deep learning course", "a completely different sentence here"])
    for row in batch.dense:
        norm = float(np.linalg.norm(row))
        assert norm == pytest.approx(1.0) or norm == pytest.approx(0.0)


def test_empty_text_gives_zero_vector_and_empty_sparse() -> None:
    enc = FakeEncoder(dim=16)
    batch = enc.encode([""])
    assert np.array_equal(batch.dense[0], np.zeros(16, dtype=np.float32))
    assert batch.sparse[0] == {}


def test_shared_words_are_more_similar_than_disjoint_texts() -> None:
    enc = FakeEncoder(dim=64)
    batch = enc.encode(
        [
            "free deep learning course from fast.ai",
            "a free deep learning course for beginners",
            "ten minute paneer bhurji recipe",
        ]
    )
    sim_similar = float(np.dot(batch.dense[0], batch.dense[1]))
    sim_different = float(np.dot(batch.dense[0], batch.dense[2]))
    assert sim_similar > sim_different


def test_sparse_weights_are_raw_token_counts() -> None:
    enc = FakeEncoder()
    batch = enc.encode(["flow flow cat"])
    assert batch.sparse[0] == {"flow": 2.0, "cat": 1.0}


def test_encode_empty_batch() -> None:
    enc = FakeEncoder(dim=8)
    batch = enc.encode([])
    assert batch.dense.shape == (0, 8)
    assert batch.sparse == []
