"""M0 step 2: Fetch A -- Apify `memo23/instagram-video-downloader` on the 50-item sample. One
actor call per item (sequential -- see the billable-cap bug at its fix site below),
downloading every carousel slide as well as videos. Resumable at the row level. Two real bugs
found and fixed while building this are written up in `docs/M0_FINDINGS.md` §3, not
duplicated here. Writes `apify_raw.jsonl`, `apify_results.jsonl` and `media/<shortcode>.*`,
all gitignored.
"""

import json
import os
import time
import urllib.request
from pathlib import Path

from apify_client import ApifyClient

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "m0" / "sample.jsonl"
MEDIA_DIR = ROOT / "data" / "m0" / "media"
RAW_OUT = ROOT / "data" / "m0" / "apify_raw.jsonl"
RESULTS_OUT = ROOT / "data" / "m0" / "apify_results.jsonl"

ACTOR_ID = "piwPghZZql1jcdYcH"  # memo23/instagram-video-downloader, verified
APIFY_BUDGET_USD = 2.50  # soft cap for this vendor within the $6 total M0 budget


def download(url: str, dest: Path) -> int:
    # Re-hosted key-value-store URLs are private under this non-paying account -- a plain
    # GET 403s (undocumented; the actor README implies they're public). Appending the Apify
    # token as a query param fixes it. Full detail: docs/M0_FINDINGS.md §3.
    if "api.apify.com/v2/key-value-stores/" in url and "token=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}token={os.environ['APIFY_TOKEN']}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r, dest.open("wb") as f:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            f.write(chunk)
    return dest.stat().st_size


def load_raw_rows() -> dict[str, dict]:
    """shortcode -> most recent raw dataset row on disk."""
    rows: dict[str, dict] = {}
    if not RAW_OUT.exists():
        return rows
    for line in RAW_OUT.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[row["shortcode"]] = row
    return rows


def load_results() -> dict[str, dict]:
    """shortcode -> most recent result row on disk."""
    results: dict[str, dict] = {}
    if not RESULTS_OUT.exists():
        return results
    for line in RESULTS_OUT.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        results[r["shortcode"]] = r
    return results


def blank_result(shortcode: str) -> dict:
    return {
        "shortcode": shortcode,
        "status": "error",
        "error_reason": None,
        "media_type": None,
        "file_size_bytes": None,
        "duration_sec": None,
        "downloaded_path": None,
        "cost_usd": None,
        "wall_time_sec": None,
    }


def process_dataset_row(shortcode: str, row: dict) -> dict:
    """Turn one already-fetched Apify dataset row into a result row,
    downloading media as needed. Makes no actor call, so no cost."""
    result = blank_result(shortcode)
    t0 = time.time()

    error = row.get("error") or row.get("errorMessage")
    if error:
        result["status"] = "dead"
        result["error_reason"] = str(error)[:300]
        result["wall_time_sec"] = round(time.time() - t0, 2)
        return result

    video_url = row.get("videoUrl") or row.get("videoDownloadUrl")
    cover_url = row.get("coverUrl") or row.get("coverDownloadUrl")
    slides = row.get("slides")
    product_type = row.get("productType") or row.get("type") or row.get("postType")
    result["duration_sec"] = (
        row.get("duration") or row.get("videoDuration") or row.get("durationSeconds")
    )

    if slides:
        result["media_type"] = "carousel"
    elif video_url:
        result["media_type"] = "video"
    elif cover_url:
        result["media_type"] = "image"
    else:
        result["media_type"] = product_type or "unknown"

    try:
        if slides:
            paths = []
            total_size = 0
            for slide in slides:
                idx = slide.get("index")
                s_video = slide.get("videoUrl")
                s_image = slide.get("imageUrl")
                if s_video:
                    dest = MEDIA_DIR / f"{shortcode}_slide{idx}.mp4"
                    size = download(s_video, dest)
                elif s_image:
                    dest = MEDIA_DIR / f"{shortcode}_slide{idx}.jpg"
                    size = download(s_image, dest)
                else:
                    continue
                paths.append(str(dest.relative_to(ROOT)))
                total_size += size
            if paths:
                result["file_size_bytes"] = total_size
                result["downloaded_path"] = ";".join(paths)
                result["status"] = "success"
            else:
                result["status"] = "dead"
                result["error_reason"] = "carousel had no downloadable slide media"
        elif video_url:
            dest = MEDIA_DIR / f"{shortcode}.mp4"
            size = download(video_url, dest)
            result["file_size_bytes"] = size
            result["downloaded_path"] = str(dest.relative_to(ROOT))
            result["status"] = "success"
        elif cover_url:
            dest = MEDIA_DIR / f"{shortcode}.jpg"
            size = download(cover_url, dest)
            result["file_size_bytes"] = size
            result["downloaded_path"] = str(dest.relative_to(ROOT))
            result["status"] = "success"
        else:
            result["status"] = "dead"
            result["error_reason"] = "no video/cover/slides url in dataset row"
    except Exception as e:
        result["status"] = "error"
        result["error_reason"] = f"download failed: {e}"[:300]

    result["wall_time_sec"] = round(time.time() - t0, 2)
    return result


