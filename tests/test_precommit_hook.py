"""The pre-commit guard refuses personal data (Verification step 3).

A fake ``git`` on PATH plays the part of the repository, so this runs the real hook script
without touching any real repository. The end-to-end check (a real commit being refused) is
run by the owner, because the agent never runs git.

.githooks/ is gitignored by the owner's choice, so on CI (a fresh clone) this is skipped.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".githooks" / "pre-commit"

pytestmark = pytest.mark.skipif(not HOOK.exists(), reason=".githooks/ is local-only")


def run_hook(tmp_path: Path, staged: list[str], gitignore: str = "data/\n.env\n") -> int:
    fake = tmp_path / "bin" / "git"
    fake.parent.mkdir()
    (tmp_path / "staged.txt").write_text("\n".join(staged) + "\n")
    (tmp_path / "gitignore.txt").write_text(gitignore)
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'if [ "$1" = diff ]; then cat "{tmp_path}/staged.txt"; exit 0; fi\n'
        f'if [ "$1" = show ]; then cat "{tmp_path}/gitignore.txt"; exit 0; fi\n'
        "exit 1\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ, "PATH": f"{fake.parent}:{os.environ['PATH']}"}
    return subprocess.run([str(HOOK)], env=env, capture_output=True).returncode


@pytest.mark.parametrize(
    "path",
    [
        "data/raw/message_1.json",
        "data/media/abc.mp4",
        "records/x.jsonl",
        "corrections.jsonl",
        "curation.jsonl",
        ".env",
        # .envrc holds the live API keys in plaintext and used to sail past this hook,
        # because it matches neither `.*\.env$` nor `.*\.env\..*` (found by the M1 checker).
        ".envrc",
        "secrets/key.pem",
    ],
)
def test_personal_data_or_secrets_are_blocked(tmp_path: Path, path: str) -> None:
    assert run_hook(tmp_path, ["README.md", path]) == 1


def test_ordinary_code_is_allowed(tmp_path: Path) -> None:
    assert run_hook(tmp_path, ["src/reelkb/contract/db.py", "docs/PLAN.md"]) == 0


FULL_GITIGNORE = "data/\nrecords/\n.env\n.envrc\n"


def test_removing_data_from_gitignore_is_blocked(tmp_path: Path) -> None:
    assert run_hook(tmp_path, [".gitignore"], gitignore=".env\n") == 1


@pytest.mark.parametrize("dropped", ["data/", "records/", ".env", ".envrc"])
def test_dropping_any_required_gitignore_line_is_blocked(tmp_path: Path, dropped: str) -> None:
    remaining = "".join(f"{line}\n" for line in FULL_GITIGNORE.split() if line != dropped)
    assert run_hook(tmp_path, [".gitignore"], gitignore=remaining) == 1


def test_a_complete_gitignore_is_allowed(tmp_path: Path) -> None:
    assert run_hook(tmp_path, [".gitignore"], gitignore=FULL_GITIGNORE) == 0


def test_a_substring_match_does_not_satisfy_the_dotenv_requirement(tmp_path: Path) -> None:
    """'.envrc' contains '.env', so a substring check thought '.env' was still ignored.

    Found by the M1 checker: with `grep -F`, deleting the real `.env` line went unnoticed as
    long as `.envrc` remained. The hook now matches whole lines.
    """
    assert run_hook(tmp_path, [".gitignore"], gitignore="data/\nrecords/\n.envrc\n") == 1
