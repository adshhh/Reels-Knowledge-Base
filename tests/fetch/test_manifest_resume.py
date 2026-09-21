"""AC-8.1: killing a fetch run mid-batch and restarting processes only unfinished items and
produces no duplicates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reelkb.contract.db import connect_stage
from reelkb.fetch.manifest import initialise, pending_requests
from reelkb.fetch.orchestrator import run_fetch
from reelkb.fetch.types import FetchResult, MediaFile

from .helpers import CrashingFakeFetcher, RecordingFakeFetcher, fake_downloader_factory, seed_items

ITEMS = [
    ("reelA", "reel", "https://www.instagram.com/reel/reelA/"),
    ("reelB", "reel", "https://www.instagram.com/reel/reelB/"),
    ("reelC", "reel", "https://www.instagram.com/reel/reelC/"),
    ("reelD", "reel", "https://www.instagram.com/reel/reelD/"),
]

ALL_OUTCOMES = [
    FetchResult(
        "reelA", "success", media_type="video", files=(MediaFile("http://x/a.mp4", "video"),)
    ),
    FetchResult(
        "reelB", "success", media_type="video", files=(MediaFile("http://x/b.mp4", "video"),)
    ),
    FetchResult("reelC", "dead", reason="post deleted by creator"),
    FetchResult(
        "reelD", "success", media_type="video", files=(MediaFile("http://x/d.mp4", "video"),)
    ),
]


def test_kill_mid_run_then_restart_processes_only_unfinished_items(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    seed_items(db, ITEMS)
    media_dir = tmp_path / "media"
    calls, downloader = fake_downloader_factory(bytes_per_item=999)

    # --- run 1: crashes after 2 of the 4 items are done (simulating a kill mid-run) ---
    def crashing_run() -> None:
        """The crash must escape the `with` block, or this test proves nothing.

        The M3 checker demonstrated the earlier version of this test: with `pytest.raises`
        INSIDE the `with connect_stage(...)` block, the exception was swallowed there, the
        connection context manager exited cleanly, and sqlite3 committed everything on the
        way out. The test passed identically with orchestrator.py's per-item `commit()`
        removed -- i.e. it could not detect the loss of the one mechanism AC-8.1 rests on.

        Letting the exception propagate out of the `with` makes sqlite3 ROLL BACK instead,
        so only work that was genuinely committed per-item survives -- which is precisely
        what a real kill -9 would leave behind.
        """
        with connect_stage(db, "fetch") as conn:
            initialise(conn)
            assert len(pending_requests(conn)) == 4
            # batch_size=len(requests): everything rides in one vendor call, so the crash
            # happens mid-batch, not between separate calls -- the harder case for AC-8.1.
            requests = pending_requests(conn)
            run_fetch(
                conn,
                CrashingFakeFetcher(ALL_OUTCOMES, crash_after=2),
                media_dir,
                requests,
                via="apify",
                batch_size=len(requests),
                downloader=downloader,
            )

    with pytest.raises(RuntimeError, match="simulated kill mid-run"):
        crashing_run()

    # The two items processed before the crash are already terminal on disk...
    with connect_stage(db, "fetch") as conn:
        after_crash = {
            r[0]: r[1] for r in conn.execute("SELECT item_id, status FROM fetch_status").fetchall()
        }
    assert after_crash["reelA"] == "fetched"
    assert after_crash["reelB"] == "fetched"
    # ...and the two never reached are still pending, not half-written or marked failed.
    assert after_crash["reelC"] == "pending"
    assert after_crash["reelD"] == "pending"
    assert (media_dir / "reelA.mp4").exists()
    assert (media_dir / "reelB.mp4").exists()
    assert not (media_dir / "reelC.mp4").exists()
    assert not (media_dir / "reelD.mp4").exists()
    calls_after_crash = list(calls)

    # --- restart: a fresh run only asks for what's still pending ---
    with connect_stage(db, "fetch") as conn:
        initialise(conn)  # idempotent: touches nothing already set
        resumed_requests = pending_requests(conn)
        assert {r.item_id for r in resumed_requests} == {"reelC", "reelD"}

        resume_fetcher = RecordingFakeFetcher({o.item_id: o for o in ALL_OUTCOMES})
        run_fetch(
            conn, resume_fetcher, media_dir, resumed_requests, via="apify", downloader=downloader
        )
        # The restart never re-requested the two items already terminal before the crash.
        assert sorted(resume_fetcher.requested) == ["reelC", "reelD"]

    final = {
        r[0]: r[1]
        for r in connect_stage(db, "fetch")
        .execute("SELECT item_id, status FROM fetch_status")
        .fetchall()
    }
    assert final == {"reelA": "fetched", "reelB": "fetched", "reelC": "dead", "reelD": "fetched"}

    # Zero duplicate downloads: reelA/reelB's bytes were fetched exactly once across both runs.
    assert calls.count("http://x/a.mp4") == 1
    assert calls.count("http://x/b.mp4") == 1
    assert calls == calls_after_crash + ["http://x/d.mp4"]

    # Each fetched file is still exactly the size the (fake) download produced once.
    assert (media_dir / "reelA.mp4").stat().st_size == 999
    assert (media_dir / "reelD.mp4").stat().st_size == 999
