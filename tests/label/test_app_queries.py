"""TestClient coverage of query judging: pooling/dedup across searchers, fixed format, resume."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reelkb.contract.cards import Card, load_cards
from reelkb.contract.curation import Curation, load_curation
from reelkb.contract.db import connect_readonly
from reelkb.contract.search_api import SearchFilters, SearchHit
from reelkb.label.app import create_app
from reelkb.testing.fake_db import REELS, build


class _FixedSearcher:
    """A Searcher stub that always returns the same hits, ignoring the query text."""

    def __init__(self, item_ids: list[str]) -> None:
        self._item_ids = item_ids

    def search(
        self, query: str, curation: Curation, filters: SearchFilters | None = None, k: int = 20
    ) -> list[SearchHit]:
        return [SearchHit(i, 1.0) for i in self._item_ids[:k]]


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    d = tmp_path / "data"
    d.mkdir()
    build(d)
    return d


@pytest.fixture
def eval_dir(tmp_path: Path) -> Path:
    return tmp_path / "eval"


@pytest.fixture
def cards(data_dir: Path) -> list[Card]:
    conn = connect_readonly(data_dir / "kb.db")
    return load_cards(conn, load_curation(data_dir))


def test_create_query_and_get_judge_page(data_dir: Path) -> None:
    dense = _FixedSearcher(["FAKEml001", "FAKEml002"])
    sparse = _FixedSearcher(["FAKEml002", "FAKEml003"])  # FAKEml002 overlaps
    app = create_app(data_dir, searchers={"dense": dense, "sparse": sparse})
    client = TestClient(app)

    resp = client.post("/queries", data={"query": "free ml course"}, follow_redirects=False)
    assert resp.status_code == 303
    qid = resp.headers["location"].rsplit("/", 1)[-1]

    judge = client.get(f"/queries/{qid}")
    assert judge.status_code == 200
    # pooled + deduped: three distinct items across both searchers
    assert judge.text.count("candidate-header") == 3


def test_saving_judgements_writes_the_fixed_format(data_dir: Path, eval_dir: Path) -> None:
    dense = _FixedSearcher(["FAKEml001"])
    app = create_app(data_dir, searchers={"dense": dense})
    client = TestClient(app)

    client.post("/queries", data={"query": "free ml course"})
    judge_html = client.get("/queries/q01").text
    match = re.search(r'judgement_([0-9a-f]{16})"', judge_html)
    assert match is not None
    hid = match.group(1)

    save = client.post(
        "/queries/q01",
        data={f"judgement_{hid}": "2", "canary": "on"},
        follow_redirects=False,
    )
    assert save.status_code == 303

    row = json.loads((eval_dir / "queries_v1.jsonl").read_text().splitlines()[0])
    assert set(row) == {"qid", "query", "judgements", "canary", "canary_hids"}
    assert row["judgements"] == {hid: 2}
    assert row["canary"] is True


def test_no_raw_item_id_appears_in_the_fixture_file(data_dir: Path, eval_dir: Path) -> None:
    dense = _FixedSearcher(["FAKEml001", "FAKEmv001"])
    app = create_app(data_dir, searchers={"dense": dense})
    client = TestClient(app)
    client.post("/queries", data={"query": "anything"})
    html = client.get("/queries/q01").text
    hids = re.findall(r'judgement_([0-9a-f]{16})"', html)
    data = {f"judgement_{h}": "1" for h in hids}
    client.post("/queries/q01", data=data)

    text = (eval_dir / "queries_v1.jsonl").read_text()
    for r in REELS:
        assert r.item_id not in text


def test_resume_shows_previous_judgements_preselected(data_dir: Path, eval_dir: Path) -> None:
    dense = _FixedSearcher(["FAKEml001"])
    app = create_app(data_dir, searchers={"dense": dense})
    client = TestClient(app)
    client.post("/queries", data={"query": "q"})
    html = client.get("/queries/q01").text
    hid = re.search(r'judgement_([0-9a-f]{16})"', html).group(1)  # type: ignore[union-attr]
    client.post("/queries/q01", data={f"judgement_{hid}": "0"})

    reopened = client.get("/queries/q01").text
    assert re.search(rf'name="judgement_{hid}" value="0" checked', reopened)


def test_editing_a_query_rewrites_not_duplicates(data_dir: Path, eval_dir: Path) -> None:
    dense = _FixedSearcher(["FAKEml001"])
    app = create_app(data_dir, searchers={"dense": dense})
    client = TestClient(app)
    client.post("/queries", data={"query": "q"})
    html = client.get("/queries/q01").text
    hid = re.search(r'judgement_([0-9a-f]{16})"', html).group(1)  # type: ignore[union-attr]
    client.post("/queries/q01", data={f"judgement_{hid}": "0"})
    client.post("/queries/q01", data={f"judgement_{hid}": "2"})

    lines = (eval_dir / "queries_v1.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["judgements"][hid] == 2


def test_default_searcher_is_substring_when_none_given(data_dir: Path) -> None:
    app = create_app(data_dir)  # no searchers kwarg
    client = TestClient(app)
    client.post("/queries", data={"query": "fast.ai"})  # matches FAKEml001's OCR text
    html = client.get("/queries/q01").text
    assert "candidate-header" in html


def _graded_query(data_dir: Path) -> tuple[TestClient, str, str]:
    """Create a query, grade its first candidate 2, and return (client, qid, that hid)."""
    app = create_app(data_dir, searchers={"dense": _FixedSearcher(["FAKEml001", "FAKEml002"])})
    client = TestClient(app)
    resp = client.post("/queries", data={"query": "free ml course"}, follow_redirects=False)
    qid = resp.headers["location"].rsplit("/", 1)[-1]
    hids = re.findall(r'name="judgement_([0-9a-f]+)"', client.get(f"/queries/{qid}").text)
    assert hids, "the judging page should offer candidates to grade"
    client.post(f"/queries/{qid}", data={f"judgement_{hids[0]}": "2"}, follow_redirects=False)
    return client, qid, hids[0]


def _saved_judgements(eval_dir: Path, qid: str) -> dict[str, int]:
    rows = [json.loads(line) for line in (eval_dir / "queries_v1.jsonl").read_text().splitlines()]
    return next(r["judgements"] for r in rows if r["qid"] == qid)


def test_an_empty_submit_does_not_wipe_existing_judgements(data_dir: Path, eval_dir: Path) -> None:
    """A submit carries only what was on screen; everything else must survive.

    The M7 checker showed a full grading pass erased by one submit that omitted the radios --
    and the owner would have no way to see that hours of judging had gone.
    """
    client, qid, hid = _graded_query(data_dir)
    assert _saved_judgements(eval_dir, qid) == {hid: 2}

    client.post(f"/queries/{qid}", data={}, follow_redirects=False)  # nothing on the form
    assert _saved_judgements(eval_dir, qid) == {hid: 2}


def test_re_grading_the_same_candidate_still_overwrites(data_dir: Path, eval_dir: Path) -> None:
    """Merging must not make a grade permanent -- changing your mind is the point."""
    client, qid, hid = _graded_query(data_dir)
    client.post(f"/queries/{qid}", data={f"judgement_{hid}": "0"}, follow_redirects=False)
    assert _saved_judgements(eval_dir, qid) == {hid: 0}
