"""The manifest: giving every ``items`` row a ``fetch_status`` row, and reading the queue.

Terminal states (``fetched``, ``dead``, ``unrecoverable``, ``excluded``) are never touched
again once set -- that is what makes AC-2.2 true. ``initialise`` only ever INSERTs a row for
an item that doesn't have one yet; it never looks at, let alone changes, a row that already
exists.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from .types import FetchRequest

# Exact wording from docs/CONTRACT.md's fetch_status row.
REASON_UNRECOVERABLE = "export has no share data"
# decisions/003: v1 records external links / typed notes in the manifest but never fetches them.
REASON_EXCLUDED = "non-Instagram link or typed note, deferred to v2 (decisions/003)"
REASON_NO_URL = "reel/post row carries no url, nothing to fetch"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def initialise(conn: sqlite3.Connection) -> dict[str, int]:
    """Give every ``items`` row missing a ``fetch_status`` row one.

    attachment -> unrecoverable; external/note -> excluded; reel/post -> pending.
    Idempotent: safe to call at the start of every run. Returns how many rows of each new
    status were inserted this call (0s on a second run, since nothing is missing any more).
    """
    rows = conn.execute(
        "SELECT items.item_id, items.kind, items.url FROM items "
        "LEFT JOIN fetch_status ON fetch_status.item_id = items.item_id "
        "WHERE fetch_status.item_id IS NULL"
    ).fetchall()

    counts = {"pending": 0, "unrecoverable": 0, "excluded": 0}
    ts = now_iso()
    for item_id, kind, url in rows:
        if kind == "attachment":
            status, reason = "unrecoverable", REASON_UNRECOVERABLE
        elif kind in ("external", "note"):
            status, reason = "excluded", REASON_EXCLUDED
        elif not (url or "").strip():
            # A reel/post row with no url can never be fetched, so it must not sit in the
            # queue forever pretending it might be: AC-2.2 wants every item terminal with a
            # recorded reason. M2's parser classifies link-less shares as 'external', so this
            # should be unreachable -- which is exactly why it is worth making explicit rather
            # than leaving a None to travel into a vendor request. (M3 checker, finding 7.)
            status, reason = "unrecoverable", REASON_NO_URL
        else:  # 'reel' or 'post' with a url
            status, reason = "pending", None
        conn.execute(
            "INSERT INTO fetch_status (item_id, status, reason, updated_at) VALUES (?, ?, ?, ?)",
            (item_id, status, reason, ts),
        )
        counts[status] += 1
    conn.commit()
    return counts


def pending_requests(conn: sqlite3.Connection, limit: int | None = None) -> list[FetchRequest]:
    """The current fetch queue: every 'pending' item, oldest saved first.

    Terminal items never appear here (AC-2.2) -- this is the only query the orchestrator uses
    to decide what to ask a vendor for.
    """
    sql = (
        "SELECT items.item_id, items.url FROM items "
        "JOIN fetch_status ON fetch_status.item_id = items.item_id "
        "WHERE fetch_status.status = 'pending' "
        "ORDER BY items.sent_at"
    )
    params: tuple[int, ...] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)
    rows = conn.execute(sql, params).fetchall()
    return [FetchRequest(item_id=r[0], url=r[1]) for r in rows]


def project_disk_use(conn: sqlite3.Connection) -> tuple[float, float]:
    """(average bytes per fetched item so far, that average projected over every reel/post).

    A rough running estimate, printed after every run -- not a promise, since dead items and
    attrition mean the real total is always less than "average so far x every reel/post".
    """
    avg_row = conn.execute(
        "SELECT AVG(bytes) FROM fetch_status WHERE status = 'fetched' AND bytes IS NOT NULL"
    ).fetchone()
    avg_bytes = float(avg_row[0]) if avg_row and avg_row[0] is not None else 0.0
    total_row = conn.execute("SELECT COUNT(*) FROM items WHERE kind IN ('reel', 'post')").fetchone()
    total_items = int(total_row[0]) if total_row else 0
    return avg_bytes, avg_bytes * total_items
