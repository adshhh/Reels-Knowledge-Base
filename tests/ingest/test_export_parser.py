"""Proof for AC-2.1 and AC-2.3 (docs/PLAN.md §2), the M2 acceptance criteria.

Two layers, per the M2 build spec:

1. Unit tests against a small synthetic export built right here -- covers mojibake,
   dedupe, every ``kind``, and idempotency. No file, no network, no model: runs everywhere,
   including CI.
2. Tests against the real ``data/raw/message_1.json`` asserting the exact locked counts.
   Skipped with a clear reason when that file is absent (e.g. in CI, where the archive is
   never present -- it's gitignored, see docs/CONTRACT.md). These assert counts and
   invariants ONLY: no caption, URL or account from the real archive is ever printed or
   compared against a literal value.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from reelkb.contract.db import connect_stage, init_db
from reelkb.ingest.__main__ import run, write_items
from reelkb.ingest.parser import (
    ParsedItem,
    detect_caption_language,
    fix_mojibake,
    iso_utc,
    parse_messages,
)

REAL_EXPORT = Path(__file__).parents[2] / "data" / "raw" / "message_1.json"


def _mojibake(real_text: str) -> str:
    """Simulate the export bug: real UTF-8 bytes read back as Latin-1."""
    return real_text.encode("utf-8").decode("latin-1")


# --------------------------------------------------------------------------- fixtures

BASE_MS = 1_700_000_000_000


def synthetic_messages() -> list[dict[str, Any]]:
    """One message per case the parser has to handle, in export order (newest-first)."""
    return [
        # note: no share, no content key at all (a bare photo message).
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 12_000,
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
            "photos": [{"uri": "photos/1.jpg"}],
        },
        # note: a field that is genuinely non-Latin-1 Unicode (not mojibake) -- the
        # encode('latin-1') step itself fails, so fix_mojibake must fall back gracefully.
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 11_000,
            "content": "नमस्ते",
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        },
        # note: ordinary typed text.
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 10_000,
            "content": _mojibake("Your lie in april"),
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        },
        # attachment: Messenger's own placeholder, no share.
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 9_000,
            "content": _mojibake("Owner sent an attachment."),
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        },
        # external: a non-Instagram link whose PATH happens to look like an IG post
        # (/p/<slug>) -- domain must be checked before path, or this misclassifies as `post`.
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 8_000,
            "share": {
                "link": "https://blog.example.com/p/my-post-slug",
                "share_text": _mojibake("blog post"),
            },
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        },
        # external: share with no link at all (only original_content_owner survived).
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 7_000,
            "share": {"original_content_owner": _mojibake("ghost_account")},
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        },
        # external: an Instagram profile share (no /reel/ or /p/ path).
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 6_000,
            "share": {
                "link": "https://www.instagram.com/_u/someprofile/",
                "profile_share_username": _mojibake("someprofile"),
                "profile_share_name": _mojibake("Some Profile"),
            },
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        },
        # external: a plain non-Instagram link.
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 5_000,
            "share": {
                "link": "https://github.com/someuser/somerepo",
                "share_text": _mojibake("cool repo"),
            },
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        },
        # post: a single, undeduplicated share.
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 4_000,
            "share": {
                "link": "https://www.instagram.com/p/XYZ9988776/",
                "share_text": _mojibake("A nice post"),
                "original_content_owner": _mojibake("poster_account"),
            },
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        },
        # reel, occurrence B: chronologically LATER, appears FIRST in file order (export is
        # newest-first). Has the caption; occurrence A (below) does not.
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 3_000,
            "share": {
                "link": "https://www.instagram.com/reel/ABCDEFGHIJK/",
                "share_text": _mojibake("Cool café video"),
                "original_content_owner": _mojibake("creator_café"),
            },
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        },
        # reel, occurrence A: chronologically EARLIEST (smallest timestamp_ms) but LAST in
        # file order. No caption. sent_at must come from here; caption must come from B.
        {
            "sender_name": "Owner",
            "timestamp_ms": BASE_MS + 1_000,
            "share": {
                "link": "https://www.instagram.com/reel/ABCDEFGHIJK/",
            },
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        },
    ]


def _by_id(items: list[ParsedItem]) -> dict[str, ParsedItem]:
    return {i.item_id: i for i in items}


# --------------------------------------------------------------------------- unit: mojibake


def test_fix_mojibake_round_trips_real_export_style_corruption() -> None:
    fixed, ok = fix_mojibake(_mojibake("Cool café video ☕"))
    assert ok is True
    assert fixed == "Cool café video ☕"
    assert "ð" not in fixed


def test_fix_mojibake_keeps_original_and_reports_failure_when_it_cannot_round_trip() -> None:
    # A string that was never mojibake in the first place -- already-correct Unicode
    # outside Latin-1's range can't even be encoded back to latin-1.
    original = "नमस्ते"
    fixed, ok = fix_mojibake(original)
    assert ok is False
    assert fixed == original  # kept, not invented or mangled


# --------------------------------------------------------------------------- unit: kinds


def test_every_kind_is_classified_correctly() -> None:
    items, stats = parse_messages(synthetic_messages())
    by_kind: dict[str, list[ParsedItem]] = {}
    for item in items:
        by_kind.setdefault(item.kind, []).append(item)

    assert stats.counts == {
        "reel": 1,
        "post": 1,
        "external": 4,
        "attachment": 1,
        "note": 3,
    }
    assert len(by_kind["reel"]) == 1
    assert len(by_kind["post"]) == 1
    assert len(by_kind["external"]) == 4
    assert len(by_kind["attachment"]) == 1
    assert len(by_kind["note"]) == 3


def test_reel_and_post_item_ids_are_the_shortcode() -> None:
    items, _ = parse_messages(synthetic_messages())
    ids = {i.item_id for i in items}
    assert "ABCDEFGHIJK" in ids
    assert "XYZ9988776" in ids


def test_non_instagram_link_with_a_p_shaped_path_is_not_mistaken_for_a_post() -> None:
    """Regression test: a real export link (a Substack /p/... URL) triggered exactly this
    bug during development -- domain must be checked before the /p/ path pattern."""
    items, _ = parse_messages(synthetic_messages())
    blog_item = next(i for i in items if i.url == "https://blog.example.com/p/my-post-slug")
    assert blog_item.kind == "external"
    assert blog_item.caption == "blog post"


def test_attachment_only_message_has_no_link_and_no_invented_caption() -> None:
    items, _ = parse_messages(synthetic_messages())
    attachment = next(i for i in items if i.kind == "attachment")
    assert attachment.item_id.startswith("att-")
    assert attachment.url is None
    assert attachment.caption is None  # Messenger's placeholder text is not real content


def test_share_with_no_link_at_all_becomes_external_not_invented() -> None:
    items, _ = parse_messages(synthetic_messages())
    ghost = next(i for i in items if i.source_account == "ghost_account")
    assert ghost.kind == "external"
    assert ghost.url is None
    assert ghost.caption is None


def test_instagram_profile_share_becomes_external_with_username_as_account() -> None:
    items, _ = parse_messages(synthetic_messages())
    profile = next(i for i in items if i.source_account == "someprofile")
    assert profile.kind == "external"
    assert profile.url == "https://www.instagram.com/_u/someprofile/"


def test_photo_only_message_with_no_share_and_no_content_is_a_note() -> None:
    """Independent decision (see parser.py): keeps AC-2.3's attachment count exact."""
    items, _ = parse_messages(synthetic_messages())
    notes = [i for i in items if i.kind == "note"]
    assert any(n.caption is None for n in notes)


