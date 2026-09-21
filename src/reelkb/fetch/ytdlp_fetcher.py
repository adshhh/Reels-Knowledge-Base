"""YtDlpFetcher -- logged-out, throttled yt-dlp for monthly top-ups (decisions/002, D18).

Never logs in: no cookies, no browser cookie jar. A random 10-30s delay between items is the
politeness budget that keeps a top-up batch (<100/month) from tripping a rate limit --
``m0/03_fetch_ytdlp.py`` established these numbers, and the same 5-consecutive-failure stop
rule, by running against the real site. After 5 consecutive login-wall/rate-limit-shaped
errors, this fetcher stops yielding entirely for the rest of the batch: those items are never
seen by ``run_fetch``, so they stay 'pending' rather than being marked dead or retried in a
tight loop against a site that has started refusing every request.

Unlike ``m0/03_fetch_ytdlp.py`` (which lets yt-dlp download the file directly), this fetcher
only *resolves* the direct media URL (``download=False``) and hands it to the shared
``download.py`` step, so both vendors go through the same isolated, temp-name-then-rename
download path. This is an independent decision made for M3 (see the build report) and is
unverified against the real site -- only exercised here by fake fetchers in unit tests, per
the "no real vendor calls in unit tests" rule; a ``realmodel``-marked test would be the way to
check it for real.
"""

from __future__ import annotations

import random
import time
from collections.abc import Iterator, Sequence
from typing import Any

from .types import FetchRequest, FetchResult, MediaFile, Outcome

FFMPEG_LOCATION = "/opt/homebrew/bin"
MIN_DELAY_SEC = 10
MAX_DELAY_SEC = 30
CONSECUTIVE_FAILURE_STOP = 5

LOGIN_WALL_HINTS = (
    "login",
    "log in",
    "rate-limit",
    "rate limit",
    "429",
    "requested content is not available",
    "restricted",
    "private",
)


# Messages that mean the post itself is gone, not that we were blocked. Without these, a
# deleted reel yields 'transient' forever: it stays 'pending', is re-requested on every future
# run, and no item can ever reach a terminal state through this fetcher -- which is AC-2.2's
# whole requirement. Found by the M3 checker.
#
# Deliberately narrow, and checked AFTER the login-wall hints. A login wall is the ambiguous
# case ("restricted", "private" could mean either), and misreading one as 'dead' would burn a
# live reel permanently, so ambiguity resolves to 'transient' -- the recoverable direction.
GONE_HINTS = (
    "video unavailable",
    "post unavailable",
    "404",
    "not found",
    "has been removed",
    "no longer available",
    "this page isn't available",
    "deleted",
)


def _is_login_wall(message: str) -> bool:
    low = message.lower()
    return any(hint in low for hint in LOGIN_WALL_HINTS)


def _classify(message: str) -> tuple[Outcome, bool]:
    """Map a yt-dlp error to an outcome and whether it counts toward the login-wall stop.

    Returns ('transient'|'dead', is_login_wall). Login wall wins ties: see GONE_HINTS.
    """
    if _is_login_wall(message):
        return "transient", True
    low = message.lower()
    if any(hint in low for hint in GONE_HINTS):
        return "dead", False
    return "transient", False


class YtDlpFetcher:
    def __init__(
        self,
        sleep: Any = time.sleep,
        rand: Any = random.uniform,
        min_delay: float = MIN_DELAY_SEC,
        max_delay: float = MAX_DELAY_SEC,
    ) -> None:
        self._sleep = sleep
        self._rand = rand
        self._min_delay = min_delay
        self._max_delay = max_delay

    def fetch(self, batch: Sequence[FetchRequest]) -> Iterator[FetchResult]:
        import yt_dlp  # lazy: never imported by the unit test suite

        consecutive_login_wall = 0
        for i, request in enumerate(batch):
            info, error = self._extract(yt_dlp, request.url)
            if info is not None:
                consecutive_login_wall = 0
                yield self._result_from_info(request.item_id, info)
            else:
                outcome, is_login_wall = _classify(error or "")
                consecutive_login_wall = consecutive_login_wall + 1 if is_login_wall else 0
                yield FetchResult(request.item_id, outcome, reason=error)
                if consecutive_login_wall >= CONSECUTIVE_FAILURE_STOP:
                    return  # rest of the batch stays untouched -> stays 'pending'

            if i < len(batch) - 1:
                self._sleep(self._rand(self._min_delay, self._max_delay))

    @staticmethod
    def _extract(yt_dlp_module: Any, url: str) -> tuple[dict[str, Any] | None, str | None]:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "cookiesfrombrowser": None,
            "cookiefile": None,
            "ffmpeg_location": FFMPEG_LOCATION,
            "noplaylist": True,
            "retries": 1,
            "socket_timeout": 30,
        }
        try:
            with yt_dlp_module.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            return info, None
        except Exception as exc:
            return None, str(exc)[:400]

    @staticmethod
    def _result_from_info(item_id: str, info: dict[str, Any]) -> FetchResult:
        url = info.get("url")
        if not url:
            formats = info.get("formats") or []
            url = formats[-1].get("url") if formats else None
        if not url:
            return FetchResult(item_id, "transient", reason="yt-dlp returned no downloadable url")
        return FetchResult(
            item_id,
            "success",
            media_type="video",
            files=(MediaFile(url, "video"),),
            vendor_duration_s=info.get("duration"),
        )
