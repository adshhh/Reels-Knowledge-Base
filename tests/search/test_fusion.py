"""Score fusion: both methods checked against hand-computed (min-max / RRF) arithmetic."""

from __future__ import annotations

import pytest

from reelkb.search.fusion import fuse

DENSE = {"a": 0.9, "b": 0.5, "c": 0.1}
SPARSE = {"a": 2.0, "b": 0.0, "c": 4.0}


def test_weighted_sum_hand_computed() -> None:
    # min-max normalised: dense {a:1.0, b:0.5, c:0.0}, sparse {a:0.5, b:0.0, c:1.0}
    # fused (alpha=0.5): a=0.75, b=0.25, c=0.5 -> ranked a, c, b
    ranked = fuse(DENSE, SPARSE, method="weighted_sum", alpha=0.5)
    scores = dict(ranked)
    assert scores["a"] == pytest.approx(0.75)
    assert scores["b"] == pytest.approx(0.25)
    assert scores["c"] == pytest.approx(0.5)
    assert [item for item, _ in ranked] == ["a", "c", "b"]


def test_weighted_sum_alpha_1_is_pure_dense() -> None:
    ranked = fuse(DENSE, SPARSE, method="weighted_sum", alpha=1.0)
    assert [item for item, _ in ranked] == ["a", "b", "c"]  # dense order: 0.9, 0.5, 0.1


def test_weighted_sum_alpha_0_is_pure_sparse() -> None:
    ranked = fuse(DENSE, SPARSE, method="weighted_sum", alpha=0.0)
    assert [item for item, _ in ranked] == ["c", "a", "b"]  # sparse order: 4.0, 2.0, 0.0


def test_weighted_sum_identical_scores_dont_divide_by_zero() -> None:
    flat = {"a": 1.0, "b": 1.0}
    ranked = fuse(flat, flat, method="weighted_sum")
    assert dict(ranked) == {"a": pytest.approx(1.0), "b": pytest.approx(1.0)}


def test_weighted_sum_item_missing_from_one_side_still_scored() -> None:
    dense = {"a": 1.0, "b": 0.0}
    sparse = {"a": 1.0}  # "b" never appeared in the sparse ranking at all
    ranked = fuse(dense, sparse, method="weighted_sum", alpha=0.5)
    scores = dict(ranked)
    assert scores["a"] == pytest.approx(1.0)
    assert scores["b"] == pytest.approx(0.0)


def test_rrf_hand_computed() -> None:
    # dense ranks a=1,b=2,c=3. SPARSE["b"] is 0.0 -- b matched no query term, so it is ABSENT
    # from the sparse ranking rather than last in it, and sparse ranks only c=1, a=2.
    # rrf(a) = 1/61 + 1/62 = 0.03252247...
    # rrf(b) = 1/62           = 0.01612903...  (dense only)
    # rrf(c) = 1/63 + 1/61    = 0.03226645...
    ranked = fuse(DENSE, SPARSE, method="rrf", rrf_k=60)
    scores = dict(ranked)
    assert scores["a"] == pytest.approx(0.03252247488101534)
    assert scores["b"] == pytest.approx(1 / 62)
    assert scores["c"] == pytest.approx(0.032266458495966696)
    assert [item for item, _ in ranked] == ["a", "c", "b"]


def test_rrf_item_absent_from_one_ranking_only_counts_the_other() -> None:
    dense = {"a": 1.0}
    sparse = {"a": 1.0, "b": 1.0}
    ranked = fuse(dense, sparse, method="rrf", rrf_k=60)
    scores = dict(ranked)
    # "b" ties with "a" in the sparse ranking, so they SHARE rank 1 (competition ranking).
    # The previous version of this test asserted 1/62 -- "tied with 'a' but sorted after it
    # -> rank 2" -- which encoded the defect as the expectation: rank order was falling back
    # to dict insertion order, i.e. the line order of sparse_weights.jsonl. (M8 checker.)
    assert scores["b"] == pytest.approx(1 / 61)


def test_unknown_method_rejected() -> None:
    with pytest.raises(ValueError):
        fuse(DENSE, SPARSE, method="bogus")  # type: ignore[arg-type]


def test_tied_scores_rank_identically_across_hash_seeds() -> None:
    """Fusion must be deterministic, or no AC-5.1 number can be reproduced.

    Equal-scoring items used to come out of a set, so their order followed Python's
    per-process hash randomisation: the same query gave four different top-6 orders under
    four PYTHONHASHSEED values. Re-running the eval could then move a reel in or out of the
    top 10 with nothing changed. Ties are guaranteed here, not incidental -- `_ranks` gives
    tied scores the same rank by design. (Found by code review.)
    """
    dense = {f"doc{i}": 0.5 for i in range(6)}
    sparse = {f"doc{i}": 0.5 for i in range(6)}
    ranked = [item for item, _ in fuse(dense, sparse, method="rrf")]
    assert ranked == sorted(ranked), "a tie must resolve by item_id, not by hash order"
    assert ranked == [item for item, _ in fuse(dense, sparse, method="rrf")]


def test_weighted_sum_ties_are_deterministic_too() -> None:
    dense = {"z": 1.0, "a": 1.0, "m": 1.0}
    sparse = {"z": 1.0, "a": 1.0, "m": 1.0}
    assert [i for i, _ in fuse(dense, sparse, method="weighted_sum")] == ["a", "m", "z"]
