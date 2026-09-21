"""Guards that apply to every unit test (AC-6.2).

1. No network: any attempt to open a connection or resolve a hostname fails the test.
2. No models, no vendors: importing a model library or a vendor client fails the test.

Both are installed at import time, before any test module is collected, so even a
module-level ``import torch`` in a test file is caught. Tests marked ``realmodel`` are
skipped unless REELKB_ALLOW_MODELS=1, which also switches both guards off:

    REELKB_ALLOW_MODELS=1 pytest -m realmodel
"""

from __future__ import annotations

import importlib.abc
import os
import socket
import sys
from collections.abc import Sequence
from types import ModuleType
from typing import Any

import pytest

ALLOW_MODELS = os.environ.get("REELKB_ALLOW_MODELS") == "1"

BLOCKED_MODULES = (
    "torch", "torchaudio", "mlx", "mlx_whisper", "onnxruntime", "silero_vad", "ocrmac",
    "FlagEmbedding", "transformers", "sentence_transformers", "sklearn",
    "groq", "apify_client", "google.genai", "yt_dlp",
)  # fmt: skip


class NetworkBlocked(RuntimeError):
    pass


class ModelImportBlocked(ImportError):
    pass


def _blocked(*_args: Any, **_kwargs: Any) -> Any:
    raise NetworkBlocked("unit tests may not use the network (AC-6.2); mark it realmodel")


class _ModelImportBlocker(importlib.abc.MetaPathFinder):
    def find_spec(
        self, fullname: str, path: Sequence[str] | None, target: ModuleType | None = None
    ) -> None:
        if any(fullname == m or fullname.startswith(m + ".") for m in BLOCKED_MODULES):
            raise ModelImportBlocked(
                f"unit tests may not import {fullname!r} (AC-6.2); mark the test realmodel"
            )
        return None


if not ALLOW_MODELS:
    socket.socket.connect = _blocked  # type: ignore[method-assign]
    socket.socket.connect_ex = _blocked  # type: ignore[method-assign]
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked
    for name in list(sys.modules):
        if any(name == m or name.startswith(m + ".") for m in BLOCKED_MODULES):
            del sys.modules[name]
    sys.meta_path.insert(0, _ModelImportBlocker())


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if ALLOW_MODELS:
        return
    skip = pytest.mark.skip(reason="realmodel test: run with REELKB_ALLOW_MODELS=1 -m realmodel")
    for item in items:
        if "realmodel" in item.keywords:
            item.add_marker(skip)
