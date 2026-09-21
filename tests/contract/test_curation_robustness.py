"""A damaged curation log must not take the product down (M7 checker, finding 5).

``curation.jsonl`` and ``corrections.jsonl`` hold the owner's own edits, appended with a
plain non-atomic write. A disk-full, an interrupted append or a hand-edit can leave one torn
line -- and before this, that single line raised out of ``load_curation``, which every route
calls, so the landing page, search, every category page, every item page and ``/eval`` all
returned HTTP 500 at once.

The rule these tests fix in place: skip what cannot be read, report it, keep every event that
is still intact, and never rewrite the file.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from reelkb.contract.curation import hide, load_curation
from reelkb.serve.app import create_app


def _write(path: Path, lines: list[str]) -> None:
    path.write_text("".join(line + "\n" for line in lines))


def test_a_torn_last_line_is_skipped_and_the_rest_survives(tmp_path: Path) -> None:
    """The realistic failure: the process died halfway through appending."""
    _write(
        tmp_path / "curation.jsonl",
        [
            json.dumps({"action": "hide", "item_id": "A"}),
            json.dumps({"action": "edit", "item_id": "B", "field": "title", "value": "Mine"}),
            '{"action": "hide", "item_i',  # torn mid-write
        ],
    )
    cur = load_curation(tmp_path)
    assert cur.hidden == {"A"}
    assert cur.edits == {"B": {"title": "Mine"}}
    assert len(cur.problems) == 1
    assert "curation.jsonl:3" in cur.problems[0]


def test_a_problem_names_the_real_file_line(tmp_path: Path) -> None:
    """Line numbers must match what the owner sees in an editor.

    They were previously counted over the *parsed* events, so a bad event on line 3 was
    reported as "event 2" -- and the two numbering schemes were mixed in one list.
    (Found by code review.)"""
    _write(
        tmp_path / "curation.jsonl",
        [
            json.dumps({"action": "hide", "item_id": "A"}),
            "not json",
            json.dumps({"action": "hide"}),  # bad event on file line 3
        ],
    )
    cur = load_curation(tmp_path)
    assert any("curation.jsonl:2" in p for p in cur.problems)
    assert any("curation.jsonl:3" in p for p in cur.problems)


def test_events_missing_required_keys_are_skipped_not_raised(tmp_path: Path) -> None:
    _write(
        tmp_path / "curation.jsonl",
        [
            json.dumps({"action": "hide"}),  # no item_id
            json.dumps({"item_id": "B"}),  # no action
            json.dumps({"action": "edit", "item_id": "C"}),  # no field/value
            json.dumps({"action": "hide", "item_id": "D"}),  # the good one
        ],
    )
    cur = load_curation(tmp_path)
    assert cur.hidden == {"D"}
    assert len(cur.problems) == 3


def test_a_damaged_corrections_file_is_survived_too(tmp_path: Path) -> None:
    _write(
        tmp_path / "corrections.jsonl",
        [
            json.dumps({"item_id": "A", "category_id": "books"}),
            "not json at all",
            json.dumps({"item_id": "B"}),  # no category_id
        ],
    )
    cur = load_curation(tmp_path)
    assert cur.categories == {"A": "books"}
    assert len(cur.problems) == 2


def test_the_damaged_file_is_never_rewritten(tmp_path: Path) -> None:
    """Append-only means append-only: repairing the owner's log is not this layer's business."""
    path = tmp_path / "curation.jsonl"
    original = json.dumps({"action": "hide", "item_id": "A"}) + "\n{broken"
    path.write_text(original)
    load_curation(tmp_path)
    assert path.read_text() == original


def test_appending_still_works_after_a_damaged_line(tmp_path: Path) -> None:
    """New edits must keep landing, so a torn line never blocks further curation."""
    path = tmp_path / "curation.jsonl"
    path.write_text('{"action": "hide", "item_i')
    hide(tmp_path, "B")
    cur = load_curation(tmp_path)
    assert cur.hidden == {"B"}
    assert cur.problems


def test_the_whole_app_still_serves_with_a_damaged_curation_log(tmp_path: Path) -> None:
    """Every route returned 500 before this. The knowledge base must stay readable."""
    from reelkb.testing.fake_db import build

    build(tmp_path)
    (tmp_path / "curation.jsonl").write_text(
        json.dumps({"action": "hide", "item_id": "FAKEml001"}) + "\n" + '{"action": "hid'
    )
    client = TestClient(create_app(tmp_path))
    for path in ("/", "/search?q=course", "/hidden", "/item/FAKEml002"):
        assert client.get(path).status_code == 200, path
    # ...and the intact event before the damaged line is still in force.
    assert client.get("/item/FAKEml001").status_code == 200
