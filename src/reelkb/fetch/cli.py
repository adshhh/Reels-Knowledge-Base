"""python -m reelkb.fetch -- Stage 3: vendor fetch + manifest (docs/PLAN.md §2, §8).

    python -m reelkb.fetch [--db data/kb.db] [--via apify|ytdlp] [--limit N]
                            [--batch-size N] [--dry-run]

Initialises fetch_status for any new items (AC-2.2, AC-2.3), then asks the chosen vendor for
every 'pending' item (oldest-saved first, capped at --limit if given) and records each
outcome as soon as it arrives. Safe to interrupt and re-run at any point (AC-8.1): a re-run
only ever asks for what is still 'pending'.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from reelkb.contract.db import connect_stage

from .manifest import initialise, pending_requests, project_disk_use
from .orchestrator import run_fetch
from .types import Fetcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m reelkb.fetch", description=__doc__)
    parser.add_argument(
        "--db", type=Path, default=Path("data/kb.db"), help="path to the shared database"
    )
    parser.add_argument(
        "--via", choices=["apify", "ytdlp"], default="apify", help="which vendor to fetch through"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="fetch at most N pending items this run"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="items per vendor call (keep at 1 for a non-paying Apify account, see m0/02)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the queue and projected disk use; fetch nothing",
    )
    return parser


def _make_fetcher(via: str, batch_size: int) -> Fetcher:
    if via == "apify":
        from .apify_fetcher import ApifyFetcher

        return ApifyFetcher(batch_size=batch_size)
    from .ytdlp_fetcher import YtDlpFetcher

    return YtDlpFetcher()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    # sqlite3 happily creates an empty file for a path that doesn't exist, so without this
    # check a typo'd --db died several lines later with a bare "no such table: items"
    # traceback -- and left a stray empty database behind. (M3 checker, finding 8.)
    if not args.db.exists():
        print(
            f"no database at {args.db}. Run the ingest stage first "
            f"(python -m reelkb.ingest), or pass --db with the right path."
        )
        return 2
    conn = connect_stage(args.db, "fetch")
    try:
        try:
            counts = initialise(conn)
        except sqlite3.OperationalError as exc:
            if "no such table" not in str(exc):
                raise
            print(
                f"{args.db} is not a Reel KB database yet ({exc}). "
                f"Run the ingest stage first: python -m reelkb.ingest"
            )
            return 2
        print(f"manifest initialised {sum(counts.values())} new item(s): {counts}")

        requests = pending_requests(conn, args.limit)
        print(f"pending to fetch this run: {len(requests)}")

        if args.dry_run or not requests:
            avg_bytes, projected_bytes = project_disk_use(conn)
            headline = "dry run: no vendor requests made." if args.dry_run else "nothing pending."
            print(
                f"{headline} avg bytes/fetched item so far: {avg_bytes:.0f}; "
                f"projected total disk use across every reel/post item: "
                f"{projected_bytes / 1e9:.2f} GB"
            )
            return 0

        fetcher = _make_fetcher(args.via, args.batch_size)
        media_dir = args.db.parent / "media"
        summary = run_fetch(
            conn, fetcher, media_dir, requests, via=args.via, batch_size=args.batch_size
        )
        print(summary.describe())

        avg_bytes, projected_bytes = project_disk_use(conn)
        print(
            f"projected total disk use across every reel/post item: {projected_bytes / 1e9:.2f} GB"
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