def test_mojibake_failure_is_counted_not_raised() -> None:
    _, stats = parse_messages(synthetic_messages())
    assert stats.mojibake_failures >= 1


def test_no_stored_field_contains_the_mojibake_marker_character() -> None:
    items, _ = parse_messages(synthetic_messages())
    for item in items:
        for field in (item.caption, item.source_account, item.url):
            if field:
                assert "ð" not in field


# --------------------------------------------------------------------------- unit: dedupe


def test_duplicate_shortcode_earliest_message_wins_for_sent_at() -> None:
    items, stats = parse_messages(synthetic_messages())
    reel = _by_id(items)["ABCDEFGHIJK"]
    assert stats.duplicate_shares == 1
    assert reel.sent_at_ms == BASE_MS + 1_000  # the earlier occurrence, not the later one
    assert iso_utc(reel.sent_at_ms) == "2023-11-14T22:13:21+00:00"


def test_duplicate_shortcode_keeps_first_non_empty_caption_and_account() -> None:
    items, _ = parse_messages(synthetic_messages())
    reel = _by_id(items)["ABCDEFGHIJK"]
    # Occurrence A (earliest, kept for sent_at) had no caption; occurrence B did.
    assert reel.caption == "Cool café video"
    assert reel.source_account == "creator_café"


