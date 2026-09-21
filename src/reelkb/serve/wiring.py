"""Choosing which search engine the running app uses.

This exists because of a real gap the M9/M10 checker found: ``create_app`` falls back to
``SubstringSearcher`` -- the deliberately dumb test double -- whenever no searcher is passed,
and nothing in the app ever passed one. The product would have shipped with the fake engine
on real data, silently, with every test green.

The rule here: if the vector files exist, use the real hybrid engine; otherwise fall back and
say so out loud, so "search feels bad" can never be a mystery.
"""

from __future__ import annotations

from pathlib import Path

from reelkb.contract.curation import load_curation
from reelkb.contract.db import connect_readonly
from reelkb.contract.search_api import Searcher
from reelkb.search.encoder import Encoder


def make_searcher(
    data_dir: Path,
    *,
    encoder: Encoder | None = None,
    fusion_method: str = "weighted_sum",
    alpha: float = 0.5,
    rrf_k: int = 60,
) -> tuple[Searcher | None, str]:
    """Return (searcher, a line to print). ``None`` means "let the app use its fallback".

    ``encoder`` is injectable so tests can wire the real engine with a fake encoder; in
    production it is None and the real BGE-M3 encoder is loaded by the embed module.
    """
    embeddings = data_dir / "embeddings.npy"
    if not embeddings.exists():
        return None, (
            f"[reelkb.serve] WARNING: no {embeddings.name} in {data_dir} -- falling back to "
            "the basic substring search. Results will be poor and AC-SEARCH is not being "
            "met. Run `python -m reelkb.search.embed` to build the real index."
        )

    # Imported here, not at module import time: this path pulls in the search stack, and in
    # production the encoder loads a real model (AC-6.2 keeps that out of unit-test imports).
    from reelkb.eval.runner import build_hybrid_searcher

    conn = connect_readonly(data_dir / "kb.db")
    searcher = build_hybrid_searcher(
        data_dir,
        conn,
        load_curation(data_dir),
        encoder=encoder,
        fusion_method=fusion_method,
        alpha=alpha,
        rrf_k=rrf_k,
    )
    return searcher, (
        f"[reelkb.serve] using the hybrid BGE-M3 search engine "
        f"[{fusion_method}, alpha={alpha}, rrf_k={rrf_k}]"
    )
