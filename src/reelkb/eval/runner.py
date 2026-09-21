"""The evaluation logic behind ``python -m reelkb.eval`` (AC-7.1), split from ``__main__.py``
so every threshold check is directly unit-testable without going through a subprocess.

Two independent evaluations, matching the two locked plan sections:

- ``run_classification_eval`` -- AC-4.1 / AC-CAT (§4), against ``classification`` in the
  database.
- ``run_search_eval`` -- AC-5.1 / AC-5.2 / AC-SEARCH (§5), against a live ``Searcher``.

Both return a list of ``Threshold`` (name, measured value, PASS/FAIL) plus whatever
qid-level detail AC-7.1 asks the CLI to print. Neither one ever touches item content in its
output -- only category ids (which are taxonomy labels, not archive content) and qids.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from reelkb.contract.cards import load_cards
from reelkb.contract.curation import Curation
from reelkb.contract.search_api import Searcher
from reelkb.eval.fixtures import FixtureError, HoldoutItem, Query
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
from reelkb.search.dense import DenseIndex
from reelkb.search.encoder import Encoder
from reelkb.search.index import HybridSearcher
from reelkb.search.sparse import SparseIndex, load_sparse_weights

# AC-4.1 thresholds (§4)
TOP1_MIN = 0.80
TOP1_OR_TOP2_MIN = 0.92
PER_CATEGORY_RECALL_MIN = 0.60
PER_CATEGORY_FLOOR_COUNT = 10  # the recall floor only applies to categories with >= this many
KAPPA_MIN = 0.60
OTHER_SHARE_MAX = 0.15

# AC-5.1 thresholds (§5)
RECALL_AT_10_MIN = 0.85
NDCG_AT_10_MIN = 0.60
MRR_AT_10_MIN = 0.70


@dataclass(frozen=True)
class Threshold:
    name: str
    value: float
    minimum: float | None = None
    maximum: float | None = None

    @property
    def passed(self) -> bool:
        if self.minimum is not None and self.value < self.minimum:
            return False
        if self.maximum is not None and self.value > self.maximum:
            return False
        return True

    def line(self) -> str:
        bound = f">= {self.minimum:.2f}" if self.minimum is not None else f"<= {self.maximum:.2f}"
        verdict = "PASS" if self.passed else "FAIL"
        return f"[{verdict}] {self.name}: {self.value:.4f} (needs {bound})"


@dataclass(frozen=True)
class ClassificationResult:
    thresholds: list[Threshold]

    @property
    def passed(self) -> bool:
        return all(t.passed for t in self.thresholds)


@dataclass(frozen=True)
class SearchResult:
    thresholds: list[Threshold]
    zero_recall_qids: list[str] = field(default_factory=list)
    canary_qids: list[str] = field(default_factory=list)
    canary_failure_qids: list[str] = field(default_factory=list)
    unjudged_qids: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            all(t.passed for t in self.thresholds)
            and not self.zero_recall_qids
            and not self.canary_failure_qids
            and not self.unjudged_qids
        )


HOLDOUT_SIZE = 150
HOLDOUT_SIZE_TOLERANCE = 15  # §7 says "150 reels"; allow a little slack, not an order of magnitude


def check_holdout_shape(
    holdout: list[HoldoutItem], lookup: dict[str, str], *, enforce_size: bool = True
) -> None:
    """Refuse a holdout that cannot support the claim AC-4.1 makes about it.

    AC-4.1 is not a statement about "whatever was labelled" -- it is a statement about a
    150-item sample, stratified, with every category floored at ~10 so per-category recall is
    measurable. Without these checks the eval degrades quietly in the flattering direction,
    which the M7 checker demonstrated three ways:

    * a 3-item holdout printed four green AC-4.1 thresholds;
    * a 1-item holdout did too;
    * and because per-category thresholds are only emitted for categories with >= 10 items, a
      degenerate fixture emits *fewer* checks -- so a broken holdout is easier to pass than a
      real one. The first thing to disappear is the per-category recall floor.

    Raises ``FixtureError`` with something the owner can act on; never warns and continues.
    """
    hids = [item.hid for item in holdout]
    duplicate_hids = sorted({hid for hid in hids if hids.count(hid) > 1})
    if duplicate_hids:
        raise FixtureError(
            f"duplicate hid(s) in the holdout: {', '.join(duplicate_hids[:5])} -- "
            f"every metric would count those reels more than once"
        )

    by_item: dict[str, list[str]] = {}
    for hid in hids:
        item_id = lookup.get(hid)
        if item_id is not None:
            by_item.setdefault(item_id, []).append(hid)
    repeated = sorted(hid_list[0] for hid_list in by_item.values() if len(hid_list) > 1)
    if repeated:
        raise FixtureError(
            f"{len(repeated)} holdout row(s) point at the same item under different hids "
            f"(e.g. {repeated[0]}). This is what a rotated eval_salt looks like: the older "
            f"rows are orphans. Every metric would double-count those reels."
        )

    if enforce_size and abs(len(holdout) - HOLDOUT_SIZE) > HOLDOUT_SIZE_TOLERANCE:
        raise FixtureError(
            f"holdout has {len(holdout)} items; AC-4.1 (§7) is defined over {HOLDOUT_SIZE}. "
            f"A smaller holdout does not merely weaken the result -- it emits fewer "
            f"per-category thresholds, so it is easier to pass. Finish labelling first."
        )


def run_classification_eval(
    conn: sqlite3.Connection, holdout: list[HoldoutItem], lookup: dict[str, str]
) -> ClassificationResult:
    """AC-4.1 / AC-CAT: classifier quality against the frozen, hand-labelled holdout.

    ``lookup`` resolves each holdout ``hid`` back to a real item_id (§7) -- it must exist on
    this machine (``data/eval_lookup.json``) or a ``FixtureError`` explains why nothing ran.
    """
    resolved: list[tuple[str, str]] = []
    missing_hids: list[str] = []
    for item in holdout:
        item_id = lookup.get(item.hid)
        if item_id is None:
            missing_hids.append(item.hid)
        else:
            resolved.append((item_id, item.category_id))
    if missing_hids:
        raise FixtureError(
            f"{len(missing_hids)} holdout hid(s) not found in the local lookup table -- "
            "run this on the machine that created data/eval_lookup.json"
        )

    class_rows = {
        r["item_id"]: r
        for r in conn.execute("SELECT item_id, category_id, runner_up_id FROM classification")
    }
    predicted: list[str] = []
    top2: list[str | None] = []
    true: list[str] = []
    unclassified: list[str] = []
    for item_id, true_category in resolved:
        row = class_rows.get(item_id)
        if row is None:
            unclassified.append(item_id)
            continue
        predicted.append(row["category_id"])
        top2.append(row["runner_up_id"])
        true.append(true_category)
    if unclassified:
        raise FixtureError(
            f"{len(unclassified)} holdout item(s) have no row in `classification` -- "
            "run the classify stage first"
        )

    all_categories = [
        r["category_id"] for r in conn.execute("SELECT category_id FROM classification")
    ]
    holdout_counts = Counter(true)
    recall_by_category = per_category_recall(predicted, true)
    floored = sorted(cat for cat, n in holdout_counts.items() if n >= PER_CATEGORY_FLOOR_COUNT)

    thresholds = [
        Threshold(
            "AC-4.1 top-1 category accuracy", top1_accuracy(predicted, true), minimum=TOP1_MIN
        ),
        Threshold(
            "AC-4.1 top-1-or-top-2 category accuracy",
            top1_or_top2_accuracy(predicted, top2, true),
            minimum=TOP1_OR_TOP2_MIN,
        ),
        Threshold("AC-4.1 Cohen's kappa", cohens_kappa(predicted, true), minimum=KAPPA_MIN),
        Threshold(
            "AC-4.1 'other' share of corpus", other_share(all_categories), maximum=OTHER_SHARE_MAX
        ),
    ]
    for category in floored:
        thresholds.append(
            Threshold(
                f"AC-4.1 per-category recall [{category}] (n={holdout_counts[category]})",
                recall_by_category.get(category, 0.0),
                minimum=PER_CATEGORY_RECALL_MIN,
            )
        )
    return ClassificationResult(thresholds=thresholds)


def build_hybrid_searcher(
    data_dir: Path,
    conn: sqlite3.Connection,
    curation: Curation,
    *,
    encoder: Encoder | None = None,
    fusion_method: str = "weighted_sum",
    alpha: float = 0.5,
    rrf_k: int = 60,
) -> HybridSearcher:
    """Load the real (or injected) vector files into a ready-to-query ``HybridSearcher``."""
    embeddings_path = data_dir / "embeddings.npy"
    sparse_path = data_dir / "sparse_weights.jsonl"
    if not embeddings_path.exists():
        raise FileNotFoundError(
            f"missing {embeddings_path} -- run `python -m reelkb.search.embed` first"
        )
    matrix = np.load(embeddings_path)
    rows = conn.execute("SELECT row, item_id FROM embedding_rows ORDER BY row").fetchall()
    item_ids = [r["item_id"] for r in rows]
    dense_index = DenseIndex(item_ids, matrix)
    sparse_index = SparseIndex(load_sparse_weights(sparse_path))
    # include_hidden=True deliberately. The searcher's card snapshot is taken once at
    # startup, but `curation.hidden` is re-read on every request and re-checked inside
    # `HybridSearcher.search`. Snapshotting without hidden items meant unhiding one never
    # brought it back to search until the server restarted -- and the dumb SubstringSearcher
    # fallback got this right, so the real engine behaved worse than the test double.
    # (Code review, finding 4.) Hidden items are still never returned: the live check does it.
    cards = load_cards(conn, curation, include_hidden=True)

    if encoder is None:
        from reelkb.search.embed import (
            BGEM3Encoder,
        )  # local import: real model, never at import time

        encoder = BGEM3Encoder()

    return HybridSearcher(
        cards,
        dense_index,
        sparse_index,
        encoder,
        fusion_method=fusion_method,  # type: ignore[arg-type]
        alpha=alpha,
        rrf_k=rrf_k,
    )


# Placeholder hid for a retrieved item the fixtures have never seen. Never a real hid, so
# it scores 0 in every metric while still occupying its rank.
_UNPOOLED = "__unpooled_rank_"


def run_search_eval(
    searcher: Searcher, curation: Curation, queries: list[Query], lookup: dict[str, str]
) -> SearchResult:
    """AC-5.1 / AC-5.2 / AC-SEARCH: run every query, grade against its judgements."""
    reverse_lookup = {item_id: hid for hid, item_id in lookup.items()}
    per_query_recall: dict[str, float] = {}
    per_query_ndcg: dict[str, float] = {}
    per_query_mrr: dict[str, float] = {}
    canary_qids: list[str] = []

    unjudged_qids: list[str] = []
    canary_failures: list[str] = []

    for q in queries:
        hits = searcher.search(q.query, curation, k=10)
        # Every hit keeps its rank, including hits the fixtures have never heard of. Resolving
        # only pooled items and dropping the rest COMPACTS the ranking: an unpooled item at
        # rank 1 vanishes and everything below it moves up, so the score improves. Worse, it
        # improves precisely when the retrieval config changes and brings in items the judging
        # pool never saw -- the eval would reward drift as if it were progress. Measured by the
        # M8 checker on a worked example: reported MRR 1.0 against a true 0.2.
        # An unknown hid scores 0 in every metric (`judgements.get(hid, 0)`), which is exactly
        # what §7 says about unjudged items; the index keeps the placeholders distinct so a
        # repeated one can never be counted as a relevant hit twice.
        ranked_hids = [
            reverse_lookup.get(h.item_id, f"{_UNPOOLED}{rank}") for rank, h in enumerate(hits)
        ]

        if q.canary_hids:
            missing = [hid for hid in q.canary_hids if hid not in ranked_hids[:10]]
            if missing:
                canary_failures.append(q.qid)
        if q.canary or q.canary_hids:
            canary_qids.append(q.qid)

        if not any(grade >= 1 for grade in q.judgements.values()):
            # No relevant item means recall_at_k returns 1.0 by convention -- a free pass that
            # would drag the average UP. A query nobody has judged is not evidence of anything,
            # so it is excluded from the averages and reported instead. (M8 checker, finding 6.)
            unjudged_qids.append(q.qid)
            continue

        per_query_recall[q.qid] = recall_at_k(ranked_hids, q.judgements, k=10)
        per_query_ndcg[q.qid] = ndcg_at_k(ranked_hids, q.judgements, k=10)
        per_query_mrr[q.qid] = mrr_at_k(ranked_hids, q.judgements, k=10)

    n = len(per_query_recall)
    avg_recall = sum(per_query_recall.values()) / n if n else 0.0
    avg_ndcg = sum(per_query_ndcg.values()) / n if n else 0.0
    avg_mrr = sum(per_query_mrr.values()) / n if n else 0.0
    zero_recall = zero_recall_queries(per_query_recall)
    # A canary query with no named reel still fails on zero recall, as before.
    canary_failures = sorted(set(canary_failures) | (set(canary_qids) & set(zero_recall)))

    thresholds = [
        Threshold("AC-5.1 Recall@10", avg_recall, minimum=RECALL_AT_10_MIN),
        Threshold("AC-5.1 nDCG@10", avg_ndcg, minimum=NDCG_AT_10_MIN),
        Threshold("AC-5.1 MRR@10", avg_mrr, minimum=MRR_AT_10_MIN),
    ]
    return SearchResult(
        thresholds=thresholds,
        zero_recall_qids=zero_recall,
        canary_qids=sorted(canary_qids),
        canary_failure_qids=canary_failures,
        unjudged_qids=sorted(unjudged_qids),
    )
