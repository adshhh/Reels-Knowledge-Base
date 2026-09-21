"""M0 step 3: Fetch B -- yt-dlp, logged OUT, no cookies, on the same 50-item sample.

Throttled with a random 10-30s delay between items (politeness, avoid
tripping a rate limit that would poison the measurement). Stops early if 5
consecutive items show a login-wall or rate-limit style error, and records
that as a finding rather than grinding through 50 identical failures.

If Apify already succeeded for a shortcode (data/m0/apify_results.jsonl,
status == "success"), yt-dlp still attempts the fetch (this is an
independent measurement of yt-dlp's own success rate) but the downloaded
file is deleted immediately after recording its size -- we don't keep two
copies of media Apify already retained.

Resumable: skips shortcodes already present in data/m0/ytdlp_results.jsonl.

Writes:
  data/m0/ytdlp_results.jsonl  -- per-item outcome
  data/m0/media/ytdlp_<shortcode>.*  -- kept only when Apify did NOT succeed
"""

import json
import random
import time
from pathlib import Path

import yt_dlp

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "m0" / "sample.jsonl"
MEDIA_DIR = ROOT / "data" / "m0" / "media"
APIFY_RESULTS = ROOT / "data" / "m0" / "apify_results.jsonl"
RESULTS_OUT = ROOT / "data" / "m0" / "ytdlp_results.jsonl"

FFMPEG_LOCATION = "/opt/homebrew/bin"
MIN_DELAY_SEC = 10
MAX_DELAY_SEC = 30
CONSECUTIVE_FAILURE_STOP = 5

LOGIN_WALL_HINTS = (
    "login",
    "log in",
    "rate-limit",
    "rate limit",
    "429",
    "requested content is not available",
    "restricted",
    "private",
)


def already_done() -> set[str]:
    if not RESULTS_OUT.exists():
        return set()
    return {
        json.loads(line)["shortcode"]
        for line in RESULTS_OUT.read_text().splitlines()
        if line.strip()
    }


def apify_success_shortcodes() -> set[str]:
    if not APIFY_RESULTS.exists():
        return set()
    out = set()
    for line in APIFY_RESULTS.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("status") == "success":
            out.add(row["shortcode"])
    return out


def classify_error(msg: str) -> str:
    low = msg.lower()
    for hint in LOGIN_WALL_HINTS:
        if hint in low:
            return "login_wall_or_rate_limit"
    return "other_error"


def fetch_one(link: str, shortcode: str, keep: bool) -> dict:
    outtmpl = str(MEDIA_DIR / f"ytdlp_{shortcode}.%(ext)s")
    result = {
        "shortcode": shortcode,
        "status": "error",
        "error_reason": None,
        "error_class": None,
        "file_size_bytes": None,
        "duration_sec": None,
        "downloaded_path": None,
        "wall_time_sec": None,
    }
    ydl_opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "cookiesfrombrowser": None,
        "cookiefile": None,
        "ffmpeg_location": FFMPEG_LOCATION,
        "noplaylist": True,
        "retries": 1,
        "socket_timeout": 30,
    }
    t0 = time.time()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(link, download=True)
        result["wall_time_sec"] = round(time.time() - t0, 2)
        result["duration_sec"] = info.get("duration")
        filepath = ydl.prepare_filename(info)
        p = Path(filepath)
        if p.exists():
            result["file_size_bytes"] = p.stat().st_size
            result["status"] = "success"
            if keep:
                result["downloaded_path"] = str(p.relative_to(ROOT))
            else:
                p.unlink()
                result["downloaded_path"] = None
        else:
            result["status"] = "error"
            result["error_reason"] = "download reported success but file missing"
    except Exception as e:
        result["wall_time_sec"] = round(time.time() - t0, 2)
        result["error_reason"] = str(e)[:400]
        result["error_class"] = classify_error(result["error_reason"])
        result["status"] = "error"
    return result


def main():
    sample = [json.loads(line) for line in SAMPLE.read_text().splitlines()]
    done = already_done()
    todo = [item for item in sample if item["shortcode"] not in done]
    apify_ok = apify_success_shortcodes()
    print(
        f"loaded {len(sample)} items, {len(done)} already done, "
        f"{len(todo)} remaining. Apify already has {len(apify_ok)} of these."
    )

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    consecutive_login_wall = 0
    stopped_early = False

    with RESULTS_OUT.open("a") as res_f:
        for i, item in enumerate(todo, 1):
            shortcode = item["shortcode"]
            link = item["link"]
            keep = shortcode not in apify_ok

            print(f"[{i}/{len(todo)}] yt-dlp fetching {shortcode} (keep={keep}) ...", flush=True)
            result = fetch_one(link, shortcode, keep)
            res_f.write(json.dumps(result) + "\n")
            res_f.flush()
            print(
                f"    -> {result['status']} "
                f"{result.get('error_class') or ''} "
                f"{result.get('error_reason') or ''}"[:160]
            )

            if result["status"] != "success" and result.get("error_class") == (
                "login_wall_or_rate_limit"
            ):
                consecutive_login_wall += 1
            else:
                consecutive_login_wall = 0

            if consecutive_login_wall >= CONSECUTIVE_FAILURE_STOP:
                print(
                    f"STOPPING EARLY: {CONSECUTIVE_FAILURE_STOP} consecutive "
                    "login-wall/rate-limit errors."
                )
                stopped_early = True
                break

            if i < len(todo):
                delay = random.uniform(MIN_DELAY_SEC, MAX_DELAY_SEC)
                print(f"    sleeping {delay:.1f}s ...", flush=True)
                time.sleep(delay)

    if stopped_early:
        marker = ROOT / "data" / "m0" / "ytdlp_stopped_early.txt"
        marker.write_text(
            f"Stopped after {CONSECUTIVE_FAILURE_STOP} consecutive "
            "login-wall/rate-limit errors from yt-dlp.\n"
        )
        print(f"wrote {marker}")

    print("done")


if __name__ == "__main__":
    main()
