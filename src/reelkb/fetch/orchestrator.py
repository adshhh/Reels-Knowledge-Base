"""Turning a Fetcher's per-item results into fetch_status rows, one item at a time.

The core AC-8.1 guarantee lives here: ``run_fetch`` writes and commits the database (and, for
a success, the file is already renamed into place first) for *each* item as its result
arrives from the fetcher's generator -- never batched into one big transaction at the end. If
the process is killed (or the fetcher raises) after N results, those N items are already
terminal on disk; a fresh run only ever asks for what's still 'pending'.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .download import (
    Downloader,
    UrlFixup,
    apify_url_fixup,
    download_result,
    fetch_url_bytes,
    no_fixup,
)
from .duration import probe_duration
from .manifest import now_iso
from .types import Fetcher, FetchRequest, FetchResult


@dataclass
class Summary:
    fetched: int = 0
    dead: int = 0
    transient: int = 0
    bytes_downloaded: int = 0
    errors: list[str] = field(default_factory=list)

    def describe(self) -> str:
        return (
            f"fetched={self.fetched} dead={self.dead} left_pending(transient)={self.transient} "
            f"bytes_downloaded_this_run={self.bytes_downloaded} "
            f"({self.bytes_downloaded / 1e9:.3f} GB)"
        )


def _chunks(items: Sequence[FetchRequest], size: int) -> list[Sequence[FetchRequest]]:
    size = max(1, size)
    return [items[i : i + size] for i in range(0, len(items), size)]


def _apply_result(
    conn: sqlite3.Connection,
    media_dir: Path,
    via: str,
    result: FetchResult,
    summary: Summary,
    *,
    downloader: Downloader,
    url_fixup: UrlFixup,
) -> None:
    ts = now_iso()
    if result.outcome == "success":
        media_path, total_bytes = download_result(
            result, media_dir, downloader=downloader, url_fixup=url_fixup
        )
        duration_s = None
        if result.media_type != "carousel":
            duration_s = probe_duration(media_dir.parent / media_path)
        conn.execute(
            "UPDATE fetch_status SET status = 'fetched', reason = NULL, fetched_via = ?, "
            "media_type = ?, media_path = ?, duration_s = ?, bytes = ?, updated_at = ? "
            "WHERE item_id = ?",
            (via, result.media_type, media_path, duration_s, total_bytes, ts, result.item_id),
        )
        summary.fetched += 1
        summary.bytes_downloaded += total_bytes
    elif result.outcome == "dead":
        conn.execute(
            "UPDATE fetch_status SET status = 'dead', reason = ?, updated_at = ? WHERE item_id = ?",
            (result.reason, ts, result.item_id),
        )
        summary.dead += 1
    else:  # transient: stays 'pending', reason recorded for visibility, retried next run
        conn.execute(
            "UPDATE fetch_status SET reason = ?, updated_at = ? WHERE item_id = ?",
            (result.reason, ts, result.item_id),
        )
        summary.transient += 1
        if result.reason:
            summary.errors.append(f"{result.item_id}: {result.reason}")
    conn.commit()


def run_fetch(
    conn: sqlite3.Connection,
    fetcher: Fetcher,
    media_dir: Path,
    requests: Sequence[FetchRequest],
    *,
    via: str,
    batch_size: int = 1,
    downloader: Downloader = fetch_url_bytes,
    url_fixup: UrlFixup | None = None,
) -> Summary:
    """Ask ``fetcher`` for every item in ``requests`` and record each outcome as it arrives.

    ``requests`` should already be the pending queue (``manifest.pending_requests``) -- this
    function does not re-check status itself, so a second call with the same requests would
    re-request them. The CLI always re-queries between runs; tests do the same explicitly so
    that "second run issues zero requests for terminal items" is a property of the manifest
    query, not of this function trusting stale input.
    """
    if url_fixup is None:
        url_fixup = apify_url_fixup if via == "apify" else no_fixup

    summary = Summary()
    for chunk in _chunks(requests, batch_size):
        for result in fetcher.fetch(chunk):
            try:
                _apply_result(
                    conn,
                    media_dir,
                    via,
                    result,
                    summary,
                    downloader=downloader,
                    url_fixup=url_fixup,
                )
            except Exception as exc:
                # One item must not end the run. This loop is the ~3.5-hour bulk fetch over
                # 1,870 items, and the download inside _apply_result touches the network, the
                # filesystem and ffprobe -- any of which can fail on a single item. Letting it
                # propagate abandoned every remaining item AND lost the run summary, so the
                # owner would not even learn what had been done. (Code review, finding 6.)
                # The item stays 'pending' (nothing was committed for it), so the next run
                # retries it -- the same recovery path as a transient vendor error.
                summary.transient += 1
                summary.errors.append(f"{result.item_id}: {type(exc).__name__}: {exc}")
    return summary
