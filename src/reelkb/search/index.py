"""``HybridSearcher``: the real implementation of ``contract.search_api.Searcher`` (§5, M8).

Combines a ``DenseIndex`` (semantic similarity) and a ``SparseIndex`` (exact-term matching)
with the fusion method from ``fusion.py``, then applies filters and curation exactly like
``reelkb.testing.fake_search.SubstringSearcher`` does, so the web app can swap one for the
other with no other code change.

Both indexes are pre-built (by ``embed.py``, from real BGE-M3 vectors, or by tests, from
``FakeEncoder`` vectors) -- ``search()`` only encodes the *query* at call time and scores it
against the stored per-item vectors. That is what makes this "brute force": no approximate
nearest-neighbour structure, just a dot product against every row (§5 -- fast enough at this
corpus size that a vector database would add latency, not remove it).
"""

from __future__ import annotations

from reelkb.contract.cards import Card
from reelkb.contract.curation import Curation
from reelkb.contract.search_api import SearchFilters, SearchHit
from reelkb.search.dense import DenseIndex
from reelkb.search.encoder import Encoder, tokenize
from reelkb.search.fusion import FusionMethod, fuse
from reelkb.search.sparse import SparseIndex

# Channels considered for matched_on, in the order they're checked. Labels match the example
# in contract/search_api.py ("on-screen text", "speech"), not cards.py's capitalised display
# labels -- matched_on is a machine-readable tag, channels() is a display label.
_CHANNELS = ("title", "summary", "caption", "on-screen text", "speech")


def _channel_text(card: Card, channel: str) -> str:
    return {
        "title": card.title,
        "summary": card.summary,
        "caption": card.caption,
        "on-screen text": card.on_screen_text,
        "speech": card.transcript,
    }[channel]


def _matched_channels(card: Card, query_tokens: set[str]) -> list[str]:
    """Which channels share at least one token with the query, in display order."""
    if not query_tokens:
        return []
    matched = []
    for channel in _CHANNELS:
        text_tokens = set(tokenize(_channel_text(card, channel)))
        if query_tokens & text_tokens:
            matched.append(channel)
    return matched


def _passes_filters(card: Card, category_id: str | None, filters: SearchFilters) -> bool:
    if filters.category_id and category_id != filters.category_id:
        return False
    if filters.source_account and card.source_account != filters.source_account:
        return False
    if filters.language and card.language != filters.language:
        return False
    if filters.unreadable_only and not card.unreadable_text:
        return False
    day = card.sent_at[:10]
    if filters.date_from and day < filters.date_from:
        return False
    if filters.date_to and day > filters.date_to:
        return False
    return True


class HybridSearcher:
    """Hybrid dense + sparse search, implementing ``contract.search_api.Searcher``."""

    def __init__(
        self,
        cards: list[Card],
        dense_index: DenseIndex,
        sparse_index: SparseIndex,
        encoder: Encoder,
        *,
        fusion_method: FusionMethod = "weighted_sum",
        alpha: float = 0.5,
        rrf_k: int = 60,
    ) -> None:
        self._cards_by_id = {c.item_id: c for c in cards}
        self._dense_index = dense_index
        self._sparse_index = sparse_index
        self._encoder = encoder
        self._fusion_method = fusion_method
        self._alpha = alpha
        self._rrf_k = rrf_k

    def search(
        self, query: str, curation: Curation, filters: SearchFilters | None = None, k: int = 20
    ) -> list[SearchHit]:
        f = filters or SearchFilters()
        batch = self._encoder.encode([query])
        dense_scores = self._dense_index.score(batch.dense[0])
        sparse_scores = self._sparse_index.score(batch.sparse[0])
        fused = fuse(
            dense_scores,
            sparse_scores,
            method=self._fusion_method,
            alpha=self._alpha,
            rrf_k=self._rrf_k,
        )

        query_tokens = set(tokenize(query))
        hits: list[SearchHit] = []
        for item_id, score in fused:
            if item_id in curation.hidden:  # D15: hidden items never returned
                continue
            card = self._cards_by_id.get(item_id)
            if card is None:  # a vector exists for an item that isn't a loaded card
                continue
            category_id = curation.categories.get(item_id, card.category_id)
            if not _passes_filters(card, category_id, f):
                continue
            hits.append(SearchHit(item_id, score, _matched_channels(card, query_tokens)))
            if len(hits) >= k:
                break
        return hits
