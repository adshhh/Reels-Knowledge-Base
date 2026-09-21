"""A fake `FusionModelClient` for tests: returns canned JSON, never touches a model or the
network. Injected everywhere `tests/fusion/` needs a client, per `FusionModelClient`'s
Protocol contract in `reelkb.fusion.model_client`.
"""

from __future__ import annotations

import json

from reelkb.fusion.types import ModelResponse


class FakeFusionClient:
    """Returns a scripted response per item_id (by matching a substring of the user prompt),
    or a default response otherwise. Records every call for assertions."""

    def __init__(
        self,
        responses: dict[str, dict[str, object]] | None = None,
        *,
        default: dict[str, object] | None = None,
        raw_text: dict[str, str] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.default = default or {
            "title": "Untitled",
            "summary": "A clip.",
            "bullets": [],
            "entities": {"urls": [], "handles": [], "titles": []},
            "language": "en",
        }
        self.raw_text = raw_text or {}  # match -> literal raw text, bypasses JSON encoding
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str) -> ModelResponse:
        self.calls.append((system, user))
        for match, text in self.raw_text.items():
            if match in user:
                return ModelResponse(text=text, prompt_tokens=10, completion_tokens=5)
        for match, payload in self.responses.items():
            if match in user:
                return ModelResponse(
                    text=json.dumps(payload), prompt_tokens=10, completion_tokens=5
                )
        return ModelResponse(text=json.dumps(self.default), prompt_tokens=10, completion_tokens=5)