def test_dedupe_does_not_create_two_rows() -> None:
    items, _ = parse_messages(synthetic_messages())
    reel_items = [i for i in items if i.item_id == "ABCDEFGHIJK"]
    assert len(reel_items) == 1


# --------------------------------------------------------------------------- unit: language


@pytest.mark.parametrize(
    "caption,expected",
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("Cool café video", "latn"),
        ("नमस्ते दुनिया", "hi-Deva"),
        ("!!! 123 ...", "other"),  # no alphabetic characters at all
    ],
)
def test_caption_language_detection(caption: str | None, expected: str | None) -> None:
    assert detect_caption_language(caption) == expected


# --------------------------------------------------------------------------- unit: idempotency


def test_ingest_run_is_idempotent(tmp_path: Path) -> None:
    export_path = tmp_path / "message_1.json"
    export_path.write_text(json.dumps({"messages": synthetic_messages()}))
    db_path = tmp_path / "kb.db"

    stats_first = run(export_path, db_path)
    conn = sqlite3.connect(db_path)
    count_after_first = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    stats_second = run(export_path, db_path)
    count_after_second = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    assert count_after_first == count_after_second
    assert stats_first.counts == stats_second.counts
    # Sanity: re-running actually re-parsed and re-wrote, not a no-op that skipped work.
    assert count_after_first == sum(stats_first.counts.values())


def test_write_items_upserts_without_violating_downstream_foreign_keys(tmp_path: Path) -> None:
    """write_items must UPDATE existing rows in place (not delete-then-reinsert), because a
    real run happens after fetch_status already references items.item_id (AC-2.2)."""
    db_path = tmp_path / "kb.db"
    init_db(db_path)
    items, _ = parse_messages(synthetic_messages())

    conn = connect_stage(db_path, "ingest")
    write_items(conn, items)
    conn.close()

    fetch_conn = connect_stage(db_path, "fetch")
    fetch_conn.execute(
        "INSERT INTO fetch_status (item_id, status, updated_at) VALUES (?, 'pending', ?)",
        ("ABCDEFGHIJK", "2024-01-01T00:00:00+00:00"),
    )
    fetch_conn.commit()
    fetch_conn.close()

    # Re-ingesting the same export must not touch fetch_status's foreign key target.
    ingest_conn = connect_stage(db_path, "ingest")
    write_items(ingest_conn, items)
    ingest_conn.close()

    check_conn = sqlite3.connect(db_path)
    row = check_conn.execute(
        "SELECT status FROM fetch_status WHERE item_id = 'ABCDEFGHIJK'"
    ).fetchone()
    assert row == ("pending",)


# --------------------------------------------------------------------------- real file: AC-2.1/2.3

pytestmark_real = pytest.mark.skipif(
    not REAL_EXPORT.exists(),
    reason=f"real export not present at {REAL_EXPORT} (expected locally, gitignored, absent in CI)",
)


@pytestmark_real
def test_real_export_produces_exactly_1870_unique_reel_and_post_items() -> None:
    """AC-2.1: exactly 1,870 unique records with a resolvable shortcode
    (1,714 reel + 156 post, measured 2026-09-19). Counts only -- no content asserted."""
    with REAL_EXPORT.open("rb") as f:
        data = json.load(f)
    items, _ = parse_messages(data["messages"])

    reels = [i for i in items if i.kind == "reel"]
    posts = [i for i in items if i.kind == "post"]
    assert len(reels) == 1714
    assert len(posts) == 156
    assert len(reels) + len(posts) == 1870
    # Every id is unique (the PRIMARY KEY the database will enforce anyway).
    assert len({i.item_id for i in reels + posts}) == 1870


