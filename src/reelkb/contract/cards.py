"""A Card is one reel as the product sees it: everything the feed, detail view and search need.

Cards are assembled from the pipeline tables and then the owner's curation is laid on top,
so hidden items vanish and edits and category corrections always win (AC-1.3, AC-4.3).
Only items that were fetched AND fused become cards; everything else is pipeline state.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from reelkb.contract.curation import Curation


@dataclass(frozen=True)
class Card:
    item_id: str
    url: str
    title: str
    summary: str
    bullets: list[str]
    source_account: str | None
    sent_at: str
    category_id: str | None
    category_name: str | None
    language: str | None
    # The three extraction channels, verbatim; '' when the channel is empty (AC-1.2).
    caption: str
    on_screen_text: str
    transcript: str
    unreadable_text: bool = False
    lyric_like: bool = False
    entities: dict[str, list[str]] = field(default_factory=dict)
    # Names the fidelity gate could not confirm against on-screen text but did NOT remove
    # (owner's call -- stripping them destroys correct cards; see DESIGN_RATIONALE #11).
    unverified_names: list[str] = field(default_factory=list)

    def channels(self) -> list[tuple[str, str]]:
        """Non-empty channels with their source label, in display order (AC-1.2)."""
        labelled = [
            ("Caption", self.caption),
            ("On-screen text", self.on_screen_text),
            ("Speech", self.transcript),
        ]
        return [(label, text) for label, text in labelled if text.strip()]


_CARD_SQL = """
SELECT i.item_id, i.url, i.caption, i.source_account, i.sent_at,
       f.title, f.summary, f.bullets, f.entities, f.language, f.unverified_names,
       c.category_id, t.text AS transcript, t.lyric_like, o.unreadable_text
FROM items i
JOIN fusion f ON f.item_id = i.item_id
LEFT JOIN classification c ON c.item_id = i.item_id
LEFT JOIN transcripts t ON t.item_id = i.item_id
LEFT JOIN ocr_runs o ON o.item_id = i.item_id
"""


def _flagged_names(raw: str | None) -> list[str]:
    """Distinct flagged names for display, in the order the gate found them."""
    out: list[str] = []
    for entry in json.loads(raw or "[]"):
        value = entry.get("value", "")
        if value and value not in out:
            out.append(value)
    return out


def _on_screen_text(conn: sqlite3.Connection) -> dict[str, str]:
    """Distinct OCR strings per item, in the order they first appeared on screen."""
    out: dict[str, list[str]] = {}
    rows = conn.execute(
        "SELECT item_id, text FROM ocr_verbatim ORDER BY item_id, frame_ts_s, rowid"
    )
    for item_id, text in rows:
        seen = out.setdefault(item_id, [])
        if text not in seen:
            seen.append(text)
    return {k: "\n".join(v) for k, v in out.items()}


def load_cards(
    conn: sqlite3.Connection, curation: Curation, *, include_hidden: bool = False
) -> list[Card]:
    names = dict(conn.execute("SELECT category_id, name FROM categories").fetchall())
    ocr = _on_screen_text(conn)
    cards = []
    for r in conn.execute(_CARD_SQL):
        item_id = r["item_id"]
        if item_id in curation.hidden and not include_hidden:
            continue
        edits = curation.edits.get(item_id, {})
        category_id = curation.categories.get(item_id, r["category_id"])
        cards.append(
            Card(
                item_id=item_id,
                url=r["url"] or "",
                title=edits.get("title", r["title"]),
                summary=edits.get("summary", r["summary"]),
                bullets=json.loads(r["bullets"]),
                source_account=r["source_account"],
                sent_at=r["sent_at"],
                category_id=category_id,
                category_name=names.get(category_id) if category_id else None,
                language=r["language"],
                caption=r["caption"] or "",
                on_screen_text=ocr.get(item_id, ""),
                transcript=r["transcript"] or "",
                unreadable_text=bool(r["unreadable_text"]),
                lyric_like=bool(r["lyric_like"]),
                entities=json.loads(r["entities"]),
                unverified_names=_flagged_names(r["unverified_names"]),
            )
        )
    return cards
