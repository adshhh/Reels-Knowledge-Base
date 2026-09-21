"""Guards around the owner's irreplaceable labelling work (§7).

The fixture files are the scope contract, and they cost roughly five hours of the owner's
time to produce. Every hid in them is ``hmac(eval_salt, item_id)``, so the 32 opaque bytes in
``data/eval_salt`` are load-bearing for all of it. These tests cover the ways the M7 checker
showed that work could evaporate without a single error message.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reelkb.eval.fixtures import FixtureError, HoldoutItem
from reelkb.eval.ids import SaltLostError, hash_id, load_salt
from reelkb.eval.runner import check_holdout_shape


def test_a_fresh_start_mints_a_salt(tmp_path: Path) -> None:
    salt = load_salt(tmp_path / "data")
    assert len(salt) == 32
    assert load_salt(tmp_path / "data") == salt, "a second call must reuse the same salt"


def test_an_empty_query_shell_does_not_block_a_fresh_start(tmp_path: Path) -> None:
    """The page writes a query row the moment one is typed, before anything is graded."""
    data_dir, eval_dir = tmp_path / "data", tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "queries_v1.jsonl").write_text(
        json.dumps({"qid": "q01", "query": "ml courses", "judgements": {}}) + "\n"
    )
    assert len(load_salt(data_dir, eval_dir)) == 32


def test_losing_the_salt_after_labelling_refuses_loudly_instead_of_starting_over(
    tmp_path: Path,
) -> None:
    """The failure that costs hours: a new salt orphans every hid already written.

    The M7 checker walked it through: 27 labelled rows, salt deleted, the page resumes at
    item 1 as though nothing had been done, and re-labelling appends 27 more rows that the
    eval harness then counts twice. No error at any point.
    """
    data_dir, eval_dir = tmp_path / "data", tmp_path / "eval"
    salt = load_salt(data_dir, eval_dir)
    eval_dir.mkdir(exist_ok=True)
    (eval_dir / "holdout_v1.jsonl").write_text(
        json.dumps({"hid": hash_id("FAKEml001", salt), "category_id": "ml-courses"}) + "\n"
    )

    (data_dir / "eval_salt").unlink()
    with pytest.raises(SaltLostError, match="unresolvable"):
        load_salt(data_dir, eval_dir)


def test_the_refusal_names_the_file_and_says_how_to_recover(tmp_path: Path) -> None:
    data_dir, eval_dir = tmp_path / "data", tmp_path / "eval"
    salt = load_salt(data_dir, eval_dir)
    eval_dir.mkdir(exist_ok=True)
    (eval_dir / "queries_v1.jsonl").write_text(
        json.dumps({"qid": "q1", "query": "x", "judgements": {hash_id("a", salt): 2}}) + "\n"
    )
    (data_dir / "eval_salt").unlink()

    with pytest.raises(SaltLostError) as exc:
        load_salt(data_dir, eval_dir)
    message = str(exc.value)
    assert "eval_salt" in message
    assert "queries_v1.jsonl" in message
    assert "backup" in message, "an error that does not say what to do is half an error"


def test_a_torn_last_line_does_not_count_as_labelled_work(tmp_path: Path) -> None:
    """A half-written line proves nothing either way; the fixture loader reports it instead."""
    data_dir, eval_dir = tmp_path / "data", tmp_path / "eval"
    eval_dir.mkdir()
    (eval_dir / "holdout_v1.jsonl").write_text('{"hid": "abc", "categ')
    load_salt(data_dir, eval_dir)  # must not raise


# --- holdout fixture shape ---------------------------------------------------------------


def _holdout(pairs: list[tuple[str, str]]) -> list[HoldoutItem]:
    return [HoldoutItem(hid=h, category_id=c) for h, c in pairs]


def test_the_same_reel_twice_under_two_hids_is_refused(tmp_path: Path) -> None:
    """Salt rotation produced exactly this: 54 rows for 27 reels, every metric double-counting.

    The checker's measurement: a duplicated holdout dropped top-1 accuracy from 1.00 to 0.56
    and per-category recall to 0.20, with no warning -- so the owner would spend a day tuning
    a classifier that was in fact perfect.
    """
    holdout = _holdout([("hid-1", "food"), ("hid-2", "food")])
    lookup = {"hid-1": "item-a", "hid-2": "item-a"}  # same reel, two hids
    with pytest.raises(FixtureError, match="same item"):
        check_holdout_shape(holdout, lookup, enforce_size=False)


def test_a_repeated_hid_is_refused(tmp_path: Path) -> None:
    holdout = _holdout([("hid-1", "food"), ("hid-1", "ml-courses")])
    with pytest.raises(FixtureError, match="duplicate hid"):
        check_holdout_shape(holdout, {"hid-1": "item-a"}, enforce_size=False)


def test_a_holdout_that_is_nowhere_near_150_items_is_refused(tmp_path: Path) -> None:
    """AC-4.1 is a statement ABOUT a 150-item floored sample, so /eval printed PASS on three.

    Worse than merely lenient: with too few items per category the per-category recall
    thresholds silently stop being emitted at all, so a degenerate fixture makes AC-CAT
    *easier* to pass than a real one.
    """
    holdout = _holdout([(f"hid-{i}", "food") for i in range(3)])
    lookup = {f"hid-{i}": f"item-{i}" for i in range(3)}
    with pytest.raises(FixtureError, match="150"):
        check_holdout_shape(holdout, lookup)


def test_a_full_size_holdout_passes(tmp_path: Path) -> None:
    holdout = _holdout([(f"hid-{i}", f"cat-{i % 10}") for i in range(150)])
    lookup = {f"hid-{i}": f"item-{i}" for i in range(150)}
    check_holdout_shape(holdout, lookup)  # must not raise
