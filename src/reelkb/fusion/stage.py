"""The fusion stage (M5): caption + OCR + transcript -> model -> fidelity gate -> `fusion` row.

For every item that has both an `ocr_runs` row and a `transcripts` row but no `fusion` row
yet, this stage builds a prompt, calls a `FusionModelClient`, parses its JSON, runs the
fidelity gate (`reelkb.fusion.fidelity.gate`), and writes the result through
`connect_stage(db, "fusion")` — so the database itself refuses any write outside the `fusion`
table (AC-3.3), and the write-once trigger on `ocr_verbatim` means fusion cannot touch it even
by accident.

Resumable and idempotent: each item is looked up fresh from `fusion` before being processed
(the "no fusion row yet" join), and each row is committed as soon as it's written, so killing
the stage mid-run and restarting it only redoes unfinished items (AC-8.1's pattern, applied
here).

Items with zero non-empty channels (no caption, no OCR text, no transcript) get **no** fusion
row at all — there would be nothing for the model to work from, and a written cost for an
empty result would sit in the database as a null-content fusion row. They are counted in
`RunSummary.skipped_empty` and reported, not silently dropped.

**OCR-only vs OCR+caption — the trade-off (owner decision, not made here).** AC-3.1 is written
against "that reel's OCR output" only, so `allowed_sources="ocr_only"` is the default and what
`__main__.py` runs unless told otherwise. `allowed_sources="ocr_and_caption"` is implemented
(`fidelity.gate` accepts it) but never the default. Under the strict default, a title that is
only *spoken* in the caption text and never appears on screen is dropped by the gate even
though the caption is right there in the prompt — captions are read by the model as context,
but not as a verification source. Under `ocr_and_caption`, that same title survives, at the
cost of trusting the caption's honesty the same way OCR's verbatim reading is trusted, which
is a materially different guarantee (a caption can lie by omission or embellishment per D3;
OCR just reads pixels). See the milestone report for the recommendation.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime

from reelkb.fusion import prompt_builder
from reelkb.fusion.fidelity import gate
from reelkb.fusion.model_client import DEFAULT_MODEL, FusionModelClient
from reelkb.fusion.types import FusionDraft, FusionInput, GatedFusion

# Rough estimate only, for a per-run sanity print -- not a billing source. Confirm against
# Groq's current pricing page before treating this as a real budget number.
PRICE_PER_1M_INPUT_TOKENS_USD = 0.15
PRICE_PER_1M_OUTPUT_TOKENS_USD = 0.75


class FusionParseError(ValueError):
    """The model's response wasn't the JSON shape we asked for."""


@dataclass
class RunSummary:
    items_considered: int = 0
    items_written: int = 0
    items_skipped_empty: list[str] = field(default_factory=list)
    items_failed: list[tuple[str, str]] = field(default_factory=list)  # (item_id, reason)
    dropped_entities_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.prompt_tokens / 1_000_000 * PRICE_PER_1M_INPUT_TOKENS_USD
            + self.completion_tokens / 1_000_000 * PRICE_PER_1M_OUTPUT_TOKENS_USD
        )

    def report(self) -> str:
        lines = [
            f"fusion: considered {self.items_considered}, wrote {self.items_written}, "
            f"skipped {len(self.items_skipped_empty)} (zero channels), "
            f"failed {len(self.items_failed)}",
            f"fusion: dropped {self.dropped_entities_count} unverified entities "
            "(fidelity gate, AC-3.1)",
            f"fusion: ~{self.prompt_tokens} prompt + {self.completion_tokens} completion "
            f"tokens, ~${self.estimated_cost_usd:.4f} estimated (rough; check Groq pricing)",
        ]
        if self.items_failed:
            lines.append("fusion: failed items: " + ", ".join(i for i, _ in self.items_failed))
        return "\n".join(lines)


def _pending_item_ids(conn: sqlite3.Connection, limit: int | None) -> list[str]:
    sql = """
        SELECT o.item_id
        FROM ocr_runs o
        JOIN transcripts t ON t.item_id = o.item_id
        LEFT JOIN fusion f ON f.item_id = o.item_id
        WHERE f.item_id IS NULL
        ORDER BY o.item_id
    """
    if limit is not None:
        sql += " LIMIT ?"
        rows = conn.execute(sql, (limit,))
    else:
        rows = conn.execute(sql)
    return [r[0] for r in rows]


def _ocr_texts(conn: sqlite3.Connection, item_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT text FROM ocr_verbatim WHERE item_id = ? ORDER BY frame_ts_s, rowid", (item_id,)
    )
    seen: list[str] = []
    for (text,) in rows:
        if text not in seen:
            seen.append(text)
    return seen


def _gather_input(conn: sqlite3.Connection, item_id: str) -> FusionInput:
    item_row = conn.execute("SELECT caption FROM items WHERE item_id = ?", (item_id,)).fetchone()
    caption = (item_row[0] if item_row and item_row[0] else "") or ""
    transcript_row = conn.execute(
        "SELECT text, lyric_like FROM transcripts WHERE item_id = ?", (item_id,)
    ).fetchone()
    transcript = transcript_row[0] if transcript_row else ""
    lyric_like = bool(transcript_row[1]) if transcript_row else False
    ocr_run_row = conn.execute(
        "SELECT unreadable_text FROM ocr_runs WHERE item_id = ?", (item_id,)
    ).fetchone()
    unreadable_text = bool(ocr_run_row[0]) if ocr_run_row else False
    return FusionInput(
        item_id=item_id,
        caption=caption,
        ocr_texts=_ocr_texts(conn, item_id),
        transcript=transcript or "",
        lyric_like=lyric_like,
        unreadable_text=unreadable_text,
    )


def parse_model_output(raw_text: str) -> FusionDraft:
    """Parse the model's JSON completion into a `FusionDraft`. Tolerates a fenced code block
    (```json ... ```), since some models wrap JSON in markdown even when asked not to."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FusionParseError(f"model output was not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise FusionParseError(f"model output was not a JSON object: {type(data).__name__}")

    title = data.get("title")
    summary = data.get("summary")
    if not isinstance(title, str) or not isinstance(summary, str):
        raise FusionParseError("model output missing string 'title' or 'summary'")

    bullets_raw = data.get("bullets", [])
    if not isinstance(bullets_raw, list):
        raise FusionParseError("model output 'bullets' was not a list")
    bullets = [b for b in bullets_raw if isinstance(b, str) and b.strip()]

    entities_raw = data.get("entities", {})
    if not isinstance(entities_raw, dict):
        raise FusionParseError("model output 'entities' was not an object")
    entities = {}
    for key in ("urls", "handles", "titles"):
        values = entities_raw.get(key, [])
        entities[key] = (
            [v for v in values if isinstance(v, str) and v.strip()]
            if isinstance(values, list)
            else []
        )

    language = data.get("language")
    language = language if isinstance(language, str) and language.strip() else None

    return FusionDraft(
        title=title, summary=summary, bullets=bullets, entities=entities, language=language
    )


