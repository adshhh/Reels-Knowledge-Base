"""eval/holdout_v1.jsonl: correct hashed lines, atomic rewrite, no duplicates on edit."""

from __future__ import annotations

import json
from pathlib import Path

from reelkb.label import holdout_store


def test_save_then_load_roundtrips(tmp_path: Path) -> None:
    holdout_store.save_answer(tmp_path, "hid1", "ml-courses")
    holdout_store.save_answer(tmp_path, "hid2", "movies")
    assert holdout_store.load_answers(tmp_path) == {"hid1": "ml-courses", "hid2": "movies"}


def test_changing_an_answer_rewrites_no_duplicate_lines(tmp_path: Path) -> None:
    holdout_store.save_answer(tmp_path, "hid1", "ml-courses")
    holdout_store.save_answer(tmp_path, "hid1", "movies")  # the owner changed their mind
    lines = (tmp_path / holdout_store.FILENAME).read_text().splitlines()
    matching = [json.loads(line) for line in lines if json.loads(line)["hid"] == "hid1"]
    assert len(matching) == 1
    assert matching[0]["category_id"] == "movies"


def test_file_format_is_hid_and_category_id_only(tmp_path: Path) -> None:
    holdout_store.save_answer(tmp_path, "hid1", "ml-courses")
    line = (tmp_path / holdout_store.FILENAME).read_text().splitlines()[0]
    row = json.loads(line)
    assert set(row) == {"hid", "category_id"}


def test_no_file_means_no_answers(tmp_path: Path) -> None:
    assert holdout_store.load_answers(tmp_path) == {}


def test_write_is_atomic_no_leftover_tmp_file(tmp_path: Path) -> None:
    holdout_store.save_answer(tmp_path, "hid1", "ml-courses")
    assert not (tmp_path / (holdout_store.FILENAME + ".tmp")).exists()
    assert (tmp_path / holdout_store.FILENAME).exists()
