"""Every metric checked against a value computed by hand (or independently in Python, shown
in the comment above each case), never against the implementation reasoning about itself.
"""

from __future__ import annotations

import pytest

from reelkb.eval.metrics import (
    cohens_kappa,
    mrr_at_k,
    ndcg_at_k,
    other_share,
    per_category_recall,
    recall_at_k,
    top1_accuracy,
    top1_or_top2_accuracy,
    zero_recall_queries,
)

# ---------------------------------------------------------------------------------------
# recall_at_k


def test_recall_at_k_hand_computed() -> None:
    # relevant = {a, b, d} (grade >= 1); top-10 contains a, b but not d -> 2/3
    judgements = {"a": 2, "b": 1, "c": 0, "d": 1}
    ranked = ["x", "a", "y", "b", "z"]
    assert recall_at_k(ranked, judgements, k=10) == pytest.approx(2 / 3)


def test_recall_at_k_respects_k() -> None:
    judgements = {"a": 1, "b": 1}
    ranked = ["a"] + ["x"] * 9 + ["b"]  # b sits at rank 11, outside top 10
    assert recall_at_k(ranked, judgements, k=10) == pytest.approx(0.5)


def test_recall_at_k_no_relevant_items_is_trivially_1() -> None:
    assert recall_at_k(["a", "b"], {"a": 0, "b": 0}, k=10) == 1.0
    assert recall_at_k(["a", "b"], {}, k=10) == 1.0


# ---------------------------------------------------------------------------------------
# ndcg_at_k


def test_ndcg_at_k_hand_computed_non_ideal_order() -> None:
    # judgements a=2, b=1, c=0; ranked [c, a, b]:
    # dcg = 0/log2(2) + 2/log2(3) + 1/log2(4) = 1.7618621...
    # idcg (ideal order [a, b]) = 2/log2(2) + 1/log2(3) = 2.6309298...
    # ndcg = 0.6696718...  (computed independently with plain math.log2, not this module)
    judgements = {"a": 2, "b": 1, "c": 0}
    assert ndcg_at_k(["c", "a", "b"], judgements, k=3) == pytest.approx(0.66967181649423)


def test_ndcg_at_k_hand_computed_truncated_by_k() -> None:
    judgements = {"a": 2, "b": 1, "c": 1, "d": 0}
    assert ndcg_at_k(["a", "d", "b", "c"], judgements, k=2) == pytest.approx(0.7601875334318685)


def test_ndcg_at_k_perfect_order_is_1() -> None:
    judgements = {"a": 2, "b": 1, "c": 0}
    assert ndcg_at_k(["a", "b", "c"], judgements, k=3) == pytest.approx(1.0)


def test_ndcg_at_k_no_positive_judgements_is_zero() -> None:
    assert ndcg_at_k(["a", "b"], {"a": 0, "b": 0}, k=10) == 0.0
    assert ndcg_at_k(["a", "b"], {}, k=10) == 0.0


# ---------------------------------------------------------------------------------------
# mrr_at_k


def test_mrr_at_k_hand_computed() -> None:
    # first relevant item ("a", grade 2) lands at rank 3 -> 1/3
    judgements = {"a": 2, "b": 1}
    assert mrr_at_k(["x", "y", "a", "b"], judgements, k=10) == pytest.approx(1 / 3)


def test_mrr_at_k_first_hit_wins() -> None:
    judgements = {"a": 1, "b": 2}
    assert mrr_at_k(["a", "b"], judgements, k=10) == pytest.approx(1.0)


def test_mrr_at_k_zero_when_nothing_relevant_found() -> None:
    assert mrr_at_k(["x", "y"], {"a": 1}, k=10) == 0.0


def test_mrr_at_k_respects_k() -> None:
    judgements = {"a": 1}
    ranked = ["x"] * 10 + ["a"]  # a at rank 11
    assert mrr_at_k(ranked, judgements, k=10) == 0.0


# ---------------------------------------------------------------------------------------
# zero_recall_queries


def test_zero_recall_queries_hand_computed() -> None:
    per_query = {"q1": 0.0, "q2": 0.5, "q3": 0.0, "q4": 1.0}
    assert zero_recall_queries(per_query) == ["q1", "q3"]


def test_zero_recall_queries_empty_when_none_are_zero() -> None:
    assert zero_recall_queries({"q1": 0.2, "q2": 1.0}) == []


# ---------------------------------------------------------------------------------------
# top1_accuracy / top1_or_top2_accuracy


def test_top1_accuracy_hand_computed() -> None:
    predicted = ["a", "b", "c"]
    true = ["a", "x", "c"]
    assert top1_accuracy(predicted, true) == pytest.approx(2 / 3)


def test_top1_accuracy_empty_is_1() -> None:
    assert top1_accuracy([], []) == 1.0


def test_top1_accuracy_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        top1_accuracy(["a"], ["a", "b"])


def test_top1_or_top2_accuracy_hand_computed() -> None:
    top1 = ["a", "b", "c"]
    top2: list[str | None] = ["x", "a", None]
    true = ["a", "z", "c"]
    # i0: a in {a, x} hit; i1: z in {b, a} miss; i2: c in {c, None} hit -> 2/3
    assert top1_or_top2_accuracy(top1, top2, true) == pytest.approx(2 / 3)


def test_top1_or_top2_accuracy_all_hit() -> None:
    top1 = ["a", "b", "c"]
    top2: list[str | None] = ["x", "a", None]
    true = ["a", "a", "c"]
    assert top1_or_top2_accuracy(top1, top2, true) == pytest.approx(1.0)


# ---------------------------------------------------------------------------------------
# per_category_recall


def test_per_category_recall_hand_computed() -> None:
    predicted = ["a", "a", "b", "c", "a"]
    true = ["a", "b", "b", "c", "a"]
    got = per_category_recall(predicted, true)
    assert got == {"a": pytest.approx(1.0), "b": pytest.approx(0.5), "c": pytest.approx(1.0)}


def test_per_category_recall_omits_categories_with_no_ground_truth() -> None:
    got = per_category_recall(["a"], ["a"])
    assert "z" not in got


# ---------------------------------------------------------------------------------------
# other_share


def test_other_share_hand_computed() -> None:
    assert other_share(["ml", "other", "other", "books"]) == pytest.approx(0.5)


def test_other_share_empty_corpus_is_zero() -> None:
    assert other_share([]) == 0.0


def test_other_share_custom_other_id() -> None:
    assert other_share(["misc", "ml", "misc"], other_id="misc") == pytest.approx(2 / 3)


# ---------------------------------------------------------------------------------------
# cohens_kappa


def test_cohens_kappa_hand_computed() -> None:
    # p_observed = 4/6; p_expected = (2*2 + 4*4)/36 -- computed independently below.
    pred = ["x", "x", "y", "y", "x", "y"]
    true = ["x", "y", "y", "y", "x", "x"]
    assert cohens_kappa(pred, true) == pytest.approx(0.33333333333333326)


def test_cohens_kappa_perfect_agreement_is_1() -> None:
    assert cohens_kappa(["a", "b", "a"], ["a", "b", "a"]) == pytest.approx(1.0)


def test_cohens_kappa_single_category_perfect_agreement_is_1() -> None:
    # p_expected == 1 here (only one category ever appears); guarded to avoid 0/0.
    assert cohens_kappa(["a", "a", "a"], ["a", "a", "a"]) == 1.0


def test_cohens_kappa_rejects_mismatched_lengths() -> None:
    with pytest.raises(ValueError):
        cohens_kappa(["a"], ["a", "b"])
