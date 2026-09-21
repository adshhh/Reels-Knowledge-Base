"""Pools top-k results from several Searchers into one deduplicated, shuffled candidate list.

Which method found a given candidate is deliberately discarded before it reaches the page:
DESIGN_RATIONALE §6 / the M7 build brief calls for the owner to judge candidates "with order
shuffled so the method isn't revealed" — grading should not be biased by knowing whether a
result came from the searcher expected to be strong on this kind of query.
"""

from __future__ import annotations

import random

from reelkb.contract.curation import Curation
from reelkb.contract.search_api import Searcher

DEFAULT_K = 10


def pool_candidates(
    query: str,
    searchers: dict[str, Searcher],
    curation: Curation,
    *,
    k: int = DEFAULT_K,
    seed: int | None = None,
) -> list[str]:
    """Unique item_ids pooled from each searcher's top ``k`` hits, in shuffled order."""
    seen: dict[str, None] = {}
    for searcher in searchers.values():
        for hit in searcher.search(query, curation, k=k):
            seen.setdefault(hit.item_id, None)
    pool = list(seen.keys())
    rng = random.Random(seed) if seed is not None else random.Random()
    rng.shuffle(pool)
    return pool
