"""A deliberately dumb Searcher (case-insensitive substring match) for building the UI."""

from __future__ import annotations

from reelkb.contract.cards import Card
from reelkb.contract.curation import Curation
from reelkb.contract.search_api import SearchFilters, SearchHit


class SubstringSearcher:
    def __init__(self, cards: list[Card]) -> None:
        self._cards = cards

    def search(
        self, query: str, curation: Curation, filters: SearchFilters | None = None, k: int = 20
    ) -> list[SearchHit]:
        f = filters or SearchFilters()
        q = query.lower().strip()
        hits = []
        for c in self._cards:
            if c.item_id in curation.hidden:
                continue
            category = curation.categories.get(c.item_id, c.category_id)
            if f.category_id and category != f.category_id:
                continue
            if f.source_account and c.source_account != f.source_account:
                continue
            if f.language and c.language != f.language:
                continue
            if f.unreadable_only and not c.unreadable_text:
                continue
            day = c.sent_at[:10]
            if (f.date_from and day < f.date_from) or (f.date_to and day > f.date_to):
                continue
            fields = {
                "title": c.title,
                "summary": c.summary,
                "caption": c.caption,
                "on-screen text": c.on_screen_text,
                "speech": c.transcript,
            }
            matched = [name for name, text in fields.items() if q and q in text.lower()]
            if matched:
                hits.append(SearchHit(c.item_id, float(len(matched)), matched))
        hits.sort(key=lambda h: -h.score)
        return hits[:k]
