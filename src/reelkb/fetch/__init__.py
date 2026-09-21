"""Stage 3: vendor fetch + manifest.

Owns ``fetch_status`` (see ``docs/CONTRACT.md``) and ``data/media/``. Run as
``python -m reelkb.fetch``; see ``cli.py`` for the flags and ``docs/PLAN.md`` §2 (AC-2.2,
AC-2.3) and §8 (AC-8.1) for what this stage is required to prove.
"""

from __future__ import annotations

from .types import Fetcher, FetchRequest, FetchResult, MediaFile

__all__ = ["Fetcher", "FetchRequest", "FetchResult", "MediaFile"]
