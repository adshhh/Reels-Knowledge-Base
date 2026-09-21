"""HybridSearcher over the fake corpus with FakeEncoder -- never loads a real model (AC-6.2).

Includes the AC-5.2 canary machinery: FAKEmv001 (the Flow-style reel) is findable by a query
whose words never appear in its caption, because the sparse half matches the on-screen text.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reelkb.contract import curation as curation_mod
from reelkb.contract.cards import load_cards
from reelkb.contract.db import connect_readonly
from reelkb.contract.search_api import SearchFilters
from reelkb.search.card_text import text_for_card
from reelkb.search.dense import DenseIndex
from reelkb.search.encoder import FakeEncoder
from reelkb.search.index import HybridSearcher
from reelkb.search.sparse import SparseIndex
from reelkb.testing.fake_db import build


def _build_searcher(
    data_dir: Path, **kwargs: object
) -> tuple[HybridSearcher, curation_mod.Curation]:
    build(data_dir)
    conn = connect_readonly(data_dir / "kb.db")
    curation = curation_mod.load_curation(data_dir)
    cards = load_cards(conn, curation)
    encoder = FakeEncoder(dim=64)
    texts = [text_for_card(c) for c in cards]
    batch = encoder.encode(texts)
    dense_index = DenseIndex([c.item_id for c in cards], batch.dense)
    sparse_index = SparseIndex({c.item_id: w for c, w in zip(cards, batch.sparse, strict=True)})
    searcher = HybridSearcher(cards, dense_index, sparse_index, encoder, **kwargs)  # type: ignore[arg-type]
    return searcher, curation


@pytest.fixture
def searcher_and_curation(tmp_path: Path) -> tuple[HybridSearcher, curation_mod.Curation]:
    return _build_searcher(tmp_path)


def test_flow_canary_found_by_a_query_absent_from_its_caption(
    tmp_path: Path,
) -> None:
    """AC-5.2: FAKEmv001's caption never says "flow"; only its on-screen text does."""
    searcher, curation = _build_searcher(tmp_path)
    conn = connect_readonly(tmp_path / "kb.db")
    flow_card = {c.item_id: c for c in load_cards(conn, curation)}["FAKEmv001"]
    assert "flow" not in flow_card.caption.lower()  # sanity: this is the hard case
    assert "flow" in flow_card.on_screen_text.lower()

    hits = searcher.search("flow", curation, k=10)
    item_ids = [h.item_id for h in hits]
    assert "FAKEmv001" in item_ids
    hit = next(h for h in hits if h.item_id == "FAKEmv001")
    assert "on-screen text" in hit.matched_on
    assert "caption" not in hit.matched_on


def test_exact_term_match_ranks_above_unrelated_items(
    searcher_and_curation: tuple[HybridSearcher, curation_mod.Curation],
) -> None:
    searcher, curation = searcher_and_curation
    hits = searcher.search("paneer bhurji recipe", curation, k=5)
    assert hits
    assert hits[0].item_id == "FAKEfd001"


def test_hidden_items_never_returned(tmp_path: Path) -> None:
    build(tmp_path)
    curation_mod.hide(tmp_path, "FAKEmv001")
    curation = curation_mod.load_curation(tmp_path)
    conn = connect_readonly(tmp_path / "kb.db")
    cards = load_cards(conn, curation)  # hidden card already excluded from the card list
    encoder = FakeEncoder(dim=64)
    texts = [text_for_card(c) for c in cards]
    batch = encoder.encode(texts)
    dense_index = DenseIndex([c.item_id for c in cards], batch.dense)
    sparse_index = SparseIndex({c.item_id: w for c, w in zip(cards, batch.sparse, strict=True)})
    searcher = HybridSearcher(cards, dense_index, sparse_index, encoder)
    hits = searcher.search("flow", curation, k=10)
    assert "FAKEmv001" not in [h.item_id for h in hits]


def test_hidden_via_curation_alone_also_excluded(
    tmp_path: Path,
) -> None:
    """Even if a hidden item's vector is still in the index, curation.hidden is the wall."""
    searcher, _ = _build_searcher(tmp_path)
    curation_mod.hide(tmp_path, "FAKEmv001")
    curation = curation_mod.load_curation(tmp_path)
    hits = searcher.search("flow", curation, k=10)
    assert "FAKEmv001" not in [h.item_id for h in hits]


def test_category_filter(
    searcher_and_curation: tuple[HybridSearcher, curation_mod.Curation],
) -> None:
    searcher, curation = searcher_and_curation
    hits = searcher.search("free", curation, filters=SearchFilters(category_id="movies"), k=20)
    assert all(h.item_id.startswith("FAKEmv") for h in hits)


def test_language_filter(
    searcher_and_curation: tuple[HybridSearcher, curation_mod.Curation],
) -> None:
    searcher, curation = searcher_and_curation
    hits = searcher.search("movie", curation, filters=SearchFilters(language="hi-Latn"), k=20)
    assert all(h.item_id == "FAKEmv005" for h in hits)


def test_source_account_filter(
    searcher_and_curation: tuple[HybridSearcher, curation_mod.Curation],
) -> None:
    searcher, curation = searcher_and_curation
    hits = searcher.search(
        "course", curation, filters=SearchFilters(source_account="learnwithdata"), k=20
    )
    assert all(h.item_id in {"FAKEml001", "FAKEml006"} for h in hits)


def test_k_limits_result_count(
    searcher_and_curation: tuple[HybridSearcher, curation_mod.Curation],
) -> None:
    searcher, curation = searcher_and_curation
    hits = searcher.search("course free learning", curation, k=2)
    assert len(hits) <= 2


def test_matched_on_lists_channels_that_share_query_words(
    searcher_and_curation: tuple[HybridSearcher, curation_mod.Curation],
) -> None:
    searcher, curation = searcher_and_curation
    hits = searcher.search("paneer bhurji", curation, k=1)
    assert hits
    assert hits[0].matched_on  # something was populated
    assert set(hits[0].matched_on) <= {"title", "summary", "caption", "on-screen text", "speech"}
