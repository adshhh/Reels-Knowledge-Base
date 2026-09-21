"""``python -m reelkb.eval`` (AC-7.1): print every AC-4.1 / AC-5.1 threshold with PASS/FAIL,
exit non-zero on any failure. See ``runner.py`` for the checks themselves.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reelkb.contract.curation import load_curation
from reelkb.contract.db import connect_readonly
from reelkb.eval.fixtures import FixtureError, load_holdout, load_queries
from reelkb.eval.ids import load_lookup
from reelkb.eval.runner import (
    build_hybrid_searcher,
    check_holdout_shape,
    run_classification_eval,
    run_search_eval,
)
from reelkb.search.encoder import Encoder


def main(argv: list[str] | None = None, *, encoder: Encoder | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reelkb.eval",
        description="AC-CAT (§4) and AC-SEARCH (§5) against the frozen fixtures (§7).",
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--eval-dir", type=Path, default=Path("eval"))
    parser.add_argument("--fusion-method", choices=["weighted_sum", "rrf"], default="weighted_sum")
    # M8's stated Wave-2 job is "eval and tuning", but alpha was reachable only by editing
    # source in two places, and nothing kept the eval'd config and the served config in
    # step. (M8 checker, finding 8.)
    parser.add_argument(
        "--alpha", type=float, default=0.5, help="dense weight for weighted_sum (1-alpha sparse)"
    )
    parser.add_argument("--rrf-k", type=int, default=60, help="RRF smoothing constant")
    parser.add_argument(
        "--allow-partial-holdout",
        action="store_true",
        help="run against a holdout that is not yet the full 150 items (results are indicative "
        "only, and per-category recall thresholds will be missing)",
    )
    args = parser.parse_args(argv)

    holdout_path = args.eval_dir / "holdout_v1.jsonl"
    queries_path = args.eval_dir / "queries_v1.jsonl"
    db_path = args.data_dir / "kb.db"

    try:
        holdout = load_holdout(holdout_path)
        queries = load_queries(queries_path)
    except FixtureError as e:
        print(f"cannot run eval -- {e}")
        return 2

    if not db_path.exists():
        print(f"cannot run eval -- no database at {db_path}; run the pipeline first")
        return 2

    lookup = load_lookup(args.data_dir)
    if not lookup:
        print(
            f"cannot run eval -- no local lookup at {args.data_dir / 'eval_lookup.json'}; "
            "hashed fixture ids can only be resolved on the machine that created them"
        )
        return 2

    conn = connect_readonly(db_path)
    curation = load_curation(args.data_dir)

    try:
        check_holdout_shape(holdout, lookup, enforce_size=not args.allow_partial_holdout)
        class_result = run_classification_eval(conn, holdout, lookup)
    except FixtureError as e:
        print(f"cannot run classification eval -- {e}")
        return 2

    try:
        searcher = build_hybrid_searcher(
            args.data_dir,
            conn,
            curation,
            encoder=encoder,
            fusion_method=args.fusion_method,
            alpha=args.alpha,
            rrf_k=args.rrf_k,
        )
    except FileNotFoundError as e:
        print(f"cannot run search eval -- {e}")
        return 2

    search_result = run_search_eval(searcher, curation, queries, lookup)

    lines = ["=== AC-CAT (§4, AC-4.1) ==="]
    lines += [t.line() for t in class_result.thresholds]
    lines.append("")
    lines.append(
        f"=== AC-SEARCH (§5, AC-5.1 / AC-5.2) "
        f"[{args.fusion_method}, alpha={args.alpha}, rrf_k={args.rrf_k}] ==="
    )
    lines += [t.line() for t in search_result.thresholds]
    if search_result.unjudged_qids:
        lines.append(
            "[FAIL] queries with no relevant judgement (they would score Recall@10 = 1.0 "
            "for free and drag the average up): " + ", ".join(search_result.unjudged_qids)
        )
    if search_result.zero_recall_qids:
        lines.append(
            "[FAIL] zero-recall queries (AC-5.1 hard-fail): "
            + ", ".join(search_result.zero_recall_qids)
        )
    else:
        lines.append("[PASS] no query returned Recall@10 = 0")
    if search_result.canary_qids:
        if search_result.canary_failure_qids:
            lines.append(
                "[FAIL] canary queries not found in top 10 (AC-5.2): "
                + ", ".join(search_result.canary_failure_qids)
            )
        else:
            lines.append(
                "[PASS] canary queries all found in top 10 (AC-5.2): "
                + ", ".join(search_result.canary_qids)
            )
    print("\n".join(lines))

    return 0 if (class_result.passed and search_result.passed) else 1


if __name__ == "__main__":
    sys.exit(main())
