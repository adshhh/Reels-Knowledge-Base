"""The embed pipeline stage (M8): ``python -m reelkb.search.embed``.

Reads every fused item from ``data/kb.db``, encodes its text (``card_text.text_for_card``)
with real BGE-M3, and writes:

- ``data/embeddings.npy`` -- the dense matrix, row i = the i-th item processed.
- ``data/sparse_weights.jsonl`` -- the sparse (lexical-weight) file, see ``sparse.py``.
- ``embedding_rows`` in the database (via ``connect_stage(db, "embed")``) -- which row of
  ``embeddings.npy`` belongs to which item_id (§5, ``schema.sql``).

BGE-M3 is loaded through ``FlagEmbedding`` -- fp16, small batches, one stage of the pipeline
alive at a time (§6: 8 GB of RAM total). The import is inside ``BGEM3Encoder.__init__``, not
at module level, so importing this module (e.g. for its CLI argument parsing, or from a test
that never constructs the real encoder) never triggers the unit-test import guard in
``tests/conftest.py`` -- only actually building a ``BGEM3Encoder`` does, which unit tests
never do (AC-6.2). The real-model path is proven by ``tests/search/test_embed_realmodel.py``,
marked ``@pytest.mark.realmodel``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from reelkb.contract.cards import load_cards
from reelkb.contract.curation import Curation
from reelkb.contract.db import connect_stage
from reelkb.search.card_text import text_for_card
from reelkb.search.encoder import EncodedBatch, Encoder
from reelkb.search.sparse import save_sparse_weights

DEFAULT_BATCH_SIZE = 8  # small batches: 8 GB of RAM total, macOS holds 3-4 of it (§6)


class BGEM3Encoder:
    """Real BGE-M3, wrapped to the ``Encoder`` protocol. Only ever constructed by this stage."""

    dim = 1024  # BGE-M3's dense dimension (§5, corrected 2026-09-19)

    def __init__(self, batch_size: int = DEFAULT_BATCH_SIZE) -> None:
        from FlagEmbedding import BGEM3FlagModel  # local import: keep model libs out of unit tests

        self._model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)
        self._batch_size = batch_size

    def encode(self, texts: list[str]) -> EncodedBatch:
        if not texts:
            return EncodedBatch(dense=np.zeros((0, self.dim), dtype=np.float32), sparse=[])
        out = self._model.encode(
            texts,
            batch_size=self._batch_size,
            max_length=2048,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        dense = np.asarray(out["dense_vecs"], dtype=np.float32)
        norms = np.linalg.norm(dense, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        dense = dense / norms
        # lexical_weights keys are BGE-M3 token ids (as strings), not words -- an internal,
        # model-specific vocabulary, opaque here and fine to be: sparse.py's scoring only
        # needs the same key space at query time and index time, which the same model gives.
        sparse = [{str(tok): float(w) for tok, w in row.items()} for row in out["lexical_weights"]]
        return EncodedBatch(dense=dense, sparse=sparse)


def run_embed(
    data_dir: Path, batch_size: int = DEFAULT_BATCH_SIZE, encoder: Encoder | None = None
) -> int:
    """Encode every fused item in ``data_dir/kb.db`` and write the vector files + embedding_rows.

    Returns the number of items embedded. ``encoder`` is injectable for the realmodel smoke
    test to swap in a tiny fake corpus without downloading anything twice; production always
    calls this with the default (real) encoder.
    """
    db_path = data_dir / "kb.db"
    conn = connect_stage(db_path, "embed")
    cards = load_cards(conn, Curation(), include_hidden=True)
    cards.sort(key=lambda c: c.item_id)  # stable row order across runs
    if not cards:
        conn.execute("DELETE FROM embedding_rows")
        conn.commit()
        return 0

    if encoder is None:
        encoder = BGEM3Encoder(batch_size=batch_size)

    dense_rows: list[np.ndarray] = []
    sparse_weights: dict[str, dict[str, float]] = {}
    texts = [text_for_card(c) for c in cards]
    for start in range(0, len(texts), batch_size):
        batch = encoder.encode(texts[start : start + batch_size])
        dense_rows.append(batch.dense)
        for card, weights in zip(cards[start : start + batch_size], batch.sparse, strict=True):
            sparse_weights[card.item_id] = weights

    dense_matrix = np.concatenate(dense_rows, axis=0) if dense_rows else np.zeros((0, encoder.dim))
    np.save(data_dir / "embeddings.npy", dense_matrix.astype(np.float32))
    save_sparse_weights(data_dir / "sparse_weights.jsonl", sparse_weights)

    conn.execute("DELETE FROM embedding_rows")
    conn.executemany(
        "INSERT INTO embedding_rows (row, item_id) VALUES (?, ?)",
        [(row, card.item_id) for row, card in enumerate(cards)],
    )
    conn.commit()
    return len(cards)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Encode every fused item with BGE-M3 (M8).")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    args = parser.parse_args(argv)

    if not (args.data_dir / "kb.db").exists():
        print(f"no database at {args.data_dir / 'kb.db'} -- run earlier pipeline stages first")
        return 2

    n = run_embed(args.data_dir, batch_size=args.batch_size)
    print(f"embedded {n} items -> {args.data_dir / 'embeddings.npy'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