def main():
    token = os.environ["APIFY_TOKEN"]
    client = ApifyClient(token)

    sample = [json.loads(line) for line in SAMPLE.read_text().splitlines()]
    print(f"loaded {len(sample)} sample items")

    raw_rows = load_raw_rows()
    results = load_results()

    total_cost = sum(r.get("cost_usd") or 0.0 for r in results.values())
    print(f"apify spend so far (from results file): ${total_cost:.4f}")

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    raw_f = RAW_OUT.open("a")

    def is_terminal(r: dict | None) -> bool:
        return r is not None and r["status"] in ("success", "dead")

    # Pass 1: reprocess anything with a usable raw row but no terminal
    # result, at zero additional cost.
    reprocessed = 0
    for item in sample:
        sc = item["shortcode"]
        if is_terminal(results.get(sc)):
            continue
        if sc in raw_rows:
            print(f"reprocessing {sc} from stored raw row (no new actor call) ...", flush=True)
            results[sc] = process_dataset_row(sc, raw_rows[sc])
            print(f"    -> {results[sc]['status']} media={results[sc]['media_type']}")
            reprocessed += 1
    print(f"reprocessed {reprocessed} item(s) from existing raw data")

    # Pass 2: fresh actor calls for anything still not terminal -- ONE PER ITEM, not a
    # single `posts: [...]` call with all of them. This account is non-paying and the actor
    # enforces an undocumented 5-billable-event-per-run cap; a single batched call silently
    # truncated to its first item. Cost per item is unchanged; this only costs run-count and
    # per-run startup latency. Full detail: docs/M0_FINDINGS.md §3.
    todo = [item for item in sample if not is_terminal(results.get(item["shortcode"]))]
    print(f"remaining items needing a fresh actor call: {len(todo)}")

    try:
        for i, item in enumerate(todo, 1):
            shortcode = item["shortcode"]
            link = item["link"]

            if total_cost >= APIFY_BUDGET_USD:
                print(
                    f"STOPPING: Apify spend ${total_cost:.3f} has reached "
                    f"the ${APIFY_BUDGET_USD} soft cap. "
                    f"{len(todo) - i + 1} items unfetched."
                )
                break

            print(f"[{i}/{len(todo)}] fetching {shortcode} ...", flush=True)
            run_input = {
                "posts": [link],
                "downloadVideo": True,
                "downloadCover": True,
                "downloadCarouselImages": True,
                "downloadMusic": False,
                "storeFiles": True,
                "maxFileSizeMb": 100,
            }

            result = blank_result(shortcode)
            t0 = time.time()
            try:
                run = client.actor(ACTOR_ID).call(run_input=run_input, logger=None)
            except Exception as e:
                result["error_reason"] = f"actor call failed: {e}"[:300]
                result["wall_time_sec"] = round(time.time() - t0, 2)
                results[shortcode] = result
                continue

            cost = float(run.usage_total_usd or 0.0)
            result["cost_usd"] = cost
            total_cost += cost

            dataset = client.dataset(run.default_dataset_id)
            rows = list(dataset.iterate_items())
            for row in rows:
                raw_f.write(json.dumps({"shortcode": shortcode, **row}, ensure_ascii=False) + "\n")
            raw_f.flush()

            if not rows:
                result["status"] = "error"
                result["error_reason"] = f"empty dataset, run status={run.status}"
                result["wall_time_sec"] = round(time.time() - t0, 2)
                results[shortcode] = result
                continue

            row = rows[0]
            processed = process_dataset_row(shortcode, row)
            processed["cost_usd"] = cost
            processed["wall_time_sec"] = round(time.time() - t0, 2)
            results[shortcode] = processed
            print(
                f"    -> {processed['status']} media={processed['media_type']} "
                f"cost=${cost:.4f} running_total=${total_cost:.3f}"
            )
    finally:
        raw_f.close()
        # Rewrite results file in full so every shortcode appears exactly once.
        with RESULTS_OUT.open("w") as res_f:
            for item in sample:
                sc = item["shortcode"]
                if sc in results:
                    res_f.write(json.dumps(results[sc]) + "\n")

    print(f"TOTAL APIFY SPEND SO FAR: ${total_cost:.3f}")
    done = sum(1 for item in sample if is_terminal(results.get(item["shortcode"])))
    print(f"terminal (success/dead) items: {done}/{len(sample)}")


if __name__ == "__main__":
    main()
