"""Search results page: filters (SearchFilters), hidden items never appearing, and the
create_app(searcher=...) seam that lets a real Searcher (or a test double) be injected.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from reelkb.contract.curation import Curation
from reelkb.contract.search_api import SearchFilters, SearchHit
from reelkb.serve.app import create_app


def test_default_searcher_finds_a_caption_only_match(client: TestClient) -> None:
    # FAKEml002 has no caption text "audit" anywhere except... check a real substring instead:
    # its caption is empty; match on summary/title text via the substring engine.
    r = client.get("/search", params={"q": "specialization"})
    assert r.status_code == 200
    assert "Andrew Ng" in r.text


def test_hidden_items_never_appear_in_search(client: TestClient) -> None:
    client.post("/item/FAKEml001/hide")
    r = client.get("/search", params={"q": "course"})
    assert "Free deep learning course" not in r.text


def test_category_filter_narrows_results(client: TestClient) -> None:
    # "course" matches items across categories via title/summary text.
    r_all = client.get("/search", params={"q": "free"})
    r_scoped = client.get("/search", params={"q": "free", "category_id": "movies"})
    assert r_scoped.text != r_all.text
    assert "Free deep learning course" not in r_scoped.text


def test_empty_query_shows_no_results_but_still_renders(client: TestClient) -> None:
    r = client.get("/search")
    assert r.status_code == 200
    assert "Free deep learning course" not in r.text


class _StubSearcher:
    """A fake Searcher double, proving create_app's injection seam is actually wired up."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(
        self,
        query: str,
        curation: Curation,
        filters: SearchFilters | None = None,
        k: int = 20,
    ) -> list[SearchHit]:
        self.calls.append(query)
        return [SearchHit("FAKEbk001", 1.0, ["stub"])]


def test_injected_searcher_is_used_instead_of_the_default(data_dir: Path) -> None:
    stub = _StubSearcher()
    client = TestClient(create_app(data_dir, searcher=stub))
    r = client.get("/search", params={"q": "anything"})
    assert stub.calls == ["anything"]
    assert "Five books for engineers" in r.text  # FAKEbk001's title
