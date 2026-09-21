"""Pure parsing logic for ``message_1.json`` (no I/O, no database — easy to unit test).

The export is a Meta "Download Your Information" DM thread. Each message is one of:

* a **share** — a link the owner sent himself, with an optional caption (``share_text``)
  and source account (``original_content_owner``). Shares split into:
    - a `/reel/<code>` or `/p/<code>` Instagram link  -> kind ``reel`` / ``post``
    - anything else (another site, or an Instagram profile share) -> kind ``external``
* an **attachment** — Messenger's own "X sent an attachment." text, with no ``share`` key
  and no recoverable link or caption.
* a **note** — typed text with no ``share`` key that is not the attachment placeholder.

Two encoding facts about the raw file drive the design:

1. The export is mojibake: real UTF-8 bytes were read back as Latin-1, so every string
   needs ``s.encode("latin-1").decode("utf-8")`` to come out clean. See :func:`fix_mojibake`.
2. Messages are stored newest-first (verified against the real export: strictly descending
   ``timestamp_ms``, zero collisions). Parsing sorts them oldest-first before deduplicating,
   so "the earliest message wins" and "the first non-empty caption/account" are the *same*
   scan direction instead of two different tie-break rules (an independent decision — see
   the M2 checkpoint report).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

Kind = Literal["reel", "post", "attachment", "external", "note"]

_REEL_PATH = re.compile(r"^/reel/([^/?]+)")
_POST_PATH = re.compile(r"^/p/([^/?]+)")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")

# The literal placeholder Messenger writes for "sent an attachment with no share data"
# (§2 of docs/PLAN.md: 358 of these in the real export). Matched as a substring because
# it is prefixed with the sender's name, which varies.
_ATTACHMENT_MARKER = "sent an attachment"


@dataclass
class ParsedItem:
    """One row bound for the ``items`` table (schema in ``contract/schema.sql``)."""

    item_id: str
    kind: Kind
    url: str | None
    caption: str | None
    source_account: str | None
    sent_at_ms: int  # converted to ISO-8601 UTC at write time (db.py has no ms->ISO need)
    caption_language: str | None


@dataclass
class ParseStats:
    """Per-kind counts plus data-quality counters, printed by ``__main__`` after a run."""

    counts: dict[Kind, int] = field(default_factory=lambda: dict.fromkeys(_KINDS, 0))
    mojibake_failures: int = 0
    duplicate_shares: int = 0  # reel/post occurrences collapsed into an existing item_id

    def record(self, kind: Kind) -> None:
        self.counts[kind] += 1


_KINDS: tuple[Kind, ...] = ("reel", "post", "attachment", "external", "note")


def fix_mojibake(s: str) -> tuple[str, bool]:
    """Undo "UTF-8 bytes read as Latin-1". Returns ``(text, ok)``.

    ``ok`` is False when the round-trip itself fails (not every Latin-1 byte sequence is
    valid UTF-8) — callers keep ``s`` unchanged and count the failure rather than raising,
    per the M2 build spec ("handle strings where that fails gracefully").
    """
    try:
        return s.encode("latin-1").decode("utf-8"), True
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s, False


def _fix(s: str | None, stats: ParseStats) -> str | None:
    """Apply :func:`fix_mojibake` to an optional field, folding failures into ``stats``."""
    if s is None:
        return None
    fixed, ok = fix_mojibake(s)
    if not ok:
        stats.mojibake_failures += 1
    return fixed


def detect_caption_language(caption: str | None) -> str | None:
    """Script-level language tag (D16). No dependency beyond the stdlib ``re`` module.

    - ``None`` for an empty/missing caption (nothing to detect — not invented).
    - ``"hi-Deva"`` if any Devanagari codepoint (U+0900-U+097F) is present.
    - ``"latn"`` if more than half of the alphabetic characters are A-Z/a-z (covers English
      and "Hinglish" typed in Latin letters, which Apple Vision OCR also reads as Latin —
      see §3 of docs/PLAN.md).
    - ``"other"`` otherwise (e.g. Arabic, Cyrillic, or a caption with no letters at all).
    """
    if caption is None:
        return None
    stripped = caption.strip()
    if not stripped:
        return None
    if _DEVANAGARI.search(stripped):
        return "hi-Deva"
    letters = [c for c in stripped if c.isalpha()]
    if not letters:
        return "other"
    latin_count = sum(1 for c in letters if _LATIN_LETTER.match(c))
    return "latn" if latin_count / len(letters) > 0.5 else "other"


def _is_instagram_domain(netloc: str) -> bool:
    netloc = netloc.lower()
    return netloc == "instagram.com" or netloc.endswith(".instagram.com")


def _classify_link(url: str) -> tuple[Kind, str | None]:
    """Given an already mojibake-fixed link, return (kind, shortcode-or-None).

    Domain is checked *before* the path pattern — a non-Instagram URL that happens to have
    a `/p/...` path (a Substack post link did, in the real export) must not be mistaken for
    an Instagram post. Only a `/reel/` or `/p/` path on an instagram.com host resolves to a
    shortcode; everything else on that host (profile shares, stories, etc.) is `external`
    with no shortcode, same as an outside link.
    """
    parsed = urlparse(url)
    if _is_instagram_domain(parsed.netloc):
        if m := _REEL_PATH.match(parsed.path):
            return "reel", m.group(1)
        if m := _POST_PATH.match(parsed.path):
            return "post", m.group(1)
    return "external", None


def iso_utc(ms: int) -> str:
    """Convert an export ``timestamp_ms`` to an ISO-8601 UTC string for ``items.sent_at``."""
    return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat()


def parse_messages(messages: list[dict[str, Any]]) -> tuple[list[ParsedItem], ParseStats]:
    """Turn the export's ``messages`` list into deduplicated items ready for the database.

    Messages are processed oldest-first (see module docstring) so that, for a shortcode
    shared more than once, the earliest occurrence sets ``sent_at`` and the first non-empty
    caption/account encountered while scanning forward is kept — one rule, one direction.
    """
    stats = ParseStats()
    by_id: dict[str, ParsedItem] = {}
    order: list[str] = []  # preserves first-seen order for a stable, testable output list

    for msg in sorted(messages, key=lambda m: m["timestamp_ms"]):
        ms = msg["timestamp_ms"]
        share = msg.get("share")

        if share is not None:
            link = _fix(share.get("link"), stats)
            caption = _fix(share.get("share_text"), stats)
            account = _fix(share.get("original_content_owner"), stats) or _fix(
                share.get("profile_share_username"), stats
            )
            if link:
                kind, code = _classify_link(link)
            else:
                # A share with no link at all (seen once in the real export: only
                # original_content_owner survived). Unresolvable -> external, not invented.
                kind, code = "external", None
        else:
            content = _fix(msg.get("content"), stats)
            link = None
            account = None
            if content is not None and _ATTACHMENT_MARKER in content:
                # Messenger's own placeholder text ("X sent an attachment.") is not real
                # content -- PLAN.md §2 describes these as "no link, no caption". Kept out
                # of `caption` so an attachment item is visibly empty, not full of boilerplate.
                kind, code, caption = "attachment", None, None
            else:
                # Covers both typed notes and the no-share/no-content case (e.g. a bare photo
                # message). The task brief's literal rule ("no share and no content ->
                # attachment") would make the photo case the 359th attachment, but AC-2.3
                # locks the attachment count at exactly 358 (matching the real export) and
                # PLAN.md §2 separately counts "~7 typed text" messages -- 6 real typed notes
                # plus this one lands on 7. Treated as `note` to satisfy both ACs; flagged in
                # the M2 checkpoint report as a resolved contract conflict rather than
                # silently picking one reading.
                kind, code, caption = "note", None, content

        if kind in ("reel", "post"):
            assert code is not None
            item_id = code
            if item_id in by_id:
                stats.duplicate_shares += 1
                existing = by_id[item_id]
                # An empty string counts as "no caption here", not as a caption. The earliest
                # occurrence of a shortcode often carries `share_text: ""` (135 of 1,870 real
                # shares have no caption text at all), and treating "" as present would let it
                # permanently block real text from a later occurrence.
                if not (existing.caption or "").strip() and (caption or "").strip():
                    existing.caption = caption
                if not (existing.source_account or "").strip() and (account or "").strip():
                    existing.source_account = account
                if existing.url is None and link is not None:
                    existing.url = link
                # sent_at already earliest: ascending scan means the first occurrence wins.
                continue
            stats.record(kind)
            by_id[item_id] = ParsedItem(
                item_id=item_id,
                kind=kind,
                url=link,
                caption=caption,
                source_account=account,
                sent_at_ms=ms,
                caption_language=detect_caption_language(caption),
            )
            order.append(item_id)
            continue

        prefix = {"attachment": "att", "external": "ext", "note": "note"}[kind]
        item_id = f"{prefix}-{ms}"
        stats.record(kind)
        by_id[item_id] = ParsedItem(
            item_id=item_id,
            kind=kind,
            url=link,
            caption=caption,
            source_account=account,
            sent_at_ms=ms,
            caption_language=detect_caption_language(caption),
        )
        order.append(item_id)

    return [by_id[i] for i in order], stats
