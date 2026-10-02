"""Dense retrieval: brute-force cosine similarity over a numpy matrix (§5). Storage is
``data/embeddings.npy`` (an (n, dim) float32 matrix) plus the ``embedding_rows`` table --
the only piece in the database -- mapping row i to an item_id. A few megabytes at this
corpus size; a vector database would add a network hop this problem doesn't need. This
module only scores a query vector against every row; loading and row-matching is the
caller's job (`index.py`, `embed.py`).
"""

from __future__ import annotations

import numpy as np


class DenseIndex:
    """A brute-force cosine-similarity index over one item_id per matrix row.

    ``matrix`` rows are expected to already be L2-normalised (``encoder.py`` guarantees this
    for both the fake and the real encoder), so cosine similarity is a plain dot product.
    """

    def __init__(self, item_ids: list[str], matrix: np.ndarray) -> None:
        if len(item_ids) != matrix.shape[0]:
            raise ValueError(f"{len(item_ids)} item_ids but matrix has {matrix.shape[0]} rows")
        self._item_ids = item_ids
        self._matrix = matrix

    def __len__(self) -> int:
        return len(self._item_ids)

    def score(self, query_vector: np.ndarray) -> dict[str, float]:
        """Cosine similarity of ``query_vector`` against every row, keyed by item_id."""
        if len(self._item_ids) == 0:
            return {}
        norm = float(np.linalg.norm(query_vector))
        q = query_vector / norm if norm > 0 else query_vector
        similarities = self._matrix @ q
        return dict(zip(self._item_ids, (float(s) for s in similarities), strict=True))
