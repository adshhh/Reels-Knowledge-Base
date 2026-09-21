"""``python -m reelkb.eval`` (AC-7.1): the CLI end to end, on the fake corpus.

Two things AC-7.1 explicitly asks to be proven, both here:

- the eval passes when everything lines up (a fully synthetic, fake-encoder corpus standing
  in for the real fixtures), and
- it exits non-zero, with the failure visible in the printed output, when the classifier is
  deliberately degraded.

Every other early-exit path (missing fixtures, missing database, missing local lookup,
missing embeddings) gets its own small test, because each one is a distinct way a fresh
checkout or a half-finished pipeline run should fail loudly rather than crash or lie.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from reelkb.contract.db import connect_stage
from reelkb.eval.__main__ import main
from reelkb.eval.ids import update_lookup
from reelkb.search.embed import run_embed
from reelkb.search.encoder import FakeEncoder
from reelkb.testing.fake_db import REELS, build

# (qid, query text, the item it must find, whether it's the AC-5.2 canary). Ranks verified
# by hand against the fake corpus + FakeEncoder: each query's target is the rank-1 hit with a
# wide score gap over the runner-up (see the eval harness build notes).
QUERY_SPECS = [
    ("q-flow", "flow", "FAKEmv001", True),  # the Flow-style canary: caption never says "flow"
    ("q-food", "paneer bhurji recipe", "FAKEfd001", False),
    ("q-career", "resume mistakes recruiter", "FAKEcr001", False),
    ("q-drink", "cold brew coffee", "FAKEfd003", False),
]


def _write_jsonl(path: Path, rows: list[Mapping[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(dict(row)) for row in rows) + "\n")


def _build_environment(tmp_path: Path, *, embed: bool = True) -> tuple[Path, Path]:
    """A full synthetic AC-7.1 environment: fake db, (optionally) embedded, plus matching
    holdout and query fixtures whose hids resolve via the local lookup, exactly like a real
    machine after the labelling page has run (§7)."""
    data_dir = tmp_path / "data"
    eval_dir = tmp_path / "eval"
    data_dir.mkdir()
    eval_dir.mkdir()
    build(data_dir)
    if embed:
        run_embed(data_dir, encoder=FakeEncoder(dim=64))

    holdout_rows: list[Mapping[str, object]] = [
        {"hid": update_lookup(data_dir, r.item_id), "category_id": r.category} for r in REELS
    ]
    _write_jsonl(eval_dir / "holdout_v1.jsonl", holdout_rows)

    query_rows: list[Mapping[str, object]] = [
        {
            "qid": qid,
            "query": query_text,
            "judgements": {update_lookup(data_dir, target_item): 2},
            "canary": canary,
        }
        for qid, query_text, target_item, canary in QUERY_SPECS
    ]
    _write_jsonl(eval_dir / "queries_v1.jsonl", query_rows)

    return data_dir, eval_dir


def test_main_passes_end_to_end_on_synthetic_fixtures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, eval_dir = _build_environment(tmp_path)

    code = main(
        ["--data-dir", str(data_dir), "--eval-dir", str(eval_dir), "--allow-partial-holdout"],
        encoder=FakeEncoder(dim=64),
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "[FAIL]" not in out
    assert "=== AC-CAT (§4, AC-4.1) ===" in out
    # The header now names the retrieval config, so a printed number can be reproduced.
    assert "=== AC-SEARCH (§5, AC-5.1 / AC-5.2) [weighted_sum, alpha=0.5, rrf_k=60] ===" in out
    assert "[PASS] no query returned Recall@10 = 0" in out
    assert "[PASS] canary queries all found in top 10 (AC-5.2): q-flow" in out


def test_main_exits_nonzero_when_classifier_is_degraded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-7.1's other half: deliberately break the classifier and show the eval catches it."""
    data_dir, eval_dir = _build_environment(tmp_path)

    conn = connect_stage(data_dir / "kb.db", "classify")
    conn.execute("UPDATE classification SET category_id = 'other' WHERE category_id != 'other'")
    conn.commit()
    conn.close()

    code = main(
        ["--data-dir", str(data_dir), "--eval-dir", str(eval_dir), "--allow-partial-holdout"],
        encoder=FakeEncoder(dim=64),
    )
    out = capsys.readouterr().out

    assert code == 1
    assert "[FAIL] AC-4.1 top-1 category accuracy" in out
    assert "[FAIL] AC-4.1 'other' share of corpus" in out


def test_main_missing_holdout_file_prints_message_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    eval_dir = tmp_path / "eval"  # left empty: no fixture files at all

    code = main(
        ["--data-dir", str(data_dir), "--eval-dir", str(eval_dir), "--allow-partial-holdout"]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert "cannot run eval" in out
    assert "holdout_v1.jsonl" in out


def test_main_missing_queries_file_prints_message_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    _write_jsonl(eval_dir / "holdout_v1.jsonl", [{"hid": "a" * 16, "category_id": "movies"}])

    code = main(
        ["--data-dir", str(data_dir), "--eval-dir", str(eval_dir), "--allow-partial-holdout"]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert "cannot run eval" in out
    assert "queries_v1.jsonl" in out


def test_main_missing_database_prints_message_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"  # never built -- no kb.db
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    _write_jsonl(eval_dir / "holdout_v1.jsonl", [{"hid": "a" * 16, "category_id": "movies"}])
    _write_jsonl(eval_dir / "queries_v1.jsonl", [{"qid": "q1", "query": "x", "judgements": {}}])

    code = main(
        ["--data-dir", str(data_dir), "--eval-dir", str(eval_dir), "--allow-partial-holdout"]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert "no database at" in out
    assert "run the pipeline first" in out


def test_main_missing_lookup_prints_message_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"
    eval_dir = tmp_path / "eval"
    data_dir.mkdir()
    eval_dir.mkdir()
    build(data_dir)  # real kb.db, but no eval_lookup.json written yet
    _write_jsonl(eval_dir / "holdout_v1.jsonl", [{"hid": "a" * 16, "category_id": "movies"}])
    _write_jsonl(eval_dir / "queries_v1.jsonl", [{"qid": "q1", "query": "x", "judgements": {}}])

    code = main(
        ["--data-dir", str(data_dir), "--eval-dir", str(eval_dir), "--allow-partial-holdout"]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert "cannot run eval" in out
    assert "eval_lookup.json" in out


def test_main_missing_embeddings_prints_message_and_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir, eval_dir = _build_environment(tmp_path, embed=False)  # classifier fixtures resolve

    code = main(
        ["--data-dir", str(data_dir), "--eval-dir", str(eval_dir), "--allow-partial-holdout"],
        encoder=FakeEncoder(dim=64),
    )
    out = capsys.readouterr().out

    assert code == 2
    assert "cannot run search eval" in out
    assert "reelkb.search.embed" in out


def test_a_partial_holdout_is_refused_unless_it_is_asked_for(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC-4.1 is defined over 150 items. Without the flag, a 27-item holdout must not print
    a green AC-CAT -- the M7 checker showed three labelled items passing all four thresholds,
    and a smaller holdout emits FEWER per-category checks, so it is easier to pass."""
    data_dir, eval_dir = _build_environment(tmp_path)

    code = main(["--data-dir", str(data_dir), "--eval-dir", str(eval_dir)])
    out = capsys.readouterr().out

    assert code == 2
    assert "150" in out
    assert "PASS" not in out, "a refused fixture must not print thresholds at all"
