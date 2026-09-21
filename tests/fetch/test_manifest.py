"""AC-2.2 and AC-2.3 (fetch side): every item ends terminal, and terminal items are never
re-requested.
"""

from __future__ import annotations

from pathlib import Path

from reelkb.contract.db import connect_readonly, connect_stage
from reelkb.fetch.manifest import (
    REASON_EXCLUDED,
    REASON_UNRECOVERABLE,
    initialise,
    pending_requests,
)
from reelkb.fetch.orchestrator import run_fetch
from reelkb.fetch.types import FetchResult, MediaFile

from .helpers import (
    RecordingFakeFetcher,
    default_corpus,
    fake_downloader_factory,
    seed_items,
    status_rows,
)


def test_initialise_gives_every_item_a_terminal_or_pending_status(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    seed_items(db, default_corpus())

    with connect_stage(db, "fetch") as conn:
        counts = initialise(conn)

    rows = status_rows(db)
    assert rows == {
        "reelAAA": ("pending", None),
        "reelBBB": ("pending", None),
        "postCCC": ("pending", None),
        "att-1": ("unrecoverable", REASON_UNRECOVERABLE),
        "ext-1": ("excluded", REASON_EXCLUDED),
        "note-1": ("excluded", REASON_EXCLUDED),
    }
    assert counts == {"pending": 3, "unrecoverable": 1, "excluded": 2}
    # No row is left NULL -- every item in the export ends in a real status (AC-2.2).
    assert None not in {status for status, _reason in rows.values()}


def test_attachments_are_unrecoverable_and_excluded_from_the_queue(tmp_path: Path) -> None:
    """AC-2.3: attachments (no share data at all) are recorded unrecoverable and never queued."""
    db = tmp_path / "kb.db"
    seed_items(db, default_corpus())
    with connect_stage(db, "fetch") as conn:
        initialise(conn)
        queue_ids = {r.item_id for r in pending_requests(conn)}

    assert "att-1" not in queue_ids
    assert status_rows(db)["att-1"] == ("unrecoverable", REASON_UNRECOVERABLE)


def test_external_and_note_items_are_excluded_from_the_queue(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    seed_items(db, default_corpus())
    with connect_stage(db, "fetch") as conn:
        initialise(conn)
        queue_ids = {r.item_id for r in pending_requests(conn)}

    assert "ext-1" not in queue_ids
    assert "note-1" not in queue_ids


def test_initialise_is_idempotent_and_never_touches_an_existing_row(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    seed_items(db, default_corpus())
    with connect_stage(db, "fetch") as conn:
        initialise(conn)
        # Hand-move one item to a terminal state, the way a real fetch run would.
        conn.execute(
            "UPDATE fetch_status SET status = 'dead', reason = 'deleted' WHERE item_id = 'reelAAA'"
        )
        conn.commit()
        second_counts = initialise(conn)

    assert second_counts == {"pending": 0, "unrecoverable": 0, "excluded": 0}
    assert status_rows(db)["reelAAA"] == ("dead", "deleted")


def test_second_run_issues_zero_requests_for_terminal_items(tmp_path: Path) -> None:
    """AC-2.2: once every item is terminal, a second run makes no vendor requests at all."""
    db = tmp_path / "kb.db"
    seed_items(db, default_corpus())
    media_dir = tmp_path / "media"
    _calls, downloader = fake_downloader_factory()

    outcomes = {
        "reelAAA": FetchResult(
            "reelAAA", "success", media_type="video", files=(MediaFile("http://x/a.mp4", "video"),)
        ),
        "reelBBB": FetchResult("reelBBB", "dead", reason="post deleted by creator"),
        "postCCC": FetchResult(
            "postCCC", "success", media_type="image", files=(MediaFile("http://x/c.jpg", "image"),)
        ),
    }

    with connect_stage(db, "fetch") as conn:
        initialise(conn)
        requests = pending_requests(conn)
        assert {r.item_id for r in requests} == {"reelAAA", "reelBBB", "postCCC"}

        first_fetcher = RecordingFakeFetcher(outcomes)
        run_fetch(conn, first_fetcher, media_dir, requests, via="apify", downloader=downloader)
        assert sorted(first_fetcher.requested) == ["postCCC", "reelAAA", "reelBBB"]

    rows = status_rows(db)
    assert rows["reelAAA"][0] == "fetched"
    assert rows["reelBBB"] == ("dead", "post deleted by creator")
    assert rows["postCCC"][0] == "fetched"

    # Second run: the queue is empty, so the fetcher is never even called.
    with connect_stage(db, "fetch") as conn:
        initialise(conn)
        second_requests = pending_requests(conn)
        assert second_requests == []

        second_fetcher = RecordingFakeFetcher({})
        run_fetch(
            conn, second_fetcher, media_dir, second_requests, via="apify", downloader=downloader
        )
        assert second_fetcher.requested == []  # zero requests for terminal items


def test_transient_result_leaves_item_pending_with_a_reason(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    seed_items(db, [("reelAAA", "reel", "https://www.instagram.com/reel/reelAAA/")])
    media_dir = tmp_path / "media"

    with connect_stage(db, "fetch") as conn:
        initialise(conn)
        requests = pending_requests(conn)
        fetcher = RecordingFakeFetcher(
            {"reelAAA": FetchResult("reelAAA", "transient", reason="actor call failed: timeout")}
        )
        run_fetch(conn, fetcher, media_dir, requests, via="apify")

    status, reason = status_rows(db)["reelAAA"]
    assert status == "pending"
    assert reason == "actor call failed: timeout"


def test_fetched_item_records_bytes_media_path_and_fetched_via(tmp_path: Path) -> None:
    db = tmp_path / "kb.db"
    seed_items(db, [("reelAAA", "reel", "https://www.instagram.com/reel/reelAAA/")])
    media_dir = tmp_path / "media"
    _calls, downloader = fake_downloader_factory(bytes_per_item=555)

    with connect_stage(db, "fetch") as conn:
        initialise(conn)
        requests = pending_requests(conn)
        fetcher = RecordingFakeFetcher(
            {
                "reelAAA": FetchResult(
                    "reelAAA",
                    "success",
                    media_type="video",
                    files=(MediaFile("http://vendor/reelAAA.mp4", "video"),),
                )
            }
        )
        run_fetch(conn, fetcher, media_dir, requests, via="apify", downloader=downloader)

    row = (
        connect_readonly(db)
        .execute(
            "SELECT status, fetched_via, media_type, media_path, bytes FROM fetch_status "
            "WHERE item_id = 'reelAAA'"
        )
        .fetchone()
    )
    assert row["status"] == "fetched"
    assert row["fetched_via"] == "apify"
    assert row["media_type"] == "video"
    assert row["media_path"] == "media/reelAAA.mp4"
    assert row["bytes"] == 555
    assert (media_dir / "reelAAA.mp4").exists()


def test_one_failing_download_does_not_abandon_the_rest_of_the_run(tmp_path: Path) -> None:
    """The bulk fetch is ~1,870 items over hours; a single bad item must not end it.

    Before this, an exception inside the download step propagated out of the loop: every
    remaining item was abandoned AND the run summary was lost, so the owner could not even
    see what had already been fetched. (Found by code review.)
    """
    db = tmp_path / "kb.db"
    seed_items(db, [(f"reel{i}", "reel", f"https://x/reel/reel{i}/") for i in range(4)])
    media_dir = tmp_path / "media"

    def exploding_downloader(url: str, dest: Path, **_kwargs: object) -> int:
        if "reel1" in str(dest):
            raise OSError("disk went away")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"x" * 10)
        return 10

    outcomes = [
        FetchResult(
            f"reel{i}",
            "success",
            media_type="video",
            files=(MediaFile(f"http://x/{i}.mp4", "video"),),
        )
        for i in range(4)
    ]
    with connect_stage(db, "fetch") as conn:
        initialise(conn)
        summary = run_fetch(
            conn,
            RecordingFakeFetcher({o.item_id: o for o in outcomes}),
            media_dir,
            pending_requests(conn),
            via="apify",
            downloader=exploding_downloader,
        )

    assert summary.fetched == 3, "the three healthy items must still be recorded"
    assert any("reel1" in e for e in summary.errors)
    with connect_stage(db, "fetch") as conn:
        statuses = dict(conn.execute("SELECT item_id, status FROM fetch_status").fetchall())
    assert statuses["reel1"] == "pending", "the failed item retries next run"
    assert statuses["reel3"] == "fetched"
