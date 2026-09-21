"""What a search call looks like, agreed between the search engine and the web app.

The real engine (reelkb.search, M8) implements ``Searcher`` with hybrid BGE-M3 retrieval.
Until it exists, the web app builds against ``reelkb.testing.fake_search.SubstringSearcher``.
Hidden items must never be returned (D15); callers pass the current Curation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from reelkb.contract.curation import Curation


@dataclass(frozen=True)
class SearchFilters:
    category_id: str | None = None
    source_account: str | None = None
    date_from: str | None = None  # ISO date, inclusive
    date_to: str | None = None  # ISO date, inclusive
    language: str | None = None
    unreadable_only: bool = False


@dataclass(frozen=True)
class SearchHit:
    item_id: str
    score: float  # higher is better; only comparable within one result list
    matched_on: list[str] = field(default_factory=list)  # e.g. ["on-screen text", "speech"]


class Searcher(Protocol):
    def search(
        self, query: str, curation: Curation, filters: SearchFilters | None = None, k: int = 20
    ) -> list[SearchHit]: ...
