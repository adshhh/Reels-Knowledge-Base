"""AC-7.2: holdout items are quarantined -- never used as prompt examples (§7).

Two things are proven, deliberately kept separate:

1. The checking machinery itself catches a leak, and clears a clean tree, on synthetic data.
   These tests always run -- they can't be skipped away by an empty environment -- so a
   regression in the checker is caught regardless of whether real fixtures exist anywhere.
2. The real check: this repo's actual holdout fixture (if it exists on this machine) against
   this repo's actual prompt files. Skipped, not failed, when the fixture or the local lookup
   table is absent -- both are local-only, un-committed data (§7), so a fresh checkout or CI
   legitimately has neither, and "no data to check" must never look like "check passed" or
   "check failed".
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reelkb.eval.fixtures import load_holdout
from reelkb.eval.ids import load_lookup
from reelkb.eval.quarantine import find_leaks, find_prompt_files

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SOURCE_ROOT = REPO_ROOT / "src" / "reelkb"
REAL_DATA_DIR = REPO_ROOT / "data"
REAL_EVAL_DIR = REPO_ROOT / "eval"


# --------------------------------------------------------------------------------------
# 1. The checking machinery, proven on synthetic data, unconditionally.


def test_find_prompt_files_finds_files_nested_under_any_prompts_directory(tmp_path: Path) -> None:
    (tmp_path / "fusion" / "prompts" / "examples").mkdir(parents=True)
    (tmp_path / "fusion" / "prompts" / "system.txt").write_text("be careful")
    (tmp_path / "fusion" / "prompts" / "examples" / "few_shot.txt").write_text("example one")
    (tmp_path / "fusion" / "not_prompts.txt").write_text("irrelevant")

    files = find_prompt_files(tmp_path)

    assert {p.name for p in files} == {"system.txt", "few_shot.txt"}


def test_find_prompt_files_on_missing_root_returns_empty(tmp_path: Path) -> None:
    assert find_prompt_files(tmp_path / "does-not-exist") == []


def test_checker_catches_a_synthetic_leak(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "classify" / "prompts"
    prompts_dir.mkdir(parents=True)
    leaky_file = prompts_dir / "few_shot.txt"
    leaky_file.write_text("Example: FAKEholdout999 was labelled 'movies' by the owner.")

    leaks = find_leaks(["FAKEholdout999"], find_prompt_files(tmp_path))

    assert len(leaks) == 1
    assert leaks[0].item_id == "FAKEholdout999"
    assert leaks[0].path == leaky_file


def test_checker_passes_clean_on_synthetic_data(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "classify" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "system.txt").write_text("You are a careful, conservative classifier.")

    leaks = find_leaks(["FAKEholdout999"], find_prompt_files(tmp_path))

    assert leaks == []


def test_checker_ignores_a_matching_file_outside_any_prompts_directory(tmp_path: Path) -> None:
    (tmp_path / "classify").mkdir()
    (tmp_path / "classify" / "notes.txt").write_text("mentions FAKEholdout999 in passing")

    leaks = find_leaks(["FAKEholdout999"], find_prompt_files(tmp_path))

    assert leaks == []


def test_checker_skips_empty_item_ids(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "classify" / "prompts"
    prompts_dir.mkdir(parents=True)
    (prompts_dir / "system.txt").write_text("anything at all")

    leaks = find_leaks(["", "FAKEholdout999"], find_prompt_files(tmp_path))

    assert leaks == []


# --------------------------------------------------------------------------------------
# 2. The real check, against this repo's actual fixture and prompt files.


def test_no_real_holdout_item_id_appears_in_any_real_prompt_file() -> None:
    """AC-7.2 proper. Skips cleanly (CI, a fresh checkout) when the local-only fixture or
    lookup table doesn't exist -- neither is ever committed (§7, `.gitignore`)."""
    holdout_path = REAL_EVAL_DIR / "holdout_v1.jsonl"
    if not holdout_path.exists():
        pytest.skip(f"no {holdout_path} on this machine -- nothing to quarantine-check yet")
    lookup = load_lookup(REAL_DATA_DIR)
    if not lookup:
        pytest.skip(f"no {REAL_DATA_DIR / 'eval_lookup.json'} -- can't resolve hids to item_ids")

    holdout = load_holdout(holdout_path)
    item_ids = [lookup[item.hid] for item in holdout if item.hid in lookup]
    leaks = find_leaks(item_ids, find_prompt_files(REAL_SOURCE_ROOT))

    assert leaks == [], "holdout item_id(s) leaked into prompt file(s): " + ", ".join(
        f"{leak.item_id} in {leak.path}" for leak in leaks
    )
