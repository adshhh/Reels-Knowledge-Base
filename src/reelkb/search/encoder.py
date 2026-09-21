"""The ``Encoder`` boundary between the search engine and whatever model produces vectors.

The real encoder (``reelkb.search.embed.BGEM3Encoder``) wraps BGE-M3 and is only ever loaded
by the embed pipeline stage. Everything in this package that *searches* -- ``index.py``,
``fusion.py``, and every unit test -- is written against this protocol instead, so unit tests
build a deterministic ``FakeEncoder`` here and never load a real model (AC-6.2).

BGE-M3 produces two representations per text: a dense vector (semantic similarity) and a set
of *lexical weights* -- a sparse, token -> weight mapping that behaves like a learned
TF-IDF (exact-term matching). ``EncodedBatch`` mirrors that shape so the fake and the real
encoder are interchangeable.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Protocol

import numpy as np

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase, alphanumeric-run tokens. Shared by the fake encoder and ``matched_on``."""
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class EncodedBatch:
    dense: np.ndarray  # shape (n, dim), float32, L2-normalised rows
    sparse: list[dict[str, float]]  # one token -> weight mapping per input text


class Encoder(Protocol):
    dim: int

    def encode(self, texts: list[str]) -> EncodedBatch: ...


class FakeEncoder:
    """Deterministic stand-in for BGE-M3: no randomness, no model, no network (AC-6.2).

    Dense: each token is hashed into one of ``dim`` buckets (the "hashing trick"), so texts
    sharing words get non-zero cosine similarity and texts sharing none are (near-)
    orthogonal -- enough structure to unit-test ranking behaviour without a real embedding
    model. Sparse: raw token counts, which is exactly the exact-term-matching behaviour the
    real sparse half is standing in for (§5) -- it is what lets the Flow-style canary
    (AC-5.2) be found by a query whose words are absent from the caption but present in the
    on-screen text.
    """

    def __init__(self, dim: int = 64) -> None:
        self.dim = dim

    def _dense_vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        for token in tokenize(text):
            bucket = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16) % self.dim
            vec[bucket] += 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    def _sparse_weights(self, text: str) -> dict[str, float]:
        weights: dict[str, float] = {}
        for token in tokenize(text):
            weights[token] = weights.get(token, 0.0) + 1.0
        return weights

    def encode(self, texts: list[str]) -> EncodedBatch:
        dense = (
            np.stack([self._dense_vector(t) for t in texts])
            if texts
            else np.zeros((0, self.dim), dtype=np.float32)
        )
        sparse = [self._sparse_weights(t) for t in texts]
        return EncodedBatch(dense=dense, sparse=sparse)
