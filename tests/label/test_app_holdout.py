"""TestClient coverage of the holdout labelling flow: hashed writes, resume, no leakage."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reelkb.contract.db import connect_readonly
from reelkb.eval.ids import hash_id, load_salt
from reelkb.label.app import create_app
from reelkb.testing.fake_db import REELS, build


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
def client(data_dir: Path) -> TestClient:
    app = create_app(data_dir)
    return TestClient(app)


def _classifier_category(data_dir: Path, item_id: str) -> str:
    conn = connect_readonly(data_dir / "kb.db")
    row = conn.execute(
        "SELECT category_id FROM classification WHERE item_id = ?", (item_id,)
    ).fetchone()
    return str(row["category_id"])


def test_holdout_root_redirects_to_first_card(client: TestClient) -> None:
    resp = client.get("/holdout", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/holdout/1"


def test_saving_writes_a_correctly_hashed_line(
    client: TestClient, data_dir: Path, eval_dir: Path
) -> None:
    resp = client.get("/holdout/1")
    assert resp.status_code == 200
    salt = load_salt(data_dir)
    item_id = json.loads((data_dir / "holdout_sample.json").read_text())["item_ids"][0]
    expected_hid = hash_id(item_id, salt)

    save = client.post("/holdout/1", data={"category_id": "ml-courses"}, follow_redirects=False)
    assert save.status_code == 303

    rows = [json.loads(line) for line in (eval_dir / "holdout_v1.jsonl").read_text().splitlines()]
    assert rows == [{"hid": expected_hid, "category_id": "ml-courses"}]


def test_no_raw_item_id_appears_in_the_fixture_file(
    client: TestClient, data_dir: Path, eval_dir: Path
) -> None:
    for n in range(1, 6):
        client.post(f"/holdout/{n}", data={"category_id": "ml-courses"})
    text = (eval_dir / "holdout_v1.jsonl").read_text()
    for r in REELS:
        assert r.item_id not in text


def test_classifier_category_is_never_specially_marked_in_the_page(
    client: TestClient, data_dir: Path
) -> None:
    """The taxonomy button grid must render identically regardless of which category the
    classifier picked for the item being shown -- proving the suggestion isn't surfaced,
    highlighted, reordered or pre-selected anywhere on an unanswered card."""
    client.get("/holdout/1")  # trigger sample creation
    sample = json.loads((data_dir / "holdout_sample.json").read_text())["item_ids"]

    # find two sampled positions whose classifier categories differ
    positions_by_category: dict[str, int] = {}
    for i, item_id in enumerate(sample, start=1):
        cat = _classifier_category(data_dir, item_id)
        positions_by_category.setdefault(cat, i)
    assert len(positions_by_category) >= 2, "fake corpus should span multiple categories"

    grids = []
    for pos in list(positions_by_category.values())[:2]:
        html = client.get(f"/holdout/{pos}").text
        match = re.search(r'<div class="category-grid">(.*?)</form>', html, re.S)
        assert match, "category grid not found in rendered page"
        grids.append(match.group(1))

    assert grids[0] == grids[1]


def test_classification_internals_never_leak_onto_the_page(client: TestClient) -> None:
    html = client.get("/holdout/1").text
    for forbidden in ("confidence", "rationale", "runner_up"):
        assert forbidden not in html


def test_resume_lands_on_first_unanswered_card(client: TestClient) -> None:
    client.post("/holdout/1", data={"category_id": "ml-courses"})
    client.post("/holdout/2", data={"category_id": "ml-courses"})
    resp = client.get("/holdout", follow_redirects=False)
    assert resp.headers["location"] == "/holdout/3"


def test_changing_an_answer_rewrites_rather_than_duplicates(
    client: TestClient, eval_dir: Path
) -> None:
    client.post("/holdout/1", data={"category_id": "ml-courses"})
    client.post("/holdout/1", data={"category_id": "movies"})
    lines = (eval_dir / "holdout_v1.jsonl").read_text().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["category_id"] == "movies"


def test_going_back_and_your_previous_answer_is_shown(client: TestClient) -> None:
    client.post("/holdout/1", data={"category_id": "movies"})
    html = client.get("/holdout/1").text
    assert 'value="movies"' in html
    assert "your-answer" in html


def test_unknown_category_is_rejected(client: TestClient) -> None:
    resp = client.post("/holdout/1", data={"category_id": "not-a-real-category"})
    assert resp.status_code == 400


def test_out_of_range_position_is_404(client: TestClient, data_dir: Path) -> None:
    client.get("/holdout/1")  # trigger sample creation
    total = len(json.loads((data_dir / "holdout_sample.json").read_text())["item_ids"])
    assert client.get(f"/holdout/{total + 1}").status_code == 404
    assert client.get("/holdout/0").status_code == 404
