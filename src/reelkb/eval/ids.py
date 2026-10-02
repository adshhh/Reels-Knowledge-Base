"""Hashed document IDs shared between the labelling page and the eval harness (§7). The
fixture files are committed to a public repo, so real item ids never appear in them --
instead every item is a ``hid``: ``hmac_sha256(salt, item_id).hexdigest()[:16]``. The salt
(``data/eval_salt``) and the ``hid -> item_id`` lookup (``data/eval_lookup.json``) are both
local-only, never committed. One module, imported by both the labelling page and this
harness, so the id scheme is defined in exactly one place.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path

SALT_FILE = "eval_salt"
LOOKUP_FILE = "eval_lookup.json"
HID_LENGTH = 16


class SaltLostError(RuntimeError):
    """The salt is gone but labelled fixtures exist, so every hid in them is unresolvable."""


def _fixtures_with_content(eval_dir: Path) -> list[Path]:
    """Fixture files that contain at least one hashed id.

    Not merely "the file exists": the labelling page writes a query row the moment a query is
    typed, before anything has been graded, and that row holds no hid at all. Refusing on an
    empty shell would block a genuinely fresh start.
    """
    if not eval_dir.exists():
        return []
    labelled = []
    for path in sorted(eval_dir.glob("*.jsonl")):
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn line is not evidence either way; the loader reports it
            if row.get("hid") or row.get("judgements") or row.get("canary_hids"):
                labelled.append(path)
                break
    return labelled


def load_salt(data_dir: Path, eval_dir: Path | None = None) -> bytes:
    """Read ``data_dir/eval_salt``, creating a random 32-byte salt only on a genuinely fresh start.

    Safe to call repeatedly and from multiple processes: once the file exists, later calls
    just read it back.

    **Refuses to mint a new salt when labelled fixtures already exist.** Every hid in
    ``eval/*.jsonl`` is ``hmac(salt, item_id)``, so a new salt does not merely lose the
    mapping -- it makes every line already written permanently unresolvable, and the
    labelling page then shows a blank slate as if no work had been done. The M7 checker
    demonstrated exactly that: 27 labelled rows, salt deleted, resume lands on item 1, and
    re-labelling appends a second set of 27 rows that the eval harness then double-counts.
    Silently regenerating is the single cheapest way to destroy hours of the owner's work.

    ``eval_dir`` defaults to ``<data_dir>/../eval``, matching the labelling page and
    ``python -m reelkb.eval``.
    """
    path = data_dir / SALT_FILE
    if path.exists():
        return path.read_bytes()

    eval_dir = eval_dir if eval_dir is not None else data_dir.parent / "eval"
    labelled = _fixtures_with_content(eval_dir)
    if labelled:
        names = ", ".join(p.name for p in labelled)
        raise SaltLostError(
            f"{path} is missing, but labelled fixtures already exist ({names}).\n"
            f"Minting a new salt would make every hid in them unresolvable, and the "
            f"labelling page would look empty as though nothing had been labelled.\n"
            f"Restore {path} from a backup. If the salt is genuinely unrecoverable, the "
            f"existing labels cannot be recovered either: move {eval_dir} aside deliberately, "
            f"then re-run to start over."
        )

    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(32))
    return path.read_bytes()


def hash_id(item_id: str, salt: bytes) -> str:
    """The fixture-file id for ``item_id``: the first 16 hex chars of HMAC-SHA256(salt, id)."""
    digest = hmac.new(salt, item_id.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest[:HID_LENGTH]


def load_lookup(data_dir: Path) -> dict[str, str]:
    """Read ``data_dir/eval_lookup.json`` ({hid: item_id}); ``{}`` if it doesn't exist yet."""
    path = data_dir / LOOKUP_FILE
    if not path.exists():
        return {}
    with path.open() as f:
        data: dict[str, str] = json.load(f)
    return data


def save_lookup(data_dir: Path, lookup: dict[str, str]) -> None:
    """Overwrite ``data_dir/eval_lookup.json`` with ``lookup``, sorted for stable diffs."""
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / LOOKUP_FILE
    path.write_text(json.dumps(lookup, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def update_lookup(data_dir: Path, item_id: str, salt: bytes | None = None) -> str:
    """Hash ``item_id``, record the mapping in the local lookup table, and return the hid.

    Idempotent: hashing the same item_id twice yields the same hid and just rewrites the same
    lookup entry.
    """
    if salt is None:
        salt = load_salt(data_dir)
    hid = hash_id(item_id, salt)
    lookup = load_lookup(data_dir)
    lookup[hid] = item_id
    save_lookup(data_dir, lookup)
    return hid


def resolve(hid: str, lookup: dict[str, str]) -> str | None:
    """item_id for ``hid``, or ``None`` if this machine's lookup doesn't have it."""
    return lookup.get(hid)
