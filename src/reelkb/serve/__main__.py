"""Run the web app: ``python -m reelkb.serve [--data-dir data] [--host 0.0.0.0] [--port 8000]``.

``--fake`` builds the made-up corpus from ``reelkb.testing.fake_db`` into a temp directory and
serves that instead, so the owner can look at the UI before the real pipeline has produced
``data/kb.db``.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import uvicorn

from reelkb.serve.app import create_app
from reelkb.serve.wiring import make_searcher


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m reelkb.serve")
    parser.add_argument(
        "--data-dir", default="data", help="directory holding kb.db (default: data)"
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    # The eval harness can tune these; without them here a tuned configuration could never
    # reach the running app, so the numbers proven by /eval would not be the numbers the
    # owner actually searches against. (Code review, finding 9.)
    parser.add_argument("--fusion-method", choices=["weighted_sum", "rrf"], default="weighted_sum")
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument(
        "--fake",
        action="store_true",
        help="serve the made-up fake corpus (built into a temp dir) instead of --data-dir",
    )
    args = parser.parse_args()

    if args.fake:
        from reelkb.testing.fake_db import build

        tmp_dir = Path(tempfile.mkdtemp(prefix="reelkb-fake-"))
        build(tmp_dir)
        data_dir = tmp_dir
        print(f"[reelkb.serve] --fake: built the fake corpus into {data_dir}")
    else:
        data_dir = Path(args.data_dir)
        if not (data_dir / "kb.db").exists():
            raise SystemExit(
                f"no database at {data_dir / 'kb.db'} -- run the pipeline first, "
                "or pass --fake to browse the made-up corpus"
            )

    searcher, note = make_searcher(
        data_dir,
        fusion_method=args.fusion_method,
        alpha=args.alpha,
        rrf_k=args.rrf_k,
    )
    print(note)
    app = create_app(data_dir, searcher=searcher)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