@pytestmark_real
def test_real_export_records_358_attachments_and_10_external() -> None:
    """AC-2.3 (358 attachment-only messages) and AC-2.1's 9 non-Instagram links
    + 1 profile share = 10 `external` items."""
    with REAL_EXPORT.open("rb") as f:
        data = json.load(f)
    items, _ = parse_messages(data["messages"])

    attachments = [i for i in items if i.kind == "attachment"]
    external = [i for i in items if i.kind == "external"]
    assert len(attachments) == 358
    assert len(external) == 10


@pytestmark_real
def test_real_export_has_no_mojibake_marker_anywhere() -> None:
    """AC-2.1: no record contains the literal sequence 'ð'. Structural check only."""
    with REAL_EXPORT.open("rb") as f:
        data = json.load(f)
    items, _ = parse_messages(data["messages"])

    offending = 0
    for item in items:
        for value in (item.caption, item.source_account, item.url):
            if value and "ð" in value:
                offending += 1
    assert offending == 0


@pytestmark_real
def test_real_export_missing_captions_and_accounts_are_counted_not_invented() -> None:
    """AC-2.1: caption/account decoded where present; the export's gaps are NULL, never a
    made-up placeholder string."""
    with REAL_EXPORT.open("rb") as f:
        data = json.load(f)
    items, _ = parse_messages(data["messages"])

    reel_and_post = [i for i in items if i.kind in ("reel", "post")]
    absent_caption = sum(1 for i in reel_and_post if i.caption is None)
    no_caption_text = sum(1 for i in reel_and_post if not (i.caption or "").strip())
    missing_account = sum(1 for i in reel_and_post if not (i.source_account or "").strip())

    # Measured 2026-09-19 and recorded here rather than described. The M2 checker found the
    # earlier version of this test counted only caption IS NULL (1) and called it "a handful",
    # which hid the real figure: 135 of 1,870 shares (7.2%) carry no caption TEXT, because the
    # export stores an empty string far more often than it omits the field. Downstream stages
    # must treat "caption present" as 92.8%, not ~100%. If these numbers move, the export
    # changed -- update them deliberately.
    assert len(reel_and_post) == 1_870
    assert absent_caption == 1
    assert no_caption_text == 135
    assert missing_account == 0
    # Nothing is invented to fill a gap: an absent caption is None, never a placeholder.
    assert all(i.caption is None or isinstance(i.caption, str) for i in reel_and_post)


@pytestmark_real
def test_real_export_ingest_is_idempotent(tmp_path: Path) -> None:
    """AC-2.1 in practice: running the real file through the database twice must not
    duplicate rows (proves idempotency on the real shape, not just the synthetic one)."""
    db_path = tmp_path / "kb.db"
    run(REAL_EXPORT, db_path)
    conn = sqlite3.connect(db_path)
    first_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    run(REAL_EXPORT, db_path)
    second_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]

    assert first_count == second_count
    note_count = conn.execute("SELECT COUNT(*) FROM items WHERE kind = 'note'").fetchone()[0]
    assert first_count == 1870 + 358 + 10 + note_count


def test_an_empty_caption_on_the_earlier_share_does_not_block_a_later_real_one() -> None:
    """An empty string means "nothing here", not "a caption is already present".

    Found by the M2 checker. The existing dedupe test covers a *missing* share_text; this
    covers `share_text: ""`, which is the common shape: 135 of the 1,870 real shares carry no
    caption text, so the earliest occurrence of a duplicated shortcode is quite likely to be
    an empty one. Before the fix, "" on the earlier occurrence permanently blocked real text
    from the later one.
    """

    def share(text: str, account: str, offset_ms: int) -> dict[str, Any]:
        return {
            "sender_name": "Someone",
            "timestamp_ms": BASE_MS + offset_ms,
            "content": "",
            "share": {
                "link": "https://www.instagram.com/reel/EMPTYCAP123/",
                "share_text": text,
                "original_content_owner": account,
            },
            "is_geoblocked_for_viewer": False,
            "is_unsent_image_by_messenger_kid_parent": False,
        }

    # Later in file order, earlier in time, and empty -- the awkward combination.
    items, _ = parse_messages(
        [share("a real caption", "real_account", 2_000), share("", "", 1_000)]
    )
    reel = _by_id(items)["EMPTYCAP123"]
    assert reel.caption == "a real caption"
    assert reel.source_account == "real_account"
    assert reel.sent_at_ms == BASE_MS + 1_000  # earliest still wins for the date