def _write_fusion_row(
    conn: sqlite3.Connection, item_id: str, gated: GatedFusion, model: str
) -> None:
    conn.execute(
        "INSERT INTO fusion "
        "(item_id, title, summary, bullets, entities, dropped_entities, unverified_names, "
        "language, model, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            item_id,
            gated.title,
            gated.summary,
            json.dumps(gated.bullets),
            json.dumps(gated.entities),
            json.dumps([d.to_json() for d in gated.dropped_entities]),
            json.dumps([f.to_json() for f in gated.unverified_names]),
            gated.language,
            model,
            datetime.now(UTC).isoformat(timespec="seconds"),
        ),
    )
    conn.commit()  # per-item commit so a mid-run kill leaves already-written items intact


def run(
    conn: sqlite3.Connection,
    client: FusionModelClient,
    *,
    limit: int | None = None,
    allowed_sources: str = "ocr_only",
    model_name: str = DEFAULT_MODEL,
    log: object = None,
) -> RunSummary:
    """Run the fusion stage over ``conn`` (already opened with `connect_stage(db, "fusion")`).

    ``client`` is anything satisfying `FusionModelClient` — a `GroqFusionClient` for a real
    run, or a fake in tests. ``log``, if given, is a callable(str) used to print per-item
    progress; defaults to nothing so tests stay quiet.
    """
    summary = RunSummary()
    printer = log if callable(log) else (lambda _msg: None)

    item_ids = _pending_item_ids(conn, limit)
    for item_id in item_ids:
        summary.items_considered += 1
        inp = _gather_input(conn, item_id)
        if not inp.has_any_channel():
            summary.items_skipped_empty.append(item_id)
            printer(f"fusion: {item_id} skipped (zero non-empty channels)")
            continue

        # The call and the parse are separated deliberately. Tokens are billed the moment the
        # model answers, whether or not the answer is usable -- counting them only on the
        # success path meant every parse failure was billed but invisible, so the run's cost
        # estimate read low exactly when things were going wrong. (Code review, finding 8.)
        try:
            response = client.complete(
                system=prompt_builder.system_prompt(), user=prompt_builder.user_prompt(inp)
            )
        except Exception as exc:
            # Any client-side failure -- a rate limit, a dropped connection, a 500 -- used to
            # abort the whole run without recording the item, so a stage part-way through
            # 1,300 items reported nothing at all. Record it and carry on; the item simply has
            # no fusion row, and the next run picks it up.
            summary.items_failed.append((item_id, f"{type(exc).__name__}: {exc}"))
            printer(f"fusion: {item_id} FAILED calling the model: {exc}")
            continue

        summary.prompt_tokens += response.prompt_tokens
        summary.completion_tokens += response.completion_tokens

        try:
            draft = parse_model_output(response.text)
        except FusionParseError as exc:
            summary.items_failed.append((item_id, str(exc)))
            printer(f"fusion: {item_id} FAILED to parse model output: {exc}")
            continue

        gated = gate(
            draft,
            ocr_texts=inp.ocr_texts,
            caption=inp.caption,
            allowed_sources=allowed_sources,
        )
        summary.dropped_entities_count += len(gated.dropped_entities)

        _write_fusion_row(conn, item_id, gated, model_name)
        summary.items_written += 1
        printer(
            f"fusion: {item_id} written "
            f"({len(gated.dropped_entities)} entities dropped by the gate)"
        )

    return summary


# Note: retries with backoff for Groq 429/5xx live in `GroqFusionClient.complete`
# (`reelkb.fusion.model_client`), not here. This loop just calls `client.complete` once per
# item and treats retry as the client's concern, per the `FusionModelClient` protocol (it
# either returns a `ModelResponse` or raises).
