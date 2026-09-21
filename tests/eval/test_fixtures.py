"""Fixture loading: happy path, and every way a fixture file can be wrong."""

from __future__ import annotations

from pathlib import Path

import pytest

from reelkb.eval.fixtures import FixtureError, load_holdout, load_queries


def test_load_holdout_happy_path(tmp_path: Path) -> None:
    path = tmp_path / "holdout_v1.jsonl"
    path.write_text(
        '{"hid": "abc123", "category_id": "movies"}\n{"hid": "def456", "category_id": "books"}\n'
    )
    items = load_holdout(path)
    assert [(i.hid, i.category_id) for i in items] == [
        ("abc123", "movies"),
        ("def456", "books"),
    ]


def test_load_holdout_missing_file_raises_clear_error(tmp_path: Path) -> None:
    with pytest.raises(FixtureError, match="missing fixture file"):
        load_holdout(tmp_path / "nope.jsonl")


def test_load_holdout_blank_lines_ignored(tmp_path: Path) -> None:
    path = tmp_path / "holdout_v1.jsonl"
    path.write_text('{"hid": "abc123", "category_id": "movies"}\n\n\n')
    assert len(load_holdout(path)) == 1


def test_load_holdout_bad_json_raises(tmp_path: Path) -> None:
    path = tmp_path / "holdout_v1.jsonl"
    path.write_text("{not json}\n")
    with pytest.raises(FixtureError, match="invalid JSON"):
        load_holdout(path)


def test_load_holdout_missing_field_raises(tmp_path: Path) -> None:
    path = tmp_path / "holdout_v1.jsonl"
    path.write_text('{"hid": "abc123"}\n')
    with pytest.raises(FixtureError, match="missing field"):
        load_holdout(path)


def test_load_holdout_empty_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "holdout_v1.jsonl"
    path.write_text("")
    with pytest.raises(FixtureError, match="no rows"):
        load_holdout(path)


def test_load_queries_happy_path(tmp_path: Path) -> None:
    path = tmp_path / "queries_v1.jsonl"
    path.write_text(
        '{"qid": "q01", "query": "flow movie", "judgements": {"abc123": 2}, "canary": true}\n'
    )
    queries = load_queries(path)
    assert len(queries) == 1
    q = queries[0]
    assert q.qid == "q01"
    assert q.query == "flow movie"
    assert q.judgements == {"abc123": 2}
    assert q.canary is True


def test_load_queries_canary_defaults_to_false(tmp_path: Path) -> None:
    path = tmp_path / "queries_v1.jsonl"
    path.write_text('{"qid": "q01", "query": "x", "judgements": {}}\n')
    assert load_queries(path)[0].canary is False


def test_load_queries_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FixtureError, match="missing fixture file"):
        load_queries(tmp_path / "nope.jsonl")
