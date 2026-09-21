"""The shapes fetch code passes around.

A ``Fetcher`` takes a batch of :class:`FetchRequest` (one per item still ``pending``) and
yields a :class:`FetchResult` per item as it finishes -- not necessarily all at once and not
necessarily in order, so the orchestrator can commit each item to the database the moment its
outcome (and, for a success, its media) is known (AC-8.1).
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol

Outcome = Literal["success", "dead", "transient"]
MediaKind = Literal["video", "image"]
MediaTypeField = Literal["video", "image", "carousel"]


@dataclass(frozen=True)
class FetchRequest:
    """One pending item asking to be fetched."""

    item_id: str
    url: str


@dataclass(frozen=True)
class MediaFile:
    """One file a vendor says it can hand back -- a video, a single image, or one carousel slide."""

    url: str
    media_type: MediaKind


@dataclass(frozen=True)
class FetchResult:
    """What a vendor found for one item.

    - ``success``: ``files`` holds one or more :class:`MediaFile` (more than one only for a
      carousel post) and ``media_type`` says which of video / image / carousel it is.
    - ``dead``: the vendor is sure the post is gone (deleted, private, not found) -- terminal,
      never retried.
    - ``transient``: something went wrong that isn't the vendor telling us the post is gone
      (a network blip, a rate limit, an empty dataset row). The item is left ``pending`` and
      retried on the next run.
    """

    item_id: str
    outcome: Outcome
    reason: str | None = None
    media_type: MediaTypeField | None = None
    files: tuple[MediaFile, ...] = field(default_factory=tuple)
    vendor_duration_s: float | None = None


class Fetcher(Protocol):
    def fetch(self, batch: Sequence[FetchRequest]) -> Iterator[FetchResult]:
        """Yield one FetchResult per item in ``batch`` as each finishes.

        A fetcher that stops partway (e.g. YtDlpFetcher after 5 consecutive login-wall
        errors) simply yields fewer results than were asked for; items it never yields for
        stay 'pending' and are retried next run.
        """
        ...
