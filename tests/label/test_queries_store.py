"""eval/queries_v1.jsonl: fixed format, resume/edit without duplicating a query line."""

from __future__ import annotations

import json
from pathlib import Path

from reelkb.label.queries_store import QueryRecord, load_queries, next_qid, save_query


def test_save_then_load_roundtrips(tmp_path: Path) -> None:
    rec = QueryRecord(
        qid="q01", query="free ml course", judgements={"hid1": 2, "hid2": 0}, canary=True
    )
    save_query(tmp_path, rec)
    loaded = load_queries(tmp_path)
    assert loaded["q01"] == rec


def test_file_format_matches_the_fixed_schema(tmp_path: Path) -> None:
    save_query(
        tmp_path, QueryRecord(qid="q01", query="flow movie", judgements={"h": 1}, canary=False)
    )
    row = json.loads((tmp_path / "queries_v1.jsonl").read_text().splitlines()[0])
    assert set(row) == {"qid", "query", "judgements", "canary", "canary_hids"}
    assert row == {
        "qid": "q01",
        "query": "flow movie",
        "judgements": {"h": 1},
        "canary": False,
        "canary_hids": [],
    }


def test_editing_a_query_rewrites_not_duplicates(tmp_path: Path) -> None:
    save_query(tmp_path, QueryRecord(qid="q01", query="v1", judgements={}))
    save_query(tmp_path, QueryRecord(qid="q01", query="v1", judgements={"h1": 2}))
    lines = (tmp_path / "queries_v1.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["judgements"] == {"h1": 2}


def test_next_qid_fills_gaps_sequentially(tmp_path: Path) -> None:
    assert next_qid({}) == "q01"
    existing = load_queries(tmp_path)
    save_query(tmp_path, QueryRecord(qid="q01", query="a"))
    save_query(tmp_path, QueryRecord(qid="q02", query="b"))
    existing = load_queries(tmp_path)
    assert next_qid(existing) == "q03"


def test_canary_hids_survive_a_re_save(tmp_path: Path) -> None:
    """The named-canary reel must not evaporate when the query is edited again.

    AC-5.2 is about one specific reel. If this field is dropped on rewrite, the eval falls
    back to the query-level boolean, which the M8 checker proved can pass while that very
    reel is missing from the results.
    """
    record = QueryRecord(qid="q01", query="animated cat movie", canary=True, canary_hids=["abc123"])
    save_query(tmp_path, record)

    reloaded = load_queries(tmp_path)["q01"]
    assert reloaded.canary_hids == ["abc123"]

    reloaded.judgements = {"abc123": 2}
    save_query(tmp_path, reloaded)
    assert load_queries(tmp_path)["q01"].canary_hids == ["abc123"]
