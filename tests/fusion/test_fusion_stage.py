"""End-to-end tests for the fusion stage orchestration (`reelkb.fusion.stage`).

Uses `FakeFusionClient` (tests/fusion/fake_model_client.py) throughout — no network call, no
model load (AC-6.2). Real Groq usage is exercised only in `@pytest.mark.realmodel` tests
elsewhere, never here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reelkb.contract.db import connect_readonly, connect_stage, init_db
from reelkb.fusion.stage import FusionParseError, parse_model_output, run
from reelkb.fusion.types import ModelResponse
from reelkb.testing.fake_db import REELS

from .fake_model_client import FakeFusionClient

NOW = "2026-09-19T00:00:00+00:00"

# FAKEml001's caption in reelkb.testing.fake_db -- a substring unique to that item's user
# prompt, used to script FakeFusionClient responses without needing item_id in the prompt
# (the real prompt template never includes it; the model only ever sees the three channels).
FAKEML001_MARKER = "Best free course I've found"


def _fusion_rows(db: Path) -> dict[str, dict[str, Any]]:
    conn = connect_readonly(db)
    out = {}
    for row in conn.execute("SELECT * FROM fusion"):
        out[row["item_id"]] = dict(row)
    return out


# --------------------------------------------------------------------------- happy path


def test_every_pending_item_gets_a_fusion_row(unfused_db: Path) -> None:
    client = FakeFusionClient()
    with connect_stage(unfused_db, "fusion") as conn:
        summary = run(conn, client)
    rows = _fusion_rows(unfused_db)
    assert set(rows) == {r.item_id for r in REELS}
    assert summary.items_written == len(REELS)
    assert summary.items_considered == len(REELS)
    assert summary.items_failed == []


def test_fusion_row_shape_matches_the_gated_output(unfused_db: Path) -> None:
    client = FakeFusionClient(
        responses={
            FAKEML001_MARKER: {
                "title": "Free deep learning course from fast.ai",
                "summary": "A free, practical deep learning course.",
                "bullets": ["covers deep learning basics", "hands-on projects"],
                "entities": {"urls": ["course.fast.ai"], "handles": [], "titles": []},
                "language": "en",
            }
        }
    )
    with connect_stage(unfused_db, "fusion") as conn:
        run(conn, client)
    row = _fusion_rows(unfused_db)["FAKEml001"]
    assert row["title"] == "Free deep learning course from fast.ai"
    assert json.loads(row["bullets"]) == ["covers deep learning basics", "hands-on projects"]
    assert json.loads(row["entities"])["urls"] == ["course.fast.ai"]
    assert row["model"]
    assert row["completed_at"]


# --------------------------------------------------------- resumability / idempotency


def test_second_run_is_a_no_op_and_writes_no_duplicates(unfused_db: Path) -> None:
    client = FakeFusionClient()
    with connect_stage(unfused_db, "fusion") as conn:
        first = run(conn, client)
    calls_after_first = len(client.calls)

    with connect_stage(unfused_db, "fusion") as conn:
        second = run(conn, client)

    assert first.items_written == len(REELS)
    assert second.items_considered == 0
    assert second.items_written == 0
    assert len(client.calls) == calls_after_first  # no new model calls on the second run
    assert len(_fusion_rows(unfused_db)) == len(REELS)  # no duplicate rows


def test_killed_mid_run_and_restarted_finishes_the_rest(unfused_db: Path) -> None:
    """Simulates AC-8.1's pattern for this stage: process half, "restart" (a fresh connection,
    as a real restart would give us), and confirm the rest gets done with no duplication."""
    client = FakeFusionClient()
    half = len(REELS) // 2
    with connect_stage(unfused_db, "fusion") as conn:
        run(conn, client, limit=half)
    assert len(_fusion_rows(unfused_db)) == half

    with connect_stage(unfused_db, "fusion") as conn:
        run(conn, client)  # "restart": no limit, picks up whatever's left
    rows = _fusion_rows(unfused_db)
    assert len(rows) == len(REELS)
    assert set(rows) == {r.item_id for r in REELS}


def test_limit_processes_at_most_n_items(unfused_db: Path) -> None:
    client = FakeFusionClient()
    with connect_stage(unfused_db, "fusion") as conn:
        summary = run(conn, client, limit=3)
    assert summary.items_written == 3
    assert len(_fusion_rows(unfused_db)) == 3


# --------------------------------------------------------------------------- zero-channel items


@pytest.fixture
def db_with_a_silent_blank_item(tmp_path: Path) -> Path:
    """A minimal, hand-built DB (not the shared fake corpus) with one item that has ocr_runs
    and transcripts rows but nothing readable in any channel -- the case §3/M5 calls out:
    "items with zero non-empty channels get no fusion row."
    """
    db = tmp_path / "kb.db"
    init_db(db)
    with connect_stage(db, "ingest") as conn:
        conn.execute(
            "INSERT INTO items VALUES (?, 'reel', ?, ?, ?, ?, ?)",
            (
                "FAKEblank01",
                "https://www.instagram.com/reel/FAKEblank01/",
                None,
                "nobody",
                NOW,
                None,
            ),
        )
    with connect_stage(db, "ocr") as conn:
        # No ocr_verbatim rows at all: nothing readable was found.
        conn.execute("INSERT INTO ocr_runs VALUES (?, 5, 0, NULL, ?)", ("FAKEblank01", NOW))
    with connect_stage(db, "speech") as conn:
        conn.execute(
            "INSERT INTO transcripts VALUES (?, 0, '', NULL, 0, 'silero', ?)",
            ("FAKEblank01", NOW),
        )
    return db


def test_zero_channel_item_gets_no_fusion_row_and_is_counted(
    db_with_a_silent_blank_item: Path,
) -> None:
    client = FakeFusionClient()
    with connect_stage(db_with_a_silent_blank_item, "fusion") as conn:
        summary = run(conn, client)
    assert summary.items_written == 0
    assert summary.items_skipped_empty == ["FAKEblank01"]
    assert _fusion_rows(db_with_a_silent_blank_item) == {}
    assert client.calls == []  # never even worth a model call


@pytest.fixture
def db_with_ocr_but_no_transcript(tmp_path: Path) -> Path:
    """An item with an ocr_runs row but no transcripts row: not a fusion candidate yet (the
    stage requires both, per its docstring/query), so it must not appear as pending."""
    db = tmp_path / "kb.db"
    init_db(db)
    with connect_stage(db, "ingest") as conn:
        conn.execute(
            "INSERT INTO items VALUES (?, 'reel', ?, ?, ?, ?, ?)",
            (
                "FAKEnotranscript",
                "https://www.instagram.com/reel/FAKEnotranscript/",
                "a caption",
                "acct",
                NOW,
                "en",
            ),
        )
    with connect_stage(db, "ocr") as conn:
        conn.execute(
            "INSERT INTO ocr_verbatim VALUES (?, 0.0, 'some text', 0.9, NULL)",
            ("FAKEnotranscript",),
        )
        conn.execute("INSERT INTO ocr_runs VALUES (?, 5, 0, 'en', ?)", ("FAKEnotranscript", NOW))
    return db


def test_item_without_a_transcript_row_is_not_yet_a_candidate(
    db_with_ocr_but_no_transcript: Path,
) -> None:
    client = FakeFusionClient()
    with connect_stage(db_with_ocr_but_no_transcript, "fusion") as conn:
        summary = run(conn, client)
    assert summary.items_considered == 0
    assert client.calls == []


# ------------------------------------------------------------------- the gate, wired in end-to-end


def test_fidelity_gate_runs_inside_the_stage_and_drops_fakes(unfused_db: Path) -> None:
    client = FakeFusionClient(
        responses={
            FAKEML001_MARKER: {
                "title": "Free deep learning course from fast.ai",
                "summary": "Also see totally-fake-domain.biz for extra notes",
                "bullets": [],
                "entities": {
                    "urls": ["course.fast.ai", "totally-fake-domain.biz"],
                    "handles": ["@invented_handle"],
                    "titles": [],
                },
                "language": "en",
            }
        }
    )
    with connect_stage(unfused_db, "fusion") as conn:
        summary = run(conn, client)
    row = _fusion_rows(unfused_db)["FAKEml001"]
    entities = json.loads(row["entities"])
    assert entities["urls"] == ["course.fast.ai"]
    assert entities["handles"] == []
    assert "totally-fake-domain.biz" not in row["summary"]
    dropped = json.loads(row["dropped_entities"])
    dropped_values = {d["value"] for d in dropped}
    assert "totally-fake-domain.biz" in dropped_values
    assert "@invented_handle" in dropped_values
    assert summary.dropped_entities_count == len(dropped)
    assert summary.dropped_entities_count >= 3


# --------------------------------------------------------------------------- malformed model output


def test_malformed_json_is_recorded_as_failed_not_crashed(unfused_db: Path) -> None:
    client = FakeFusionClient(raw_text={FAKEML001_MARKER: "not json at all {{{"})
    with connect_stage(unfused_db, "fusion") as conn:
        summary = run(conn, client)
    failed_ids = [item_id for item_id, _reason in summary.items_failed]
    assert "FAKEml001" in failed_ids
    assert "FAKEml001" not in _fusion_rows(unfused_db)
    # every other item still gets processed
    assert summary.items_written == len(REELS) - 1


def test_json_wrapped_in_markdown_fence_is_tolerated(unfused_db: Path) -> None:
    fenced = (
        "```json\n"
        + json.dumps(
            {
                "title": "t",
                "summary": "s",
                "bullets": [],
                "entities": {"urls": [], "handles": [], "titles": []},
                "language": "en",
            }
        )
        + "\n```"
    )
    client = FakeFusionClient(raw_text={"FAKEml001": fenced})
    with connect_stage(unfused_db, "fusion") as conn:
        summary = run(conn, client)
    assert summary.items_failed == []
    assert "FAKEml001" in _fusion_rows(unfused_db)


# ------------------------------------------------------- parse_model_output unit tests


def test_parse_model_output_valid() -> None:
    draft = parse_model_output(
        json.dumps(
            {
                "title": "t",
                "summary": "s",
                "bullets": ["a", "b"],
                "entities": {"urls": ["x.com"], "handles": [], "titles": []},
                "language": "en",
            }
        )
    )
    assert draft.title == "t"
    assert draft.bullets == ["a", "b"]
    assert draft.entities["urls"] == ["x.com"]
    assert draft.language == "en"


def test_parse_model_output_missing_title_raises() -> None:
    with pytest.raises(FusionParseError):
        parse_model_output(json.dumps({"summary": "s"}))


def test_parse_model_output_not_json_raises() -> None:
    with pytest.raises(FusionParseError):
        parse_model_output("this is not json")


def test_parse_model_output_not_an_object_raises() -> None:
    with pytest.raises(FusionParseError):
        parse_model_output(json.dumps(["a", "list", "not", "an", "object"]))


def test_parse_model_output_bullets_not_a_list_raises() -> None:
    with pytest.raises(FusionParseError):
        parse_model_output(json.dumps({"title": "t", "summary": "s", "bullets": "not a list"}))


def test_parse_model_output_tolerates_missing_entities_and_language() -> None:
    draft = parse_model_output(json.dumps({"title": "t", "summary": "s"}))
    assert draft.entities == {"urls": [], "handles": [], "titles": []}
    assert draft.language is None


def test_parse_model_output_ignores_non_string_bullets() -> None:
    draft = parse_model_output(
        json.dumps({"title": "t", "summary": "s", "bullets": ["ok", 5, None, "also ok"]})
    )
    assert draft.bullets == ["ok", "also ok"]


# --------------------------------------------------------------------------- token / cost


def test_summary_tracks_token_usage_and_a_nonzero_cost_estimate(unfused_db: Path) -> None:
    client = FakeFusionClient()  # every call reports 10 prompt + 5 completion tokens
    with connect_stage(unfused_db, "fusion") as conn:
        summary = run(conn, client)
    assert summary.prompt_tokens == 10 * len(REELS)
    assert summary.completion_tokens == 5 * len(REELS)
    assert summary.estimated_cost_usd > 0
    assert "estimated" in summary.report()


def test_report_lists_failed_item_ids(unfused_db: Path) -> None:
    client = FakeFusionClient(raw_text={FAKEML001_MARKER: "broken"})
    with connect_stage(unfused_db, "fusion") as conn:
        summary = run(conn, client)
    assert "FAKEml001" in summary.report()


def test_tokens_are_counted_even_when_the_answer_cannot_be_parsed(unfused_db: Path) -> None:
    """Billing happens when the model answers, not when we like the answer.

    Counting tokens only on the success path made the run's cost estimate read low exactly
    when things were going wrong. (Found by code review.)
    """
    client = FakeFusionClient(raw_text={FAKEML001_MARKER: "not json at all {{{"})
    with connect_stage(unfused_db, "fusion") as conn:
        summary = run(conn, client)

    assert summary.items_failed, "the unparseable item should be recorded as failed"
    failed_ids = [item_id for item_id, _ in summary.items_failed]
    assert "FAKEml001" in failed_ids
    # FakeFusionClient reports 10 prompt + 5 completion tokens for every call it answers,
    # including this one -- so the totals must cover every item, not just the written ones.
    answered = summary.items_written + len(summary.items_failed)
    assert summary.prompt_tokens == 10 * answered
    assert summary.completion_tokens == 5 * answered


def test_a_client_error_records_the_item_instead_of_ending_the_run(unfused_db: Path) -> None:
    """A rate limit part-way through 1,300 items must not discard the whole run's work."""

    class _FlakyClient(FakeFusionClient):
        def complete(self, *, system: str, user: str) -> ModelResponse:
            if FAKEML001_MARKER in user:
                raise RuntimeError("429 rate limit reached")
            return super().complete(system=system, user=user)

    with connect_stage(unfused_db, "fusion") as conn:
        summary = run(conn, _FlakyClient())

    assert "FAKEml001" in [item_id for item_id, _ in summary.items_failed]
    assert any("429" in reason for _, reason in summary.items_failed)
    assert summary.items_written > 0, "every other item must still have been written"
