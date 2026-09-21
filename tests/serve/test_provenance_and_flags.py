"""Provenance on the card, and the unverified-name badge.

Provenance (owner's request): the original reel/post link, the account that sent it and the
date all sit together directly under the title, before the summary, so a card can always be
traced back to the thing it came from. None of it costs anything extra -- all three fields
come from the Instagram export the parser already reads, not from the fetch vendor.

The badge surfaces names the fidelity gate could not confirm against on-screen text. The gate
records them rather than deleting them (DESIGN_RATIONALE #11), so the card must say so.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from reelkb.contract.cards import load_cards
from reelkb.contract.curation import Curation
from reelkb.contract.db import connect_readonly, connect_stage
from reelkb.serve.app import create_app


def _body(client: TestClient, path: str) -> str:
    response = client.get(path)
    assert response.status_code == 200
    return response.text


def test_detail_page_shows_account_date_and_original_link_before_the_summary(
    client: TestClient,
) -> None:
    html = _body(client, "/item/FAKEml001")
    link = html.index("instagram-link")
    summary = html.index('class="summary"')
    assert link < summary, "the original link must sit above the summary, not at the bottom"
    meta = html[html.index('class="meta"') : summary]
    assert "instagram.com" in meta
    assert re.search(r"\d{4}-\d{2}-\d{2}", meta), "the date belongs on the provenance line"


def test_list_pages_also_carry_the_original_link(client: TestClient) -> None:
    """The search page renders the shared card-list partial the category page also uses."""
    assert "instagram-link" in _body(client, "/search?q=learning")


def test_a_card_with_no_url_renders_without_a_dangling_separator(
    client: TestClient, data_dir: Path
) -> None:
    """External/note items have no Instagram URL; the line must simply omit the link."""
    with connect_stage(data_dir / "kb.db", "ingest") as conn:
        conn.execute("UPDATE items SET url = NULL WHERE item_id = 'FAKEml001'")
    html = _body(client, "/item/FAKEml001")
    meta = html[html.index('class="meta"') : html.index('class="summary"')]
    assert "instagram-link" not in meta
    assert "&middot; &middot;" not in " ".join(meta.split())


def _set_flags(db: Path, item_id: str, names: list[str]) -> None:
    payload = json.dumps([{"value": n, "location": "title", "reason": "test"} for n in names])
    with connect_stage(db, "fusion") as conn:
        conn.execute("UPDATE fusion SET unverified_names = ? WHERE item_id = ?", (payload, item_id))


def test_flagged_names_survive_the_round_trip_into_a_card(data_dir: Path) -> None:
    db = data_dir / "kb.db"
    _set_flags(db, "FAKEml001", ["Source Code", "Hulu"])
    cards = {c.item_id: c for c in load_cards(connect_readonly(db), Curation())}
    assert cards["FAKEml001"].unverified_names == ["Source Code", "Hulu"]
    assert cards["FAKEml002"].unverified_names == []


def test_the_badge_appears_only_when_a_name_is_unconfirmed(data_dir: Path) -> None:
    client = TestClient(create_app(data_dir))
    assert "unverified name" not in _body(client, "/item/FAKEml001")

    _set_flags(data_dir / "kb.db", "FAKEml001", ["Source Code", "Hulu"])
    html = _body(TestClient(create_app(data_dir)), "/item/FAKEml001")
    assert "2 unverified names" in html
    assert "Source Code" in html, "the names themselves belong in the badge's tooltip"


def test_the_badge_is_singular_for_one_name(data_dir: Path) -> None:
    _set_flags(data_dir / "kb.db", "FAKEml001", ["Nosferatu"])
    html = _body(TestClient(create_app(data_dir)), "/item/FAKEml001")
    assert "1 unverified name<" in html


def test_the_serving_connection_still_cannot_write_the_new_column(data_dir: Path) -> None:
    """The new column changes nothing about AC-8.2: serving reads, never writes."""
    conn = connect_readonly(data_dir / "kb.db")
    try:
        conn.execute("UPDATE fusion SET unverified_names = '[]'")
    except sqlite3.DatabaseError:
        return
    raise AssertionError("the read-only serving connection wrote to fusion")
