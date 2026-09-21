"""Small, local fixtures for fetch tests -- a tiny hand-seeded DB, not the shared fake corpus.

``src/reelkb/testing/fake_db.py`` already writes fully 'fetched' fetch_status rows for its 27
cards, which is exactly wrong for testing this stage: M3 needs to see fresh items with *no*
fetch_status row yet, so ``initialise`` and ``run_fetch`` have something to do. Building a
small DB directly here (via ``init_db`` + ``connect_stage``, the same primitives fake_db.py
itself uses) keeps that fresh-start behaviour in this test's own hands.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from pathlib import Path

from reelkb.contract.db import connect_stage, init_db
from reelkb.fetch.download import Downloader
from reelkb.fetch.types import FetchRequest, FetchResult

NOW = "2026-09-19T00:00:00+00:00"


def seed_items(db: Path, items: Sequence[tuple[str, str, str | None]]) -> None:
    """items: (item_id, kind, url) tuples. url may be None (only valid for 'attachment')."""
    init_db(db)
    with connect_stage(db, "ingest") as conn:
        for n, (item_id, kind, url) in enumerate(items):
            conn.execute(
                "INSERT INTO items (item_id, kind, url, caption, source_account, sent_at, "
                "caption_language) VALUES (?, ?, ?, NULL, 'acct', ?, NULL)",
                (item_id, kind, url, f"2023-01-{(n % 28) + 1:02d}T00:00:00+00:00"),
            )


def default_corpus() -> list[tuple[str, str, str | None]]:
    return [
        ("reelAAA", "reel", "https://www.instagram.com/reel/reelAAA/"),
        ("reelBBB", "reel", "https://www.instagram.com/reel/reelBBB/"),
        ("postCCC", "post", "https://www.instagram.com/p/postCCC/"),
        ("att-1", "attachment", None),
        ("ext-1", "external", "https://example.com/x"),
        ("note-1", "note", "https://example.com/y"),
    ]


class RecordingFakeFetcher:
    """A Fetcher that records every item_id it was ever asked for and returns scripted results.

    ``outcomes`` maps item_id -> FetchResult (or a callable producing one), consumed in the
    order requests arrive. An item with no entry gets a default 'dead' result so a test typo
    fails loudly instead of hanging.
    """

    def __init__(self, outcomes: dict[str, FetchResult]) -> None:
        self.outcomes = outcomes
        self.requested: list[str] = []

    def fetch(self, batch: Sequence[FetchRequest]) -> Iterator[FetchResult]:
        for request in batch:
            self.requested.append(request.item_id)
            yield self.outcomes.get(
                request.item_id,
                FetchResult(request.item_id, "dead", reason="no scripted outcome in test"),
            )


class CrashingFakeFetcher:
    """Yields scripted results, then raises after ``crash_after`` of them -- simulating a kill."""

    def __init__(self, outcomes: list[FetchResult], crash_after: int) -> None:
        self.outcomes = outcomes
        self.crash_after = crash_after
        self.requested: list[str] = []

    def fetch(self, batch: Sequence[FetchRequest]) -> Iterator[FetchResult]:
        for i, request in enumerate(batch):
            self.requested.append(request.item_id)
            if i >= self.crash_after:
                raise RuntimeError("simulated kill mid-run")
            yield next(o for o in self.outcomes if o.item_id == request.item_id)


def fake_downloader_factory(bytes_per_item: int = 1234) -> tuple[list[str], Downloader]:
    """A stand-in for fetch.download.fetch_url_bytes that never touches the network."""
    calls: list[str] = []

    def _fake(url: str, dest: Path, **_kwargs: object) -> int:
        calls.append(url)
        dest.write_bytes(b"x" * bytes_per_item)
        return bytes_per_item

    return calls, _fake


def status_rows(db: Path) -> dict[str, tuple[str, str | None]]:
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT item_id, status, reason FROM fetch_status").fetchall()
    conn.close()
    return {r[0]: (r[1], r[2]) for r in rows}
