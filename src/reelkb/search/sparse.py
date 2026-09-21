"""Sparse retrieval: BGE-M3's lexical weights (§5), and the storage format for them.

**Storage format (independent decision, documented here because nothing in the contract
fixes it -- ``embedding_rows`` in ``schema.sql`` only tracks the dense vector file).**
Sparse weights are written to ``data/sparse_weights.jsonl``, one JSON object per line:

    {"item_id": "FAKEmv001", "weights": {"flow": 0.34, "cat": 0.21, ...}}

JSON Lines rather than a database table because the write-once/one-owner rules in
``contract/db.py`` are already fully expressed by ``embedding_rows`` (which stage produced
this item's vectors, and in what order) -- the *weights themselves* are exactly the kind of
large, per-item blob the dense vectors already live outside the database for. Keeping both
vector artefacts as plain files next to ``embeddings.npy`` means the embed stage has one
place to write large arrays, and the database stays cheap to inspect. Order does not matter
for this file (lookup is by item_id, not row position), unlike ``embeddings.npy`` where row
position **is** the join key.

Scoring: a sparse "dot product" between the query's token weights and a document's token
weights, summed only over tokens present in both -- exactly BGE-M3's own scoring rule for its
lexical weights, and exactly the same idea whether the weights came from the real model or
``FakeEncoder``'s token counts.
"""

from __future__ import annotations

import json
from pathlib import Path


def save_sparse_weights(path: Path, weights_by_item: dict[str, dict[str, float]]) -> None:
    """Write ``{item_id: {token: weight}}`` as JSON Lines, one item per line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for item_id, weights in weights_by_item.items():
            f.write(json.dumps({"item_id": item_id, "weights": weights}, ensure_ascii=False))
            f.write("\n")


def load_sparse_weights(path: Path) -> dict[str, dict[str, float]]:
    """Read a file written by ``save_sparse_weights`` back into ``{item_id: {token: weight}}``."""
    weights_by_item: dict[str, dict[str, float]] = {}
    if not path.exists():
        return weights_by_item
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            weights_by_item[row["item_id"]] = row["weights"]
    return weights_by_item


def sparse_dot(query_weights: dict[str, float], doc_weights: dict[str, float]) -> float:
    """Sum of ``query_weight * doc_weight`` over tokens present in both (BGE-M3's own rule)."""
    if len(query_weights) > len(doc_weights):
        query_weights, doc_weights = doc_weights, query_weights
    return sum(
        weight * doc_weights[token]
        for token, weight in query_weights.items()
        if token in doc_weights
    )


class SparseIndex:
    """Scores a query's token weights against every document's stored token weights."""

    def __init__(self, weights_by_item: dict[str, dict[str, float]]) -> None:
        self._weights_by_item = weights_by_item

    def __len__(self) -> int:
        return len(self._weights_by_item)

    def score(self, query_weights: dict[str, float]) -> dict[str, float]:
        return {
            item_id: sparse_dot(query_weights, doc_weights)
            for item_id, doc_weights in self._weights_by_item.items()
        }
