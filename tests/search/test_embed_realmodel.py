"""Proves the real BGE-M3 path works, on the tiny fake corpus only.

Skipped by the normal unit run (``tests/conftest.py`` skips ``realmodel`` tests unless
``REELKB_ALLOW_MODELS=1``). Loads ~2 GB of model weights and takes real wall-clock time, so it
is run deliberately and alone, e.g.:

    direnv exec . .venv/bin/python -m pytest -m realmodel tests/search/test_embed_realmodel.py

never as part of ``check.sh`` or the default ``pytest`` invocation (§6: one model-holding
process at a time, and unit tests must never load a model, AC-6.2).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from reelkb.search.embed import BGEM3Encoder, run_embed
from reelkb.testing.fake_db import REELS, build


@pytest.mark.realmodel
def test_bgem3_encoder_produces_normalised_1024_dim_vectors() -> None:
    encoder = BGEM3Encoder(batch_size=4)
    batch = encoder.encode(["a free deep learning course", "ten-minute paneer bhurji recipe"])
    assert batch.dense.shape == (2, 1024)
    norms = np.linalg.norm(batch.dense, axis=1)
    for norm in norms:
        assert abs(norm - 1.0) < 1e-4
    assert all(row for row in batch.sparse)  # every text produced some lexical weight


@pytest.mark.realmodel
def test_run_embed_end_to_end_on_the_fake_corpus(tmp_path: Path) -> None:
    build(tmp_path)
    n = run_embed(tmp_path, batch_size=4)  # default (real) encoder
    assert n == len(REELS)
    matrix = np.load(tmp_path / "embeddings.npy")
    assert matrix.shape == (len(REELS), 1024)
