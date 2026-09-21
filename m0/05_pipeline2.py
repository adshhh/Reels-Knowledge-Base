"""M0 step 5 -- Pipeline 2: Gemini gemini-3.5-flash-lite on the whole video/
image, plus caption. No OCR, no transcript, no separate reading step -- the
model watches/reads the raw media itself and is asked for the same JSON
schema pipeline1's fusion step produces.

This exists to be *compared* against pipeline 1, not to replace it. §3 (D7)
says OCR reads and the model interprets, never the reverse; pipeline 2
deliberately breaks that boundary on purpose, so M0 can measure in dollars
and in fabricated-URL count what breaking it costs. See
docs/DESIGN_RATIONALE.md #10 for why the free tier is acceptable here
(content judged non-sensitive by the owner) and docs/CONTRACT.md "What
leaves this machine" for the disclosure this script is entry for: whole
video/image bytes go to Google, not just text.

Media: whichever files Apify fetched (see data/m0/apify_results.jsonl),
matching pipeline1's precedence. Video items send the video file; carousel
items send every slide *image* (mp4 slides skipped, same documented
simplification as pipeline1, for parity between the two pipelines' inputs).

Uses the Gemini File API (client.files.upload) rather than inline base64,
because several sample videos (up to ~16.7 MB) would push an inline request
close to Gemini's ~20MB request-size ceiling once base64-encoded -- the File
API has no such problem and is the documented path for video anyway.

Free tier: no per-call dollar cost, but usage_metadata token counts are
recorded anyway (in case a paid-tier estimate is ever wanted), and calls are
paced with a fixed delay plus retry-with-backoff on 429 to respect the free
tier's per-minute rate limit, which is the real constraint on this stage.

Resumable at the row level (skips shortcodes already in pipeline2.jsonl).

Writes:
  data/m0/extract/<shortcode>/pipeline2.json  -- raw Gemini output + timing
  data/m0/pipeline2.jsonl                     -- one aggregate row per item
"""

import json
import os
import time
from pathlib import Path

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "m0" / "sample.jsonl"
APIFY_RESULTS = ROOT / "data" / "m0" / "apify_results.jsonl"
MEDIA_DIR = ROOT / "data" / "m0" / "media"
EXTRACT_DIR = ROOT / "data" / "m0" / "extract"
OUT = ROOT / "data" / "m0" / "pipeline2.jsonl"

GEMINI_MODEL = "gemini-3.5-flash-lite"

# --- pacing / retry (free-tier rate limit is the real constraint here) ---
INTER_CALL_DELAY_SEC = 4.0
MAX_RETRIES = 4
RETRY_BASE_DELAY_SEC = 15.0
UPLOAD_POLL_INTERVAL_SEC = 2.0
UPLOAD_POLL_TIMEOUT_SEC = 90.0

SYSTEM_PROMPT = """You are organising evidence from a saved Instagram reel into a \
structured record. You are given the reel's own video (or its carousel slide \
images) plus the creator's caption. Watch/read the media yourself: read any \
on-screen text and transcribe any speech to find URLs, @handles, and proper-noun \
titles.

Return ONLY a JSON object with this exact shape:
{
  "title": "short descriptive title, <=80 chars",
  "summary": "one sentence summary",
  "bullets": ["3 to 5 short content bullets"],
  "entities": {
    "urls": ["any URLs visible on screen or spoken"],
    "handles": ["any @handles visible on screen or spoken"],
    "titles": ["any proper-noun titles: film/course/book/product names"]
  }
}"""


def media_paths_for(shortcode: str, media_type: str) -> list[Path]:
    if media_type == "video":
        p = MEDIA_DIR / f"{shortcode}.mp4"
        return [p] if p.exists() else []
    if media_type == "carousel":
        # Images only -- mp4 slides skipped, same simplification as pipeline1,
        # kept so both pipelines see the same input.
        return sorted(MEDIA_DIR.glob(f"{shortcode}_slide*.jpg"))
    if media_type == "image":
        p = MEDIA_DIR / f"{shortcode}.jpg"
        return [p] if p.exists() else []
    return []


def already_done() -> set[str]:
    if not OUT.exists():
        return set()
    return {json.loads(line)["shortcode"] for line in OUT.read_text().splitlines() if line.strip()}


