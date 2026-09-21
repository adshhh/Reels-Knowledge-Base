"""AC-1.1: every category is reachable in one click from the landing page, and each shown
count matches a COUNT(*) over non-hidden cards.

Proof note: the plan's proof names Playwright. Playwright is not an approved dependency
(pyproject.toml lists only pytest/ruff/mypy/httpx for dev), so this uses FastAPI's TestClient
(httpx-backed) plus stdlib `html.parser` -- no new dependency, same end-to-end assertion.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from fastapi.testclient import TestClient

from reelkb.contract import curation
from reelkb.contract.db import connect_readonly


class _LandingParser(HTMLParser):
    """Pulls out (category_id, shown_count) for every category link on the landing page."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self._in_count = False
        self._pending_id: str | None = None
        self.counts: dict[str, int] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        if tag == "a" and attrs_d.get("class") == "category-link":
            href = attrs_d.get("href") or ""
            cat_id = href.rsplit("/", 1)[-1]
            self.links.append(cat_id)
            self._pending_id = cat_id
        if tag == "span" and attrs_d.get("class") == "count":
            self._in_count = True

    def handle_data(self, data: str) -> None:
        if self._in_count and self._pending_id is not None:
            self.counts[self._pending_id] = int(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "span":
            self._in_count = False


def _direct_category_counts(db_path: Path, data_dir: Path) -> dict[str, int]:
    """An independent tally: raw SQL over classification+fusion, minus hidden ids from the
    curation log -- computed without going through reelkb.contract.cards.load_cards, so this
    test doesn't just check that the app agrees with itself."""
    conn = connect_readonly(db_path)
    hidden = curation.load_curation(data_dir).hidden
    counts: dict[str, int] = {}
    rows = conn.execute(
        "SELECT c.item_id, c.category_id FROM classification c "
        "JOIN fusion f ON f.item_id = c.item_id"
    ).fetchall()
    for item_id, category_id in rows:
        if item_id in hidden:
            continue
        counts[category_id] = counts.get(category_id, 0) + 1
    all_cats = [r[0] for r in conn.execute("SELECT category_id FROM categories")]
    return {cat: counts.get(cat, 0) for cat in all_cats}


def test_every_category_reachable_with_matching_count(client: TestClient, data_dir: Path) -> None:
    db_path = data_dir / "kb.db"
    n_categories = (
        connect_readonly(db_path).execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    )

    r = client.get("/")
    assert r.status_code == 200
    parser = _LandingParser()
    parser.feed(r.text)

    assert len(parser.links) == n_categories
    assert len(set(parser.links)) == n_categories  # each category exactly once

    expected = _direct_category_counts(db_path, data_dir)
    assert parser.counts == expected

    for cat_id in parser.links:
        page = client.get(f"/category/{cat_id}")
        assert page.status_code == 200


def test_hiding_a_card_changes_its_categorys_count(client: TestClient, data_dir: Path) -> None:
    db_path = data_dir / "kb.db"
    before = _direct_category_counts(db_path, data_dir)

    # FAKEot001 -> category "other"
    client.post("/item/FAKEot001/hide")

    r = client.get("/")
    parser = _LandingParser()
    parser.feed(r.text)

    assert parser.counts["other"] == before["other"] - 1
    for cat_id, count in before.items():
        if cat_id != "other":
            assert parser.counts[cat_id] == count
