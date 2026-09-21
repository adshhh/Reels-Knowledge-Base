"""Cards carry labelled channels (AC-1.2) and curation always wins (AC-1.3, AC-4.3)."""

from pathlib import Path

import pytest

from reelkb.contract import curation
from reelkb.contract.cards import load_cards
from reelkb.contract.db import connect_readonly
from reelkb.testing.fake_db import REELS, build


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    build(tmp_path)
    return tmp_path


def cards(data_dir: Path, **kw: bool) -> dict[str, object]:
    conn = connect_readonly(data_dir / "kb.db")
    return {c.item_id: c for c in load_cards(conn, curation.load_curation(data_dir), **kw)}


def test_only_fused_items_become_cards(data_dir: Path) -> None:
    assert set(cards(data_dir)) == {r.item_id for r in REELS}


def test_no_card_has_zero_channels(data_dir: Path) -> None:
    for card in cards(data_dir).values():
        assert card.channels(), card.item_id  # type: ignore[attr-defined]


def test_channels_are_labelled_and_empty_ones_omitted(data_dir: Path) -> None:
    flow = cards(data_dir)["FAKEmv001"]
    assert [label for label, _ in flow.channels()] == ["Caption", "On-screen text"]  # type: ignore[attr-defined]


def test_hidden_card_disappears_and_edits_win(data_dir: Path) -> None:
    curation.hide(data_dir, "FAKEot001")
    curation.edit(data_dir, "FAKEml001", "title", "My own title")
    curation.correct_category(data_dir, "FAKEot002", "career")
    got = cards(data_dir)
    assert "FAKEot001" not in got
    assert got["FAKEml001"].title == "My own title"  # type: ignore[attr-defined]
    assert got["FAKEot002"].category_id == "career"  # type: ignore[attr-defined]
    assert "FAKEot001" in cards(data_dir, include_hidden=True)


def test_curation_survives_a_full_pipeline_rebuild(data_dir: Path) -> None:
    curation.hide(data_dir, "FAKEot001")
    curation.edit(data_dir, "FAKEml001", "summary", "kept")
    build(data_dir)  # re-running every stage from scratch
    got = cards(data_dir)
    assert "FAKEot001" not in got
    assert got["FAKEml001"].summary == "kept"  # type: ignore[attr-defined]


def test_unhide_restores(data_dir: Path) -> None:
    curation.hide(data_dir, "FAKEot001")
    curation.unhide(data_dir, "FAKEot001")
    assert "FAKEot001" in cards(data_dir)


def test_only_title_and_summary_are_editable(data_dir: Path) -> None:
    with pytest.raises(ValueError):
        curation.edit(data_dir, "FAKEml001", "url", "x")  # type: ignore[arg-type]
