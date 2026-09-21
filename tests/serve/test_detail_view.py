"""AC-1.2: every card's detail view shows every non-empty channel labelled by source, omits
empty channels, and always links to the original Instagram URL.

Runs over every one of the 27 fake cards (fake_db.REELS), not a sample, so every awkward
combination the fake corpus was built to cover (all-empty-but-one, all three channels, etc.)
gets checked. The expected channel set is computed independently from the raw REEL fixture
fields (caption / ocr / transcript), not from Card.channels(), so this doesn't just assert
the app agrees with the contract layer's own logic.
"""

from __future__ import annotations

from html.parser import HTMLParser

from fastapi.testclient import TestClient

from reelkb.testing.fake_db import REELS, FakeReel


class _DetailParser(HTMLParser):
    """Pulls out the channel <h3> labels in order, and whether an Instagram link is present."""

    def __init__(self) -> None:
        super().__init__()
        self.channel_labels: list[str] = []
        self.instagram_href: str | None = None
        self._in_channel_h3 = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_d = dict(attrs)
        if tag == "h3":
            self._in_channel_h3 = True
        if tag == "a" and attrs_d.get("class") == "instagram-link":
            self.instagram_href = attrs_d.get("href")

    def handle_endtag(self, tag: str) -> None:
        if tag == "h3":
            self._in_channel_h3 = False

    def handle_data(self, data: str) -> None:
        if self._in_channel_h3:
            self.channel_labels.append(data.strip())


def _expected_labels(r: FakeReel) -> list[str]:
    labels = []
    if r.caption.strip():
        labels.append("Caption")
    if r.ocr:  # non-empty tuple of OCR strings
        labels.append("On-screen text")
    if r.transcript.strip():
        labels.append("Speech")
    return labels


def test_every_fake_card_shows_exactly_its_nonempty_channels(client: TestClient) -> None:
    assert REELS, "fixture is empty -- test would pass vacuously"
    for r in REELS:
        resp = client.get(f"/item/{r.item_id}")
        assert resp.status_code == 200, r.item_id

        parser = _DetailParser()
        parser.feed(resp.text)

        expected = _expected_labels(r)
        assert expected, f"{r.item_id} has zero channels -- should not exist"
        assert parser.channel_labels == expected, r.item_id

        # Every channel label rendered has non-empty text next to it -- no blank channel
        # (AC-1.2: "empty channels are omitted rather than shown blank").
        for label in ("Caption", "On-screen text", "Speech"):
            if label not in expected:
                assert label not in resp.text.split('class="actions"')[0], (r.item_id, label)

        assert parser.instagram_href == f"https://www.instagram.com/reel/{r.item_id}/", r.item_id


def test_detail_view_404s_for_unknown_item(client: TestClient) -> None:
    resp = client.get("/item/does-not-exist")
    assert resp.status_code == 404
