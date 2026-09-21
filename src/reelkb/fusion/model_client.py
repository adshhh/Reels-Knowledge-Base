"""The model client boundary: fusion talks to *some* JSON-completing model through a small
Protocol, so tests can inject a fake and never load a model or touch the network (AC-6.2).

``GroqFusionClient`` is the real implementation (`openai/gpt-oss-120b` on Groq, per §6/D17).
It imports the ``groq`` package lazily, inside ``__init__``, not at module load time — the
unit-test import guard (`tests/conftest.py`) blocks importing ``groq`` anywhere, and this
module is imported by the fusion stage even when a fake client is used, so a top-level
``import groq`` would break every unit test, not just ones that need a real client.
"""

from __future__ import annotations

import time
from typing import Protocol

from reelkb.fusion.types import ModelResponse

DEFAULT_MODEL = "openai/gpt-oss-120b"

# Groq's retryable statuses: 429 (rate limit) and 5xx (their side breaking, not ours).
RETRYABLE_MAX_ATTEMPTS = 5
RETRYABLE_BACKOFF_BASE_S = 1.0


class FusionModelClient(Protocol):
    """Anything that can turn (system prompt, user prompt) into a JSON completion."""

    def complete(self, *, system: str, user: str) -> ModelResponse: ...


class GroqFusionClient:
    """Talks to Groq's chat completions API. Never imported/instantiated in unit tests."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        max_attempts: int = RETRYABLE_MAX_ATTEMPTS,
        backoff_base_s: float = RETRYABLE_BACKOFF_BASE_S,
        sleep: object = time.sleep,
    ) -> None:
        import groq  # lazy: see module docstring

        self._groq = groq
        self._client = groq.Groq(api_key=api_key)
        self._model = model
        self._max_attempts = max_attempts
        self._backoff_base_s = backoff_base_s
        self._sleep = sleep

    def complete(self, *, system: str, user: str) -> ModelResponse:
        retryable = (
            self._groq.RateLimitError,
            self._groq.InternalServerError,
            self._groq.APIConnectionError,
        )
        last_exc: Exception | None = None
        for attempt in range(self._max_attempts):
            try:
                resp = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.2,
                )
                usage = resp.usage
                message = resp.choices[0].message.content or ""
                return ModelResponse(
                    text=message,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                )
            except retryable as exc:  # noqa: PERF203 - retry loop, not a hot path
                last_exc = exc
                if attempt == self._max_attempts - 1:
                    raise
                self._sleep(self._backoff_base_s * (2**attempt))  # type: ignore[operator]
        raise RuntimeError("unreachable: loop always returns or raises") from last_exc
