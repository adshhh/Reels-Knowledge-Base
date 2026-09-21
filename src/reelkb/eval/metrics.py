"""Pure scoring functions for AC-CAT (§4) and AC-SEARCH (§5).

Nothing here touches a database, a file, or a model -- every function takes plain Python
values in and returns a plain number or list out, so each one is checked against a
hand-computed example in ``tests/eval/test_metrics.py``. ``docs/PLAN.md`` defines each
metric in its own words just above the acceptance criteria that use it.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------------------
# Search metrics (AC-5.1 / AC-SEARCH). A "judgement" maps item_id -> 2 (exactly this) /
# 1 (related) / 0 (irrelevant). Unjudged items are 0 (§7).

RELEVANT_THRESHOLD = 1  # a judgement >= this counts as "relevant" for recall / MRR


def recall_at_k(
    ranked_item_ids: Sequence[str],
    judgements: Mapping[str, int],
    k: int = 10,
    relevant_threshold: int = RELEVANT_THRESHOLD,
) -> float:
    """Fraction of relevant items (judgement >= threshold) that appear in the top k.

    1.0 when there are no relevant items at all -- an empty target set is trivially fully
    recalled, and callers that care about that case check it separately.
    """
    relevant = {item for item, grade in judgements.items() if grade >= relevant_threshold}
    if not relevant:
        return 1.0
    top_k = set(ranked_item_ids[:k])
    return len(relevant & top_k) / len(relevant)


def ndcg_at_k(ranked_item_ids: Sequence[str], judgements: Mapping[str, int], k: int = 10) -> float:
    """Graded nDCG@k: DCG using each item's judgement (0/1/2) as its gain, over ideal DCG.

    0.0 when every judgement is 0 (nothing to rank well), matching the usual convention.
    """
    dcg = 0.0
    for rank, item_id in enumerate(ranked_item_ids[:k], start=1):
        gain = judgements.get(item_id, 0)
        if gain:
            dcg += gain / math.log2(rank + 1)
    ideal_gains = sorted((g for g in judgements.values() if g > 0), reverse=True)[:k]
    idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal_gains, start=1))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def mrr_at_k(
    ranked_item_ids: Sequence[str],
    judgements: Mapping[str, int],
    k: int = 10,
    relevant_threshold: int = RELEVANT_THRESHOLD,
) -> float:
    """1 / (rank of the first relevant item within the top k), or 0.0 if none appears."""
    for rank, item_id in enumerate(ranked_item_ids[:k], start=1):
        if judgements.get(item_id, 0) >= relevant_threshold:
            return 1.0 / rank
    return 0.0


def zero_recall_queries(per_query_recall: Mapping[str, float]) -> list[str]:
    """qids whose Recall@k is exactly 0 -- the AC-5.1 hard-fail list, sorted for stable output."""
    return sorted(qid for qid, recall in per_query_recall.items() if recall == 0.0)


# ---------------------------------------------------------------------------------------
# Classification metrics (AC-4.1 / AC-CAT).


def top1_accuracy(predicted: Sequence[str], true: Sequence[str]) -> float:
    """Fraction of items whose top-1 predicted category equals the human label."""
    if len(predicted) != len(true):
        raise ValueError("predicted and true must be the same length")
    if not true:
        return 1.0
    correct = sum(1 for p, t in zip(predicted, true, strict=True) if p == t)
    return correct / len(true)


def top1_or_top2_accuracy(
    top1: Sequence[str], top2: Sequence[str | None], true: Sequence[str]
) -> float:
    """Fraction of items where the human label is the top-1 OR the runner-up category.

    ``top2[i]`` may be ``None`` (no runner-up recorded), which simply can't satisfy the match.
    """
    if not (len(top1) == len(top2) == len(true)):
        raise ValueError("top1, top2 and true must be the same length")
    if not true:
        return 1.0
    hits = sum(1 for p1, p2, t in zip(top1, top2, true, strict=True) if t in (p1, p2))
    return hits / len(true)


def per_category_recall(predicted: Sequence[str], true: Sequence[str]) -> dict[str, float]:
    """{category_id: recall} -- of holdout items truly in that category, how many were found.

    A category absent from ``true`` never appears in the result: recall is undefined for a
    category with zero ground-truth items, not zero.
    """
    if len(predicted) != len(true):
        raise ValueError("predicted and true must be the same length")
    totals: Counter[str] = Counter(true)
    correct: Counter[str] = Counter()
    for p, t in zip(predicted, true, strict=True):
        if p == t:
            correct[t] += 1
    return {cat: correct[cat] / totals[cat] for cat in totals}


def other_share(category_ids: Iterable[str], other_id: str = "other") -> float:
    """Fraction of the corpus (or holdout) sitting in the quarantine category (AC-4.1)."""
    ids = list(category_ids)
    if not ids:
        return 0.0
    return sum(1 for c in ids if c == other_id) / len(ids)


def cohens_kappa(predicted: Sequence[str], true: Sequence[str]) -> float:
    """Agreement between predicted and true labels, corrected for chance agreement.

    Standard unweighted Cohen's kappa over the confusion matrix implied by the two label
    sequences: kappa = (p_observed - p_expected) / (1 - p_expected).
    Returns 1.0 for a perfect match on a single-category set (p_expected == 1 there too, so
    the usual 0/0 case coincides with total agreement).
    """
    if len(predicted) != len(true):
        raise ValueError("predicted and true must be the same length")
    n = len(true)
    if n == 0:
        return 1.0
    p_observed = sum(1 for p, t in zip(predicted, true, strict=True) if p == t) / n
    pred_counts = Counter(predicted)
    true_counts = Counter(true)
    categories = set(pred_counts) | set(true_counts)
    p_expected = sum(pred_counts[c] * true_counts[c] for c in categories) / (n * n)
    if p_expected == 1.0:
        return 1.0
    return (p_observed - p_expected) / (1 - p_expected)
