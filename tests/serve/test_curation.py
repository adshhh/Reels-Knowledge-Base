"""AC-1.3 (UI side): hiding a card removes it from feeds, search results and category counts;
edits and category changes show up; all of it survives rebuilding the fake DB, because
curation lives in curation.jsonl/corrections.jsonl next to the database, never inside it.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from reelkb.serve.app import create_app
from reelkb.testing.fake_db import build


def test_hidden_card_disappears_from_feed_and_search(client: TestClient) -> None:
    # FAKEml001 lives in category "ml-courses" and matches the query "course".
    assert "Free deep learning course" in client.get("/category/ml-courses").text
    assert "Free deep learning course" in client.get("/search", params={"q": "course"}).text

    client.post("/item/FAKEml001/hide")

    assert "Free deep learning course" not in client.get("/category/ml-courses").text
    assert "Free deep learning course" not in client.get("/search", params={"q": "course"}).text
    # Detail view still works for a hidden item (that's how you get to Unhide).
    assert client.get("/item/FAKEml001").status_code == 200
    assert "Free deep learning course" in client.get("/hidden").text


def test_unhide_restores_the_card(client: TestClient) -> None:
    client.post("/item/FAKEml001/hide")
    assert "Free deep learning course" not in client.get("/category/ml-courses").text

    client.post("/item/FAKEml001/unhide")
    assert "Free deep learning course" in client.get("/category/ml-courses").text
    assert "Free deep learning course" not in client.get("/hidden").text


def test_edit_title_and_summary_shows_up_everywhere(client: TestClient) -> None:
    client.post(
        "/item/FAKEml001/edit",
        data={"title": "A whole new title", "summary": "A whole new summary"},
    )
    detail = client.get("/item/FAKEml001").text
    assert "A whole new title" in detail
    assert "A whole new summary" in detail
    assert "A whole new title" in client.get("/category/ml-courses").text


def test_category_change_moves_the_card_between_feeds(client: TestClient) -> None:
    assert "Free deep learning course" in client.get("/category/ml-courses").text
    assert "Free deep learning course" not in client.get("/category/career").text

    client.post("/item/FAKEml001/category", data={"category_id": "career"})

    assert "Free deep learning course" not in client.get("/category/ml-courses").text
    assert "Free deep learning course" in client.get("/category/career").text


def test_curation_survives_rebuilding_the_fake_db(data_dir: Path, client: TestClient) -> None:
    client.post("/item/FAKEml001/hide")
    client.post("/item/FAKEml002/edit", data={"title": "Kept across rebuild", "summary": "kept"})
    client.post("/item/FAKEml003/category", data={"category_id": "career"})

    build(data_dir)  # re-run every pipeline stage from scratch; curation files are untouched

    fresh_client = TestClient(create_app(data_dir))
    assert "Free deep learning course" not in fresh_client.get("/category/ml-courses").text
    assert "Kept across rebuild" in fresh_client.get("/item/FAKEml002").text
    assert "Five GitHub repos" in fresh_client.get("/category/career").text
