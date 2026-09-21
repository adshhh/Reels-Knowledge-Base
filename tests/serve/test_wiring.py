"""The running app uses the REAL search engine when an index exists.

Regression test for the gap the M9/M10 checker found: `create_app` falls back to the dumb
`SubstringSearcher` when handed no searcher, and nothing ever handed it one -- so the product
would have shipped with the test double on real data while every test stayed green.

No model is loaded here: `FakeEncoder` stands in for BGE-M3, which is what makes this a unit
test rather than a realmodel test (AC-6.2).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reelkb.contract.curation import Curation, hide, load_curation, unhide
from reelkb.search.embed import run_embed
from reelkb.search.encoder import FakeEncoder
from reelkb.search.index import HybridSearcher
from reelkb.serve.wiring import make_searcher
from reelkb.testing.fake_db import build
from reelkb.testing.fake_search import SubstringSearcher


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


def test_without_an_index_it_falls_back_and_says_so_loudly(data_dir: Path) -> None:
    searcher, note = make_searcher(data_dir)
    assert searcher is None  # the app then uses its own fallback
    assert "WARNING" in note
    assert "reelkb.search.embed" in note  # tells the reader how to fix it
    assert "AC-SEARCH" in note  # and what it costs them meanwhile


def test_with_an_index_it_returns_the_real_hybrid_engine(data_dir: Path) -> None:
    run_embed(data_dir, encoder=FakeEncoder(dim=32))

    searcher, note = make_searcher(data_dir, encoder=FakeEncoder(dim=32))

    assert isinstance(searcher, HybridSearcher)
    assert not isinstance(searcher, SubstringSearcher)
    assert "hybrid" in note.lower()
    assert "WARNING" not in note


def test_the_real_engine_returned_here_actually_searches(data_dir: Path) -> None:
    run_embed(data_dir, encoder=FakeEncoder(dim=32))
    searcher, _ = make_searcher(data_dir, encoder=FakeEncoder(dim=32))
    assert searcher is not None

    hits = searcher.search("course", Curation(), k=10)

    assert hits, "the wired engine returned nothing for a term that is in the corpus"
    assert all(h.item_id.startswith("FAKE") for h in hits)


def test_unhiding_an_item_brings_it_back_to_search_without_a_restart(tmp_path: Path) -> None:
    """The searcher snapshots cards once at startup; hiding is re-checked on every request.

    Loading that snapshot with hidden items already removed meant an unhidden reel could
    never return to search until the server was restarted -- and the dumb SubstringSearcher
    fallback got this right, so the real engine behaved worse than the test double.
    (Found by code review.)
    """
    build(tmp_path)
    run_embed(tmp_path, encoder=FakeEncoder(dim=32))
    hide(tmp_path, "FAKEml001")

    searcher, _ = make_searcher(tmp_path, encoder=FakeEncoder(dim=32))
    assert searcher is not None

    hidden_ids = [h.item_id for h in searcher.search("learning", load_curation(tmp_path), k=50)]
    assert "FAKEml001" not in hidden_ids, "a hidden item must never be returned"

    unhide(tmp_path, "FAKEml001")
    # Same searcher object, no restart: curation is re-read per request.
    back_ids = [h.item_id for h in searcher.search("learning", load_curation(tmp_path), k=50)]
    assert "FAKEml001" in back_ids
