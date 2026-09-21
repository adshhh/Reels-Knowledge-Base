"""Which vendor responses may become terminal, and which may not (AC-2.2).

This is the decision that cannot be taken back. `dead` is terminal and never retried, so a
response wrongly classified `dead` permanently burns a live reel in the one real bulk run
this project gets -- and afterwards it is indistinguishable from a genuinely deleted post.
The safe direction is always `transient`: an item wrongly left pending costs one retry.

The M3 checker found both halves of this wrong and untested at once: Apify turned a
structurally-empty dataset row into `dead` (against types.py's own docstring, which names
that case as the textbook transient), and yt-dlp could not produce `dead` at all, so no item
could ever reach a terminal state through it.

No network, no yt_dlp import: both functions under test are pure, and take the vendor's
response as a plain dict or string.
"""

from __future__ import annotations

import pytest

from reelkb.fetch.apify_fetcher import ApifyFetcher
from reelkb.fetch.types import Outcome
from reelkb.fetch.ytdlp_fetcher import _classify

# --- Apify: dataset row -> outcome -------------------------------------------------------

VIDEO_ROW = {"videoUrl": "https://cdn/v.mp4", "duration": 31.5}
COVER_ROW = {"coverUrl": "https://cdn/c.jpg"}
CAROUSEL_ROW = {"carouselMedia": [{"url": "https://cdn/0.jpg"}, {"videoUrl": "https://cdn/1.mp4"}]}


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        # The ONLY route to terminal 'dead': the vendor explicitly says the post is gone.
        ({"error": "Post not found"}, "dead"),
        ({"errorMessage": "This post has been deleted"}, "dead"),
        # Everything unusable-but-unexplained is recoverable.
        ({}, "transient"),
        ({"videoUrl": None, "coverUrl": None}, "transient"),
        ({"carouselMedia": []}, "transient"),
        ({"carouselMedia": [{"caption": "no url here"}]}, "transient"),
        # Usable rows.
        (VIDEO_ROW, "success"),
        (COVER_ROW, "success"),
        (CAROUSEL_ROW, "success"),
    ],
)
def test_apify_row_becomes_terminal_only_when_the_vendor_says_the_post_is_gone(
    row: dict[str, object], expected: Outcome
) -> None:
    assert ApifyFetcher._row_to_result("SHORT1", row).outcome == expected


def test_an_empty_apify_row_is_never_dead() -> None:
    """The regression that matters: restore `dead` here and ~1,870 live reels are at risk.

    An empty row is what a truncated run returns -- including a run cut short by the
    non-paying account's 5-billable-event cap, which M0 measured as real behaviour on this
    exact account.
    """
    result = ApifyFetcher._row_to_result("SHORT1", {})
    assert result.outcome == "transient"
    assert result.reason is not None and "no video/cover/carousel url" in result.reason


def test_apify_carousel_keeps_only_slides_that_have_a_url() -> None:
    row = {"carouselMedia": [{"url": "https://cdn/0.jpg"}, {"caption": "broken slide"}]}
    result = ApifyFetcher._row_to_result("SHORT1", row)
    assert result.outcome == "success"
    assert result.media_type == "carousel"
    assert [f.url for f in result.files] == ["https://cdn/0.jpg"]


def test_apify_error_wins_even_when_the_row_also_carries_media() -> None:
    """A row with both an error and a url is the vendor contradicting itself; trust the error."""
    row = {"error": "Post not found", "videoUrl": "https://cdn/stale.mp4"}
    assert ApifyFetcher._row_to_result("SHORT1", row).outcome == "dead"


def test_apify_records_the_vendor_duration_it_was_given() -> None:
    assert ApifyFetcher._row_to_result("SHORT1", VIDEO_ROW).vendor_duration_s == 31.5


# --- yt-dlp: error message -> outcome ----------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "ERROR: [Instagram] Video unavailable",
        "ERROR: unable to download video data: HTTP Error 404: Not Found",
        "The post has been removed by its owner",
        "This content is no longer available",
    ],
)
def test_ytdlp_recognises_a_post_that_is_genuinely_gone(message: str) -> None:
    outcome, is_login_wall = _classify(message)
    assert outcome == "dead"
    assert not is_login_wall


@pytest.mark.parametrize(
    "message",
    [
        "ERROR: Please log in to continue",
        "HTTP Error 429: Too Many Requests",
        "The requested content is not available, rate-limit reached",
        "This account is private",
        "Unable to connect: timed out",
        "",
    ],
)
def test_ytdlp_leaves_anything_short_of_proof_recoverable(message: str) -> None:
    assert _classify(message)[0] == "transient"


def test_a_private_account_counts_toward_the_login_wall_stop_and_is_not_dead() -> None:
    """'private' matches both hint lists. Login wall must win -- ambiguity stays recoverable.

    A private account is the ambiguous case: the post exists, we just cannot see it logged
    out. Calling it dead would discard a reel that a later top-up could still fetch.
    """
    outcome, is_login_wall = _classify("ERROR: This account is private")
    assert outcome == "transient"
    assert is_login_wall


def test_a_login_wall_never_produces_a_terminal_state() -> None:
    """Five of these in a row stop the batch; none of them may mark an item dead."""
    for message in ("Please log in", "rate limit exceeded", "HTTP Error 429"):
        assert _classify(message)[0] != "dead"
