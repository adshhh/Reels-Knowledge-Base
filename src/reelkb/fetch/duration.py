"""Measuring how long a downloaded file plays for, independent of what the vendor claims.
Uses `ffprobe` (docs/PLAN.md §6) against the file actually on disk rather than trusting a
vendor-reported field. Never raises: a missing binary, missing file, or non-media file (a
still image) all just mean "no duration", a normal answer for an image post.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

_ABSOLUTE_CANDIDATES = ("/opt/homebrew/bin/ffprobe",)


def _ffprobe_binary() -> str | None:
    for candidate in _ABSOLUTE_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return shutil.which("ffprobe")


def probe_duration(path: Path) -> float | None:
    """Best-effort duration in seconds for the media file at ``path``, or None."""
    ffprobe = _ffprobe_binary()
    if ffprobe is None or not path.exists():
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        data = json.loads(result.stdout)
        duration = data.get("format", {}).get("duration")
        return float(duration) if duration is not None else None
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return None
