"""Shared shapes passed between the prompt builder, the model client, and the fidelity gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

EntityKind = Literal["url", "handle", "title"]
AllowedSources = Literal["ocr_only", "ocr_and_caption"]
TextLocation = Literal["entities", "title", "summary", "bullets"]


@dataclass(frozen=True)
class FusionInput:
    """What the fusion stage gathered for one item, before calling the model."""

    item_id: str
    caption: str
    ocr_texts: list[str]
    transcript: str
    lyric_like: bool
    unreadable_text: bool

    def has_any_channel(self) -> bool:
        return bool(self.caption.strip() or self.ocr_texts or self.transcript.strip())


@dataclass
class FusionDraft:
    """The model's raw, ungated output. Never written to the database as-is."""

    title: str
    summary: str
    bullets: list[str]
    entities: dict[str, list[str]]  # keys: "urls", "handles", "titles"
    language: str | None = None


@dataclass(frozen=True)
class DroppedEntity:
    """One thing the fidelity gate refused to keep, and why."""

    kind: EntityKind
    value: str
    reason: str
    location: TextLocation

    def to_json(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "value": self.value,
            "reason": self.reason,
            "location": self.location,
        }


@dataclass(frozen=True)
class FlaggedName:
    """A proper-noun-looking name left in the prose that OCR text cannot confirm.

    Distinct from :class:`DroppedEntity`: a dropped entity was removed, a flagged name is
    still there. The owner decided (after seeing the measured cost) that silently deleting
    names from prose destroys correct cards -- the M0 item whose card reads "Source Code
    movie recommendation" has no on-screen text at all, so every name in it is unverifiable
    even though the model got it exactly right. Recording and surfacing the name keeps the
    card readable and the doubt visible.

    AC-3.1 is NOT met by flagging; see docs/PLAN.md S3 and DESIGN_RATIONALE #11.
    """

    value: str
    location: TextLocation
    reason: str

    def to_json(self) -> dict[str, str]:
        return {"value": self.value, "location": self.location, "reason": self.reason}


@dataclass
class GatedFusion:
    """The model's output after the fidelity gate (AC-3.1). This is what fusion.py writes."""

    title: str
    summary: str
    bullets: list[str]
    entities: dict[str, list[str]]
    dropped_entities: list[DroppedEntity] = field(default_factory=list)
    language: str | None = None
    unverified_names: list[FlaggedName] = field(default_factory=list)


@dataclass(frozen=True)
class ModelResponse:
    """What a model client returns: the raw completion text plus token usage for cost tracking."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
