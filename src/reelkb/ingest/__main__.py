"""CLI entry point: ``python -m reelkb.ingest <path to message_1.json> [--db data/kb.db]``.

Loads the export, parses it with :mod:`reelkb.ingest.parser` (pure, no I/O), then upserts
the result into the ``items`` table it owns. Upserting on ``item_id`` (rather than deleting
and reinserting) is what makes a re-run idempotent without violating the foreign keys that
later stages (``fetch_status`` etc.) put on ``items.item_id`` — a delete-then-reinsert would
either cascade-fail once downstream tables have rows, or silently orphan them.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from reelkb.contract.db import connect_stage, init_db
from reelkb.ingest.parser import ParsedItem, ParseStats, iso_utc, parse_messages

_UPSERT_SQL = """
INSERT INTO items (item_id, kind, url, caption, source_account, sent_at, caption_language)
VALUES (:item_id, :kind, :url, :caption, :source_account, :sent_at, :caption_language)
ON CONFLICT(item_id) DO UPDATE SET
    kind = excluded.kind,
    url = excluded.url,
    caption = excluded.caption,
    source_account = excluded.source_account,
    sent_at = excluded.sent_at,
    caption_language = excluded.caption_language
"""


def _row(item: ParsedItem) -> dict[str, str | None]:
    return {
        "item_id": item.item_id,
        "kind": item.kind,
        "url": item.url,
        "caption": item.caption,
        "source_account": item.source_account,
        "sent_at": iso_utc(item.sent_at_ms),
        "caption_language": item.caption_language,
    }


def write_items(conn: sqlite3.Connection, items: list[ParsedItem]) -> None:
    """Upsert every parsed item. Re-running with the same export is a no-op (idempotent)."""
    conn.executemany(_UPSERT_SQL, [_row(item) for item in items])
    conn.commit()


def run(export_path: Path, db_path: Path) -> ParseStats:
    """Parse ``export_path`` and load it into ``db_path``. Returns stats for reporting."""
    with export_path.open("rb") as f:
        data = json.load(f)
    items, stats = parse_messages(data["messages"])

    init_db(db_path)
    conn = connect_stage(db_path, "ingest")
    try:
        write_items(conn, items)
    finally:
        conn.close()
    return stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Parse a DM export into the items table.")
    parser.add_argument("export_path", type=Path, help="path to message_1.json")
    parser.add_argument("--db", type=Path, default=Path("data/kb.db"), dest="db_path")
    args = parser.parse_args(argv)

    stats = run(args.export_path, args.db_path)

    print("Ingest complete. Counts per kind:")
    for kind, count in stats.counts.items():
        print(f"  {kind}: {count}")
    print(f"  (duplicate reel/post shares collapsed: {stats.duplicate_shares})")
    print(f"  (mojibake decode failures, text kept as-is: {stats.mojibake_failures})")


if __name__ == "__main__":
    main()
