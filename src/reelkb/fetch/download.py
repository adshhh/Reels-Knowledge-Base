"""Getting a vendor's media URL(s) onto disk. Its own small module, separate from the
fetchers, for AC-8.1 (writes go to a ``.part`` temp name, renamed into place only once
complete, so a kill mid-download never leaves a file that looks fetched but isn't) and so a
vendor-specific URL quirk -- like Apify's 403 on re-hosted URLs, `apify_url_fixup` -- drops in
through one hook (``url_fixup``) without touching the fetchers or the orchestrator.
"""

from __future__ import annotations

import os
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .types import FetchResult

# (url) -> possibly-rewritten url. Swap this to change how a vendor's URLs get fixed up
# before download, without touching the download loop itself.
UrlFixup = Callable[[str], str]


def apify_url_fixup(url: str) -> str:
    """Appends the Apify token to re-hosted key-value-store URLs, which 403 without it on a
    non-paying account (undocumented; found running M0, `docs/M0_FINDINGS.md` §3)."""
    if "api.apify.com/v2/key-value-stores/" in url and "token=" not in url:
        token = os.environ.get("APIFY_TOKEN")
        if token:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}token={token}"
    return url


def no_fixup(url: str) -> str:
    return url


def fetch_url_bytes(url: str, dest: Path, *, url_fixup: UrlFixup = no_fixup) -> int:
    """Download ``url`` to ``dest`` and return the byte count. The real, network-using path."""
    url = url_fixup(url)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as response, dest.open("wb") as f:
        while True:
            chunk = response.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    return dest.stat().st_size


def _extension_for(media_type: str, url: str) -> str:
    if media_type == "video":
        return "mp4"
    stem = url.split("?")[0].lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if stem.endswith(ext):
            return ext.lstrip(".")
    return "jpg"


Downloader = Callable[..., int]


def download_result(
    result: FetchResult,
    media_dir: Path,
    *,
    downloader: Downloader = fetch_url_bytes,
    url_fixup: UrlFixup = no_fixup,
) -> tuple[str, int]:
    """Write every file in a successful :class:`FetchResult` to disk.

    Single video/image: ``data/media/<item_id>.<ext>``. Carousel: one file per slide under
    ``data/media/<item_id>/<n>.<ext>``. Returns (path relative to ``data/``, total bytes).
    Tests pass a fake ``downloader`` so no unit test ever opens a socket.
    """
    if not result.files:
        raise ValueError(f"download_result called with no files for {result.item_id}")

    media_dir.mkdir(parents=True, exist_ok=True)
    data_dir = media_dir.parent

    if result.media_type == "carousel":
        item_dir = media_dir / result.item_id
        item_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        for n, media_file in enumerate(result.files):
            ext = _extension_for(media_file.media_type, media_file.url)
            dest = item_dir / f"{n}.{ext}"
            tmp = dest.with_name(dest.name + ".part")
            total += downloader(media_file.url, tmp, url_fixup=url_fixup)
            tmp.rename(dest)
        return str(item_dir.relative_to(data_dir)), total

    media_file = result.files[0]
    ext = _extension_for(media_file.media_type, media_file.url)
    dest = media_dir / f"{result.item_id}.{ext}"
    tmp = dest.with_name(dest.name + ".part")
    total = downloader(media_file.url, tmp, url_fixup=url_fixup)
    tmp.rename(dest)
    return str(dest.relative_to(data_dir)), total
