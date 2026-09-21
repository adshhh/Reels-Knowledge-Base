"""``runner.py``: the AC-4.1 / AC-5.1 checks, exercised against the fake corpus (AC-6.2 --
never a real model). CLI-level behaviour (``python -m reelkb.eval``, exit codes, the
degraded-classifier proof) lives in ``test_main.py``; this file is the pure-function layer
underneath it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from reelkb.contract.curation import Curation, load_curation
from reelkb.contract.db import connect_readonly
from reelkb.contract.search_api import SearchFilters, SearchHit
from reelkb.eval.fixtures import FixtureError, HoldoutItem, Query
from reelkb.eval.ids import hash_id, load_salt
from reelkb.eval.runner import build_hybrid_searcher, run_classification_eval, run_search_eval
from reelkb.search.embed import run_embed
from reelkb.search.encoder import FakeEncoder
from reelkb.testing.fake_db import REELS, build

# ---------------------------------------------------------------------------------------
# run_classification_eval


def _holdout_and_lookup(
    data_dir: Path, item_ids: list[str]
) -> tuple[list[HoldoutItem], dict[str, str]]:
    """Build a holdout list (true label = whatever the fake corpus's classifier already
    says) plus the matching lookup table, exactly as the labelling page + eval harness would
    produce on a real machine (§7)."""
    salt = load_salt(data_dir)
    conn = connect_readonly(data_dir / "kb.db")
    true_categories = dict(
        conn.execute("SELECT item_id, category_id FROM classification").fetchall()
    )
    lookup: dict[str, str] = {}
    holdout: list[HoldoutItem] = []
    for item_id in item_ids:
        hid = hash_id(item_id, salt)
        lookup[hid] = item_id
        holdout.append(HoldoutItem(hid=hid, category_id=true_categories[item_id]))
    return holdout, lookup


def test_run_classification_eval_passes_when_labels_match_the_classifier(tmp_path: Path) -> None:
    build(tmp_path)
    conn = connect_readonly(tmp_path / "kb.db")
    holdout, lookup = _holdout_and_lookup(tmp_path, [r.item_id for r in REELS])

    result = run_classification_eval(conn, holdout, lookup)

    assert result.passed
    values = {t.name: t.value for t in result.thresholds}
    assert values["AC-4.1 top-1 category accuracy"] == pytest.approx(1.0)
    assert values["AC-4.1 top-1-or-top-2 category accuracy"] == pytest.approx(1.0)
    assert values["AC-4.1 Cohen's kappa"] == pytest.approx(1.0)
    # 2 of 27 fake items are "other" (FAKEot001, FAKEot002).
    assert values["AC-4.1 'other' share of corpus"] == pytest.approx(2 / 27)
    # No fake category reaches the 10-item holdout floor, so no per-category row is added.
    assert not any(t.name.startswith("AC-4.1 per-category recall") for t in result.thresholds)


def test_run_classification_eval_fails_thresholds_when_labels_disagree(tmp_path: Path) -> None:
    """The degraded-classifier proof at the pure-function layer: claim every non-'other' item
    actually belongs in 'other', and confirm the thresholds catch it rather than pass anyway."""
    build(tmp_path)
    conn = connect_readonly(tmp_path / "kb.db")
    holdout, lookup = _holdout_and_lookup(tmp_path, [r.item_id for r in REELS])
    wrong_holdout = [
        HoldoutItem(hid=h.hid, category_id="other") if h.category_id != "other" else h
        for h in holdout
    ]

    result = run_classification_eval(conn, wrong_holdout, lookup)

    assert not result.passed
    values = {t.name: t.value for t in result.thresholds}
    assert values["AC-4.1 top-1 category accuracy"] == pytest.approx(2 / 27)


def test_run_classification_eval_raises_when_hid_not_in_lookup(tmp_path: Path) -> None:
    build(tmp_path)
    conn = connect_readonly(tmp_path / "kb.db")
    holdout = [HoldoutItem(hid="deadbeefdeadbeef", category_id="movies")]

    with pytest.raises(FixtureError, match="not found in the local lookup"):
        run_classification_eval(conn, holdout, lookup={})


def test_run_classification_eval_raises_when_item_has_no_classification_row(tmp_path: Path) -> None:
    build(tmp_path)
    conn = connect_readonly(tmp_path / "kb.db")
    salt = load_salt(tmp_path)
    hid = hash_id("NOT-A-REAL-ITEM", salt)
    holdout = [HoldoutItem(hid=hid, category_id="movies")]

    with pytest.raises(FixtureError, match="no row in `classification`"):
        run_classification_eval(conn, holdout, lookup={hid: "NOT-A-REAL-ITEM"})


# ---------------------------------------------------------------------------------------
# build_hybrid_searcher


def test_build_hybrid_searcher_loads_real_vector_files_and_finds_the_canary(
    tmp_path: Path,
) -> None:
    build(tmp_path)
    encoder = FakeEncoder(dim=64)
    n_embedded = run_embed(tmp_path, encoder=encoder)
    assert n_embedded == len(REELS)

    conn = connect_readonly(tmp_path / "kb.db")
    curation = load_curation(tmp_path)
    searcher = build_hybrid_searcher(tmp_path, conn, curation, encoder=encoder)

    hits = searcher.search("flow", curation, k=10)
    assert "FAKEmv001" in [h.item_id for h in hits]


def test_build_hybrid_searcher_raises_clearly_before_embed_has_run(tmp_path: Path) -> None:
    build(tmp_path)
    conn = connect_readonly(tmp_path / "kb.db")
    curation = load_curation(tmp_path)

    with pytest.raises(FileNotFoundError, match="reelkb.search.embed"):
        build_hybrid_searcher(tmp_path, conn, curation, encoder=FakeEncoder(dim=64))


# ---------------------------------------------------------------------------------------
# run_search_eval (against a hand-built stub Searcher, not HybridSearcher -- this is testing
# run_search_eval's own bookkeeping: recall/nDCG/MRR averaging, zero-recall and canary
# detection, not retrieval quality).


@dataclass
class _StubSearcher:
    hits_by_query: dict[str, list[SearchHit]]

    def search(
        self,
        query: str,
        curation: Curation,
        filters: SearchFilters | None = None,
        k: int = 20,
    ) -> list[SearchHit]:
        return self.hits_by_query.get(query, [])[:k]


def test_run_search_eval_computes_metrics_and_flags_zero_recall_canary(tmp_path: Path) -> None:
    salt = load_salt(tmp_path)
    ids = ["item-a", "item-c", "item-d", "item-x", "item-y"]
    hid_a, hid_c, hid_d, hid_x, hid_y = (hash_id(i, salt) for i in ids)
    # item-x and item-y are unjudged corpus items (grade 0 by default, §7) -- included in the
    # lookup so they still occupy ranks in the fused list, unlike an item the eval fixtures
    # have never heard of at all, which run_search_eval can't resolve back to a hid and drops.
    lookup = {hid_a: "item-a", hid_c: "item-c", hid_d: "item-d", hid_x: "item-x", hid_y: "item-y"}

    queries = [
        Query(qid="q-hit", query="good", judgements={hid_a: 2}, canary=False),
        Query(qid="q-canary-miss", query="bad", judgements={hid_c: 2}, canary=True),
        Query(qid="q-partial", query="ok", judgements={hid_d: 1}, canary=False),
    ]
    searcher = _StubSearcher(
        hits_by_query={
            "good": [SearchHit("item-a", 1.0, ["caption"])],
            "bad": [SearchHit("item-x", 1.0, ["caption"])],  # item-c never appears
            "ok": [
                SearchHit("item-x", 1.0, []),
                SearchHit("item-y", 0.9, []),
                SearchHit("item-d", 0.8, ["speech"]),
            ],
        }
    )

    result = run_search_eval(searcher, Curation(), queries, lookup)

    assert result.zero_recall_qids == ["q-canary-miss"]
    assert result.canary_qids == ["q-canary-miss"]
    assert result.canary_failure_qids == ["q-canary-miss"]
    assert not result.passed  # zero-recall alone fails it regardless of averaged thresholds

    values = {t.name: t.value for t in result.thresholds}
    # recall: 1.0, 0.0, 1.0 -> average 2/3
    assert values["AC-5.1 Recall@10"] == pytest.approx(2 / 3)
    # mrr: 1.0, 0.0, 1/3 -> average 4/9
    assert values["AC-5.1 MRR@10"] == pytest.approx((1.0 + 0.0 + 1 / 3) / 3)


def test_run_search_eval_passes_when_every_relevant_item_ranks_first(tmp_path: Path) -> None:
    salt = load_salt(tmp_path)
    hid_a, hid_b = (hash_id(i, salt) for i in ("item-a", "item-b"))
    lookup = {hid_a: "item-a", hid_b: "item-b"}
    queries = [
        Query(qid="q1", query="one", judgements={hid_a: 2}, canary=True),
        Query(qid="q2", query="two", judgements={hid_b: 2}, canary=False),
    ]
    searcher = _StubSearcher(
        hits_by_query={
            "one": [SearchHit("item-a", 1.0, ["caption"])],
            "two": [SearchHit("item-b", 1.0, ["caption"])],
        }
    )

    result = run_search_eval(searcher, Curation(), queries, lookup)

    assert result.passed
    assert result.zero_recall_qids == []
    assert result.canary_failure_qids == []
    values = {t.name: t.value for t in result.thresholds}
    assert values["AC-5.1 Recall@10"] == pytest.approx(1.0)
    assert values["AC-5.1 nDCG@10"] == pytest.approx(1.0)
    assert values["AC-5.1 MRR@10"] == pytest.approx(1.0)
