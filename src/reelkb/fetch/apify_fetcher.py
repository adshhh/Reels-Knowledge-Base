"""ApifyFetcher -- the memo23/instagram-video-downloader actor verified in M0.

``m0/02_fetch_apify.py`` is where the actor id, input schema and pricing were confirmed by
calling the Apify API directly (2026-09-19), and where a real constraint was discovered by
running, not documented anywhere: on a **non-paying** Apify account, the actor caps each run
at 5 billable events, and one post typically costs 4 of them (start + dataset-item + video +
cover) -- so a multi-item ``posts`` array silently truncates to ~1 item processed. The
workaround is one actor call per item.

``batch_size`` (from ``--batch-size``, default 1) exists so that changes without touching this
class: 1 keeps every run to a single item (safe for a non-paying account); a paid account can
raise it so more shortcodes ride in one actor call's ``posts`` array. Real network calls only
happen inside :meth:`ApifyFetcher.fetch`, and ``apify_client`` is imported there, not at
module level, so importing this module (e.g. for the CLI's ``--via`` dispatch) never trips the
unit-test import guard (AC-6.2).
"""

from __future__ import annotations

import os
from collections.abc import Iterator, Sequence
from typing import Any

from .types import FetchRequest, FetchResult, MediaFile

# memo23/instagram-video-downloader, verified live via the Apify API -- see m0/02_fetch_apify.py.
ACTOR_ID = "piwPghZZql1jcdYcH"


class ApifyFetcher:
    def __init__(self, batch_size: int = 1, token: str | None = None) -> None:
        self.batch_size = max(1, batch_size)
        self.token = token or os.environ.get("APIFY_TOKEN")

    def fetch(self, batch: Sequence[FetchRequest]) -> Iterator[FetchResult]:
        from apify_client import ApifyClient  # lazy: never imported by the unit test suite

        if not self.token:
            raise RuntimeError("APIFY_TOKEN is not set")
        client = ApifyClient(self.token)
        for i in range(0, len(batch), self.batch_size):
            sub_batch = batch[i : i + self.batch_size]
            yield from self._run_one_call(client, sub_batch)

    def _run_one_call(
        self, client: Any, sub_batch: Sequence[FetchRequest]
    ) -> Iterator[FetchResult]:
        by_id = {r.item_id: r for r in sub_batch}
        run_input = {
            "posts": [r.url for r in sub_batch],
            "downloadVideo": True,
            "downloadCover": True,
            "downloadCarouselImages": True,
            "downloadMusic": False,
            "storeFiles": True,
            "maxFileSizeMb": 100,
        }

        try:
            run = client.actor(ACTOR_ID).call(run_input=run_input, logger=None)
        except Exception as exc:  # vendor/network trouble: leave this whole sub-batch pending
            for r in sub_batch:
                yield FetchResult(r.item_id, "transient", reason=f"actor call failed: {exc}"[:300])
            return

        dataset = client.dataset(run.default_dataset_id)
        rows = list(dataset.iterate_items())
        matched: set[str] = set()
        for row in rows:
            item_id = self._match_item_id(row, by_id)
            if item_id is None:
                continue  # can't attribute this row to a request; leave it pending below
            matched.add(item_id)
            yield self._row_to_result(item_id, row)

        for r in sub_batch:
            if r.item_id not in matched:
                yield FetchResult(r.item_id, "transient", reason="no matching dataset row returned")

    @staticmethod
    def _match_item_id(row: dict[str, Any], by_id: dict[str, FetchRequest]) -> str | None:
        """Attribute one dataset row back to the request that asked for it.

        With batch_size=1 (the default) this is unambiguous: there is exactly one candidate.
        For a larger batch, memo23 does not echo the input item_id back, so this falls back to
        matching the returned shortcode/URL fields -- unverified against a real multi-item run
        (no paid Apify run was made to build this), flagged in the M3 report.
        """
        if len(by_id) == 1:
            return next(iter(by_id))
        code = row.get("shortCode") or row.get("shortcode")
        if code and code in by_id:
            return str(code)
        for item_id in by_id:
            if item_id in (row.get("url") or "") or item_id in (row.get("inputUrl") or ""):
                return item_id
        return None

    @staticmethod
    def _row_to_result(item_id: str, row: dict[str, Any]) -> FetchResult:
        error = row.get("error") or row.get("errorMessage")
        if error:
            return FetchResult(item_id, "dead", reason=str(error)[:300])

        video_url = row.get("videoUrl") or row.get("videoDownloadUrl")
        cover_url = row.get("coverUrl") or row.get("coverDownloadUrl")
        carousel = row.get("carouselMedia") or row.get("slides")
        duration = row.get("duration") or row.get("videoDuration")

        if carousel:
            files = tuple(
                MediaFile(
                    url=item.get("videoUrl") or item.get("url") or item.get("downloadUrl"),
                    media_type="video"
                    if (item.get("videoUrl") or item.get("isVideo"))
                    else "image",
                )
                for item in carousel
                if item.get("videoUrl") or item.get("url") or item.get("downloadUrl")
            )
            if files:
                return FetchResult(
                    item_id,
                    "success",
                    media_type="carousel",
                    files=files,
                    vendor_duration_s=duration,
                )
            # Transient, NOT dead: a carousel row with no usable slide urls is a malformed
            # response, not the vendor saying the post is gone. See the note below.
            return FetchResult(item_id, "transient", reason="carousel row had no usable slide urls")

        if video_url:
            return FetchResult(
                item_id,
                "success",
                media_type="video",
                files=(MediaFile(video_url, "video"),),
                vendor_duration_s=duration,
            )
        if cover_url:
            return FetchResult(
                item_id, "success", media_type="image", files=(MediaFile(cover_url, "image"),)
            )
        # Transient, NOT dead. 'dead' is terminal and never retried (AC-2.2), so it must be
        # reserved for the vendor explicitly telling us the post is gone -- the `error` branch
        # at the top of this function. A row that simply carries no media url means the actor
        # returned something unusable: a truncated run, the non-paying account's 5-billable-
        # event cap cutting a run short (see the module docstring), a quota truncation, a
        # transport hiccup. Marking those 'dead' would permanently burn live reels in the one
        # real bulk run this project gets, with no way to tell them apart from genuinely
        # deleted posts afterwards. types.py names this exact case ("an empty dataset row") as
        # the textbook transient. Found by the M3 checker, which caught the code contradicting
        # that docstring.
        return FetchResult(
            item_id, "transient", reason="no video/cover/carousel url in dataset row"
        )
