"""Combining the dense-similarity ranking and the sparse-similarity ranking into one score.

Two methods, chosen independently for this project (see the final report for why):

- ``"weighted_sum"`` (the default): min-max normalise each ranking's raw scores to [0, 1]
  *within this result set*, then combine ``alpha * dense + (1 - alpha) * sparse``. Simple,
  and keeps the two halves comparable even though cosine similarity and lexical-weight dot
  products live on different scales.
- ``"rrf"`` (Reciprocal Rank Fusion): score = sum over rankings of ``1 / (k + rank)``. Scale-
  free by construction -- useful if the raw scores ever turn out to be noisy or miscalibrated
  -- at the cost of ignoring *how much* better one hit is than the next.

Both take item_id -> raw score mappings, one per method, and return a single ranked list of
(item_id, fused_score), highest first. An item present in only one input ranking is still
scored -- min-max normalisation treats a missing item's score as 0 before combining, and RRF
simply skips the ranking it's absent from.
"""

from __future__ import annotations

from typing import Literal

FusionMethod = Literal["weighted_sum", "rrf"]


def _min_max_normalise(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    values = scores.values()
    lo, hi = min(values), max(values)
    if hi == lo:
        # Every item scored identically (including the all-zero case): no information to
        # rank by, so treat every item as equally, maximally relevant rather than dividing
        # by zero.
        return dict.fromkeys(scores, 1.0)
    return {item: (score - lo) / (hi - lo) for item, score in scores.items()}


def _weighted_sum(
    dense_scores: dict[str, float], sparse_scores: dict[str, float], alpha: float
) -> dict[str, float]:
    dense_norm = _min_max_normalise(dense_scores)
    sparse_norm = _min_max_normalise(sparse_scores)
    items = set(dense_norm) | set(sparse_norm)
    return {
        item: alpha * dense_norm.get(item, 0.0) + (1 - alpha) * sparse_norm.get(item, 0.0)
        for item in items
    }


def _ranks(scores: dict[str, float]) -> dict[str, int]:
    """Competition ranks (1, 2, 2, 4) over the items this ranking actually has evidence for.

    Two rules, both of which the first version got wrong (M8 checker, finding 3):

    * **A non-positive score means "absent", not "last".** Sparse similarity is 0 for every
      document sharing no term with the query -- which is most of the corpus. Ranking those
      anyway handed each of them a rank-2, rank-3, rank-4 reward, so documents matching
      *nothing* out-scored the one document matching the query exactly. Measured: the single
      lexical match fell to rank 39 of 200.
    * **Ties share a rank.** With hundreds of identical zero scores, `sorted` is stable, so
      rank order fell back to dict insertion order -- which is the order rows happen to sit in
      `sparse_weights.jsonl`. Search results must not depend on that.
    """
    present = {item: score for item, score in scores.items() if score > 0}
    ordered = sorted(present, key=lambda item: (-present[item], item))
    ranks: dict[str, int] = {}
    previous_score: float | None = None
    rank = 0
    for position, item in enumerate(ordered, start=1):
        if present[item] != previous_score:
            rank = position
            previous_score = present[item]
        ranks[item] = rank
    return ranks


def _rrf(
    dense_scores: dict[str, float], sparse_scores: dict[str, float], k: int
) -> dict[str, float]:
    dense_ranks = _ranks(dense_scores)
    sparse_ranks = _ranks(sparse_scores)
    items = set(dense_ranks) | set(sparse_ranks)
    fused: dict[str, float] = {}
    for item in items:
        score = 0.0
        if item in dense_ranks:
            score += 1.0 / (k + dense_ranks[item])
        if item in sparse_ranks:
            score += 1.0 / (k + sparse_ranks[item])
        fused[item] = score
    return fused


def fuse(
    dense_scores: dict[str, float],
    sparse_scores: dict[str, float],
    method: FusionMethod = "weighted_sum",
    alpha: float = 0.5,
    rrf_k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse two item_id -> raw-score rankings into one ranked (item_id, score) list.

    ``alpha`` (weighted_sum only) is the dense weight; ``1 - alpha`` goes to sparse.
    ``rrf_k`` (rrf only) is the standard RRF smoothing constant (60 in the original paper).
    """
    if method == "weighted_sum":
        fused = _weighted_sum(dense_scores, sparse_scores, alpha)
    elif method == "rrf":
        fused = _rrf(dense_scores, sparse_scores, rrf_k)
    else:  # pragma: no cover - Literal makes this unreachable from typed callers
        raise ValueError(f"unknown fusion method {method!r}")
    # Tie-break on item_id, always. Without it the order of equal-scoring items came from a
    # set, i.e. Python's per-process hash randomisation -- the same query returned four
    # different top-6 orders under four hash seeds. That makes every AC-5.1 number
    # irreproducible: re-running the eval could move a reel in or out of the top 10 with no
    # change to the code, the data or the config. Ties are also now guaranteed rather than
    # incidental, because `_ranks` deliberately gives tied scores the same rank.
    return sorted(fused.items(), key=lambda pair: (-pair[1], pair[0]))
