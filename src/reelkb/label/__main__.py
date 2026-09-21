"""``python -m reelkb.label [--data-dir data] [--port 8001] [--fake]``

Runs the local labelling page used to hand-build ``eval/holdout_v1.jsonl`` and
``eval/queries_v1.jsonl`` (PLAN.md §7). Local only — bind address is 127.0.0.1, reached over
Tailscale or localhost the same way as the main app (D5).
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import uvicorn

from reelkb.contract.cards import load_cards
from reelkb.contract.curation import load_curation
from reelkb.contract.db import connect_readonly
from reelkb.contract.search_api import Searcher
from reelkb.label.app import create_app
from reelkb.serve.wiring import make_searcher
from reelkb.testing.fake_search import SubstringSearcher


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", default="data", help="directory holding kb.db (default: data)"
    )
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument(
        "--fake", action="store_true", help="serve the fake corpus from a fresh temp dir"
    )
    args = parser.parse_args()

    if args.fake:
        from reelkb.testing.fake_db import build as build_fake_db

        tmp_root = Path(tempfile.mkdtemp(prefix="reelkb-label-fake-"))
        data_dir = tmp_root / "data"
        data_dir.mkdir(parents=True)
        build_fake_db(data_dir)
        print(f"[reelkb.label] fake corpus written to {data_dir}")
        print(f"[reelkb.label] fixtures will be written under {tmp_root / 'eval'}")
    else:
        data_dir = Path(args.data_dir)
        if not (data_dir / "kb.db").exists():
            raise SystemExit(
                f"no database at {data_dir / 'kb.db'} — run with --fake to try it on the "
                "made-up corpus, or point --data-dir at a real one"
            )

    # The judging pool must come from the engines that will actually serve search. Pooling
    # from the substring double alone means items only dense/sparse retrieval can find are
    # never shown, never graded, and score 0 for ever -- so AC-SEARCH would be measured
    # against a pool the real engine never contributed to. (M8 checker, finding 4; the same
    # defect the M9/M10 checker found in the serve app and which serve/wiring.py fixed.)
    searchers: dict[str, Searcher] | None = None
    cards = load_cards(connect_readonly(data_dir / "kb.db"), load_curation(data_dir))
    hybrid, note = make_searcher(data_dir)
    print(note.replace("[reelkb.serve]", "[reelkb.label]"))
    if hybrid is not None:
        # Both, deliberately: pooling from several retrieval methods is what §7 asks for, and
        # the lexical double still surfaces exact-term matches the vectors can miss.
        searchers = {"hybrid": hybrid, "substring": SubstringSearcher(cards)}
        print("[reelkb.label] judging pool = hybrid + substring")
    else:
        print(
            "[reelkb.label] WARNING: judging pool = substring only. Queries judged now will "
            "grade a pool the real engine never contributed to, and AC-SEARCH measured "
            "against them will be optimistic. Build the index first if you can."
        )

    app = create_app(data_dir, searchers=searchers)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