def upload_and_wait(client: genai.Client, path: Path) -> types.File:
    f = client.files.upload(file=str(path))
    t0 = time.time()
    while f.state == types.FileState.PROCESSING:
        if time.time() - t0 > UPLOAD_POLL_TIMEOUT_SEC:
            raise TimeoutError(
                f"file {path.name} still PROCESSING after {UPLOAD_POLL_TIMEOUT_SEC}s"
            )
        time.sleep(UPLOAD_POLL_INTERVAL_SEC)
        f = client.files.get(name=f.name)
    if f.state != types.FileState.ACTIVE:
        raise RuntimeError(f"file {path.name} ended in state {f.state}: {f.error}")
    return f


def generate_with_retry(
    client: genai.Client, contents: list
) -> tuple[dict | None, str | None, dict, float]:
    delay = RETRY_BASE_DELAY_SEC
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        t0 = time.time()
        try:
            resp = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.2,
                ),
            )
            usage = {}
            if resp.usage_metadata:
                usage = {
                    "prompt_tokens": resp.usage_metadata.prompt_token_count,
                    "output_tokens": resp.usage_metadata.candidates_token_count,
                    "total_tokens": resp.usage_metadata.total_token_count,
                }
            parsed = json.loads(resp.text)
            return parsed, None, usage, round(time.time() - t0, 2)
        except json.JSONDecodeError as e:
            return (
                None,
                f"json decode error: {e}; raw={resp.text[:300]!r}",
                {},
                round(time.time() - t0, 2),
            )
        except Exception as e:
            last_err = str(e)[:300]
            is_rate_limit = "429" in last_err or "RESOURCE_EXHAUSTED" in last_err
            if attempt < MAX_RETRIES and is_rate_limit:
                print(
                    f"    rate-limited (attempt {attempt}/{MAX_RETRIES}), sleeping {delay:.0f}s ..."
                )
                time.sleep(delay)
                delay *= 2
                continue
            return None, last_err, {}, round(time.time() - t0, 2)
    return None, last_err, {}, 0.0


def main():
    sample = [json.loads(line) for line in SAMPLE.read_text().splitlines()]
    apify_results = {
        json.loads(line)["shortcode"]: json.loads(line)
        for line in APIFY_RESULTS.read_text().splitlines()
        if line.strip()
    }

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    done = already_done()
    todo = [item for item in sample if item["shortcode"] not in done]
    print(f"pipeline2: {len(done)} already done, {len(todo)} remaining")

    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    with OUT.open("a") as out_f:
        for i, item in enumerate(todo, 1):
            sc = item["shortcode"]
            caption = item["caption"]
            ar = apify_results.get(sc, {})
            media_type = ar.get("media_type", "unknown")
            print(f"[{i}/{len(todo)}] {sc} media_type={media_type} ...", flush=True)

            row = {
                "shortcode": sc,
                "media_type": media_type,
                "gemini_output": None,
                "gemini_error": None,
                "n_files_uploaded": 0,
                "usage": {},
                "timings_sec": {},
            }
            t_start = time.time()

            try:
                paths = media_paths_for(sc, media_type)
                if not paths:
                    row["gemini_error"] = f"no usable media (media_type={media_type})"
                else:
                    t0 = time.time()
                    uploaded = [upload_and_wait(client, p) for p in paths]
                    row["timings_sec"]["upload"] = round(time.time() - t0, 2)
                    row["n_files_uploaded"] = len(uploaded)

                    user_text = f"CAPTION:\n{caption or '(empty)'}"
                    contents = [*uploaded, user_text]

                    output, err, usage, gen_t = generate_with_retry(client, contents)
                    row["gemini_output"] = output
                    row["gemini_error"] = err
                    row["usage"] = usage
                    row["timings_sec"]["generate"] = gen_t

                    # Delete the uploaded copy from Google's side -- no reason
                    # to leave personal media sitting in a vendor's file store
                    # longer than the single call that needed it.
                    for f in uploaded:
                        try:
                            client.files.delete(name=f.name)
                        except Exception:
                            pass

                item_dir = EXTRACT_DIR / sc
                item_dir.mkdir(parents=True, exist_ok=True)
                (item_dir / "pipeline2.json").write_text(
                    json.dumps(row, ensure_ascii=False, indent=2)
                )

            except Exception as e:
                row["gemini_error"] = f"pipeline2 exception: {e}"[:400]

            row["timings_sec"]["total"] = round(time.time() - t_start, 2)
            out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            out_f.flush()
            print(
                f"    -> files={row['n_files_uploaded']} "
                f"ok={row['gemini_output'] is not None} "
                f"err={row['gemini_error']} "
                f"total={row['timings_sec'].get('total')}s"
            )

            if i < len(todo):
                time.sleep(INTER_CALL_DELAY_SEC)

    print("pipeline2 done")


if __name__ == "__main__":
    main()
