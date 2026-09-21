"""Storage for ``eval/queries_v1.jsonl``: one query per line with pooled judgements.

    {"qid": "q01", "query": "...", "judgements": {"<hid>": 2|1|0}, "canary": false}

Rewritten atomically in full on every save, same reasoning as ``holdout_store``: resume and
edit both work by loading the whole file, changing one record, and writing it all back.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

FILENAME = "queries_v1.jsonl"


@dataclass
class QueryRecord:
    qid: str
    query: str
    judgements: dict[str, int] = field(default_factory=dict)
    canary: bool = False
    # The reels that MUST appear in this query's top 10 (AC-5.2's named canary). The eval
    # harness reads this field; without it here, re-saving a query in the labelling page
    # rewrites the line and silently erases the naming -- turning the canary back into the
    # toothless query-level boolean it used to be. (Code review, finding 3.)
    canary_hids: list[str] = field(default_factory=list)


def load_queries(eval_dir: Path) -> dict[str, QueryRecord]:
    """qid -> QueryRecord, in file order."""
    path = eval_dir / FILENAME
    if not path.exists():
        return {}
    out: dict[str, QueryRecord] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        judgements = {str(k): int(v) for k, v in dict(row.get("judgements", {})).items()}
        out[str(row["qid"])] = QueryRecord(
            qid=str(row["qid"]),
            query=str(row["query"]),
            judgements=judgements,
            canary=bool(row.get("canary", False)),
            canary_hids=[str(h) for h in row.get("canary_hids", [])],
        )
    return out


def next_qid(existing: dict[str, QueryRecord]) -> str:
    n = 1
    while f"q{n:02d}" in existing:
        n += 1
    return f"q{n:02d}"


def save_query(eval_dir: Path, record: QueryRecord) -> None:
    existing = load_queries(eval_dir)
    existing[record.qid] = record
    _write_all(eval_dir, existing)


def _write_all(eval_dir: Path, records: dict[str, QueryRecord]) -> None:
    eval_dir.mkdir(parents=True, exist_ok=True)
    path = eval_dir / FILENAME
    tmp = path.with_name(FILENAME + ".tmp")
    with tmp.open("w") as f:
        for r in records.values():
            f.write(
                json.dumps(
                    {
                        "qid": r.qid,
                        "query": r.query,
                        "judgements": r.judgements,
                        "canary": r.canary,
                        "canary_hids": r.canary_hids,
                    }
                )
                + "\n"
            )
    os.replace(tmp, path)
