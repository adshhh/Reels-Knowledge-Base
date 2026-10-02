"""What of a Card actually gets embedded (§5): every non-empty extraction channel plus the
fusion stage's title and summary, one blob per item, fixed order. Shared by `embed.py` (real
BGE-M3) and by tests (`FakeEncoder`) -- the two must agree on what text a vector represents,
or the embed stage and the search engine would silently drift apart.
"""

from __future__ import annotations

from reelkb.contract.cards import Card


def text_for_card(card: Card) -> str:
    """Title, summary, and every non-empty channel, newline-joined."""
    parts = [card.title, card.summary, card.caption, card.on_screen_text, card.transcript]
    return "\n".join(p for p in parts if p.strip())
