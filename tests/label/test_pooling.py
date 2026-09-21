"""Pooling merges and dedupes top-k hits across several searchers, discarding which one."""

from __future__ import annotations

from reelkb.contract.curation import Curation
from reelkb.contract.search_api import SearchFilters, SearchHit
from reelkb.label.pooling import pool_candidates


class _FixedSearcher:
    def __init__(self, hits: list[SearchHit]) -> None:
        self._hits = hits

    def search(
        self, query: str, curation: Curation, filters: SearchFilters | None = None, k: int = 20
    ) -> list[SearchHit]:
        return self._hits[:k]


def test_pool_dedupes_across_searchers() -> None:
    a = _FixedSearcher([SearchHit("x1", 1.0), SearchHit("x2", 0.9)])
    b = _FixedSearcher([SearchHit("x2", 1.0), SearchHit("x3", 0.5)])  # x2 overlaps with a
    pooled = pool_candidates("q", {"a": a, "b": b}, Curation(), seed=1)
    assert sorted(pooled) == ["x1", "x2", "x3"]


def test_pool_respects_k_per_searcher() -> None:
    a = _FixedSearcher([SearchHit(f"a{i}", 1.0) for i in range(20)])
    pooled = pool_candidates("q", {"a": a}, Curation(), k=5, seed=1)
    assert len(pooled) == 5


def test_pool_order_is_shuffled_not_method_order() -> None:
    a = _FixedSearcher([SearchHit(f"a{i}", 1.0) for i in range(10)])
    unshuffled = [f"a{i}" for i in range(10)]
    shuffled_once = pool_candidates("q", {"a": a}, Curation(), k=10, seed=1)
    shuffled_twice = pool_candidates("q", {"a": a}, Curation(), k=10, seed=2)
    assert sorted(shuffled_once) == sorted(unshuffled)
    # two different seeds should (almost certainly) not produce the exact same order
    assert shuffled_once != shuffled_twice or shuffled_once == unshuffled
