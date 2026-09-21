"""Stratified sampling: floor respected, seeded and reproducible, frozen across restarts."""

from __future__ import annotations

from pathlib import Path

import pytest

from reelkb.contract.cards import Card, load_cards
from reelkb.contract.curation import load_curation
from reelkb.contract.db import connect_readonly, connect_stage
from reelkb.label.sampling import (
    UnstratifiableError,
    load_or_create_sample,
    stratified_sample,
)
from reelkb.testing.fake_db import REELS, build


@pytest.fixture
def fake_cards(tmp_path: Path) -> list[Card]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    build(data_dir)
    conn = connect_readonly(data_dir / "kb.db")
    return load_cards(conn, load_curation(data_dir))


def _make_card(item_id: str, category_id: str) -> Card:
    return Card(
        item_id=item_id,
        url=f"https://example.com/{item_id}",
        title="t",
        summary="s",
        bullets=[],
        source_account=None,
        sent_at="2024-01-01T00:00:00+00:00",
        category_id=category_id,
        category_name=None,
        language="en",
        caption="c",
        on_screen_text="",
        transcript="",
    )


def test_small_fake_corpus_floor_degenerates_to_take_everything(fake_cards: list[Card]) -> None:
    """Every category in the 27-item fake corpus is smaller than the floor (10), so the
    stratified sample should just be the entire corpus."""
    result = stratified_sample(fake_cards, target=150, floor=10, seed=1)
    assert sorted(result) == sorted(r.item_id for r in REELS)


def test_floor_is_respected_when_categories_have_room(fake_cards: list[Card]) -> None:
    """A synthetic corpus where the floor is comfortably satisfiable: every category with
    at least ``floor`` items keeps at least ``floor`` in the sample, and a category with
    fewer than ``floor`` items keeps all of them."""
    cards = (
        [_make_card(f"a{i}", "a") for i in range(5)]
        + [_make_card(f"b{i}", "b") for i in range(3)]
        + [_make_card(f"c{i}", "c") for i in range(30)]
        + [_make_card(f"d{i}", "d") for i in range(20)]
    )
    result = stratified_sample(cards, target=40, floor=10, seed=7)
    assert len(result) == len(set(result)) == 40

    by_category = {"a": 0, "b": 0, "c": 0, "d": 0}
    for item_id in result:
        by_category[item_id[0]] += 1

    assert by_category["a"] == 5  # smaller than the floor: all of it
    assert by_category["b"] == 3  # smaller than the floor: all of it
    assert by_category["c"] >= 10  # at least the floor
    assert by_category["d"] >= 10  # at least the floor


def test_sampling_is_seeded_and_reproducible(fake_cards: list[Card]) -> None:
    a = stratified_sample(fake_cards, seed=42)
    b = stratified_sample(fake_cards, seed=42)
    assert a == b


def test_different_seeds_can_differ(fake_cards: list[Card]) -> None:
    # Not a hard guarantee for every possible corpus, but true for this one and catches a
    # sampler that ignores its seed entirely.
    a = stratified_sample(fake_cards, seed=1)
    b = stratified_sample(fake_cards, seed=2)
    assert a != b or len(fake_cards) < 2


def test_sample_is_frozen_to_disk_and_stable_across_restarts(
    tmp_path: Path, fake_cards: list[Card]
) -> None:
    data_dir = tmp_path / "data"
    first = load_or_create_sample(data_dir, fake_cards)
    assert (data_dir / "holdout_sample.json").exists()

    # Simulate "restart": call again with a differently-ordered card list. The frozen file
    # must win, not a fresh (and differently seeded-shuffle) computation.
    second = load_or_create_sample(data_dir, list(reversed(fake_cards)))
    assert first == second


def test_a_holdout_cannot_be_frozen_before_the_classifier_has_run(tmp_path: Path) -> None:
    """§7 wants the 150 stratified by category, but categories only exist after classify.

    The plan's Wave 2 order is taxonomy (M6) -> label -> classify (M7), so an empty
    classification table is the EXPECTED state on the owner's first visit. Sampling then puts
    every card in one bucket and freezes that to disk permanently. The M7 checker measured 9
    of 14 categories falling below the floor of 10, with one getting zero items and no warning.
    """
    cards = [
        Card(
            item_id=f"item-{i}",
            url="",
            title="t",
            summary="s",
            bullets=[],
            source_account=None,
            sent_at="2026-01-01",
            category_id=None,  # nothing classified yet
            category_name=None,
            language="en",
            caption="",
            on_screen_text="",
            transcript="",
        )
        for i in range(30)
    ]
    with pytest.raises(UnstratifiableError, match="classify"):
        load_or_create_sample(tmp_path, cards)
    assert not (tmp_path / "holdout_sample.json").exists(), "a refused sample must not be frozen"


def test_the_labelling_page_explains_the_block_instead_of_returning_500(tmp_path: Path) -> None:
    """The remediation text is the whole value of the error; a 500 hides it."""
    from fastapi.testclient import TestClient

    from reelkb.label.app import create_app
    from reelkb.testing.fake_db import build

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    build(data_dir)
    with connect_stage(data_dir / "kb.db", "classify") as conn:
        conn.execute("DELETE FROM classification")
    (data_dir / "holdout_sample.json").unlink(missing_ok=True)

    response = TestClient(create_app(data_dir), raise_server_exceptions=False).get("/holdout")
    assert response.status_code == 409
    assert "classify" in response.text
