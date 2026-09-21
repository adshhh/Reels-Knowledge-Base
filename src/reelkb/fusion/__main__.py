"""CLI entry point: ``python -m reelkb.fusion [--db data/kb.db] [--limit N]``.

Reads the Groq API key from the ``GROQ_API_KEY`` environment variable (never printed, never
logged — see `docs/CONTRACT.md`'s "what leaves this machine" table). Runs sequentially, one
item at a time, matching the project-wide rule that pipeline stages never run concurrently
(8 GB of RAM).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from reelkb.contract.db import connect_stage
from reelkb.fusion.model_client import DEFAULT_MODEL, GroqFusionClient
from reelkb.fusion.stage import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m reelkb.fusion", description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/kb.db"), help="path to kb.db")
    parser.add_argument("--limit", type=int, default=None, help="process at most N items")
    parser.add_argument(
        "--allowed-sources",
        choices=("ocr_only", "ocr_and_caption"),
        default="ocr_only",
        help=(
            "what the fidelity gate may verify entities against. ocr_only (default) matches "
            "AC-3.1 as written; ocr_and_caption is looser and is the owner's call, not the "
            "default — see reelkb.fusion.stage's module docstring for the trade-off"
        ),
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Groq model name")
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(
            f"fusion: {args.db} does not exist -- run earlier pipeline stages first",
            file=sys.stderr,
        )
        return 1

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("fusion: GROQ_API_KEY is not set", file=sys.stderr)
        return 1

    client = GroqFusionClient(api_key=api_key, model=args.model)
    conn = connect_stage(args.db, "fusion")
    try:
        summary = run(
            conn,
            client,
            limit=args.limit,
            allowed_sources=args.allowed_sources,
            model_name=args.model,
            log=print,
        )
    finally:
        conn.close()

    print(summary.report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
