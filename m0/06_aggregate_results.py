"""M0 step 6 -- aggregate pipeline1 (local OCR+VAD+Whisper+Groq fusion) and
pipeline2 (Gemini watches raw video/images) into one per-item results file,
plus the automatic URL/handle/title fidelity check against OCR that the
owner's manual judging (judge.html) doesn't need to redo.

This does NOT compute corpus-wide projections (full-run cost, disk, time) --
those are printed to stdout at the end for whoever writes
docs/M0_FINDINGS.md to copy in as aggregates, since results.jsonl is one row
per item, not a summary.

Fidelity check (§3 AC-3.1's rule, applied here as a measurement, not a
gate): a URL/@handle/title from a pipeline's output is counted as
"grounded" if it is within edit distance 2 of at least one OCR string from
that same item's pipeline1 OCR pass. This is checked identically for both
pipelines' outputs against the SAME OCR text (pipeline1's), because OCR is
the one channel we trust as ground truth (D7) regardless of which pipeline
produced the claim. Titles are checked too but are expected to fail more
often than URLs/handles even for a correct answer, since a film or course
title legitimately can appear only in speech or in the video's visuals
without ever being written on screen -- that's the whole reason pipeline 2
exists to be compared. Read the counts with that caveat, not as a raw pass
rate.

Writes:
  data/m0/results.jsonl -- one row per item (see build_row())
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "m0" / "sample.jsonl"
APIFY_RESULTS = ROOT / "data" / "m0" / "apify_results.jsonl"
YTDLP_RESULTS = ROOT / "data" / "m0" / "ytdlp_results.jsonl"
PIPELINE1 = ROOT / "data" / "m0" / "pipeline1.jsonl"
PIPELINE2 = ROOT / "data" / "m0" / "pipeline2.jsonl"
OUT = ROOT / "data" / "m0" / "results.jsonl"


def levenshtein(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def grounded_in_ocr(candidate: str, ocr_strings: list[str], max_ed: int = 2) -> bool:
    """True if `candidate` is within edit distance `max_ed` of some OCR
    string, OR of some contiguous substring of an OCR string close to its
    own length (so a short candidate isn't unfairly compared against a long
    unrelated OCR line). Cheap and approximate, documented as such."""
    if not candidate:
        return False
    cand = candidate.strip()
    for s in ocr_strings:
        s = s.strip()
        if not s:
            continue
        if levenshtein(cand, s) <= max_ed:
            return True
        # slide a same-length window across longer OCR strings
        if len(s) > len(cand) + max_ed:
            for start in range(0, len(s) - len(cand) + 1):
                window = s[start : start + len(cand)]
                if levenshtein(cand, window) <= max_ed:
                    return True
    return False


def load_jsonl(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[row["shortcode"]] = row
    return out


def entity_fidelity(entities: dict, ocr_strings: list[str], transcript: str) -> dict:
    """Two fidelity flags per entity, not one, because they measure different
    things:

    - grounded_in_ocr: matches §3 AC-3.1's literal text ("must appear in
      that reel's OCR output"), OCR only. This is the eventual production
      gate's actual, stricter standard.
    - grounded_in_ocr_or_transcript: also accepts a match against the
      speech transcript. This is the fairer "was this fabricated at all"
      measure for THIS M0 test specifically, because 04_pipeline1.py's own
      fusion prompt explicitly allows the model to copy entities from
      either the OCR text OR the transcript -- so an entity sourced from
      speech (e.g. a film title said aloud but never shown on screen) will
      correctly fail the strict OCR-only check while not being a
      fabrication. Report both; don't collapse them into one number.
    """
    transcript_strings = [transcript] if transcript else []
    result = {}
    for kind in ("urls", "handles", "titles"):
        items = entities.get(kind) or []
        result[kind] = [
            {
                "value": v,
                "grounded_in_ocr": grounded_in_ocr(v, ocr_strings),
                "grounded_in_ocr_or_transcript": grounded_in_ocr(
                    v, ocr_strings + transcript_strings
                ),
            }
            for v in items
        ]
    return result


def build_row(sc: str, sample: dict, apify: dict, ytdlp: dict, p1: dict, p2: dict) -> dict:
    ocr_strings = [x["text"] for x in (p1.get("ocr_verbatim") or [])]
    transcript = p1.get("transcript") or ""
    p1_entities = (p1.get("fusion") or {}).get("entities", {}) if p1.get("fusion") else {}
    p2_entities = (
        (p2.get("gemini_output") or {}).get("entities", {}) if p2.get("gemini_output") else {}
    )

    return {
        "shortcode": sc,
        "kind": sample.get("kind"),
        "sample_reason": sample.get("sample_reason"),
        "apify_status": apify.get("status"),
        "apify_media_type": apify.get("media_type"),
        "apify_file_size_bytes": apify.get("file_size_bytes"),
        "apify_duration_sec": apify.get("duration_sec"),
        "apify_cost_usd": apify.get("cost_usd"),
        "ytdlp_status": ytdlp.get("status"),
        "ytdlp_error_class": ytdlp.get("error_class"),
        "n_frames_sampled": p1.get("n_frames_sampled"),
        "unreadable_frame_count": p1.get("unreadable_frame_count"),
        "vad_speech": p1.get("vad_speech"),
        "speech_duration_sec": p1.get("speech_duration_sec"),
        "lyric_like": p1.get("lyric_like"),
        "caption_uninformative": p1.get("caption_uninformative"),
        "blank_bucket": p1.get("blank_bucket"),
        "pipeline1_fusion_ok": p1.get("fusion") is not None,
        "pipeline1_fusion_error": p1.get("fusion_error"),
        "pipeline1_timings_sec": p1.get("timings_sec"),
        "pipeline1_fidelity": entity_fidelity(p1_entities, ocr_strings, transcript),
        "pipeline2_ok": p2.get("gemini_output") is not None,
        "pipeline2_error": p2.get("gemini_error"),
        "pipeline2_timings_sec": p2.get("timings_sec"),
        "pipeline2_usage": p2.get("usage"),
        "pipeline2_n_files_uploaded": p2.get("n_files_uploaded"),
        "pipeline2_fidelity": entity_fidelity(p2_entities, ocr_strings, transcript),
    }


def main():
    sample_rows = {
        json.loads(line)["shortcode"]: json.loads(line) for line in SAMPLE.read_text().splitlines()
    }
    apify = load_jsonl(APIFY_RESULTS)
    ytdlp = load_jsonl(YTDLP_RESULTS)
    p1 = load_jsonl(PIPELINE1)
    p2 = load_jsonl(PIPELINE2)

    rows = []
    for sc, sample in sample_rows.items():
        rows.append(
            build_row(
                sc, sample, apify.get(sc, {}), ytdlp.get(sc, {}), p1.get(sc, {}), p2.get(sc, {})
            )
        )

    with OUT.open("w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows to {OUT}")

    # ---- quick aggregate printout for M0_FINDINGS.md ----
    n = len(rows)
    apify_success = sum(1 for r in rows if r["apify_status"] == "success")
    ytdlp_success = sum(1 for r in rows if r["ytdlp_status"] == "success")
    vad_speech_n = sum(1 for r in rows if r["vad_speech"])
    lyric_n = sum(1 for r in rows if r["lyric_like"])
    blank_n = sum(1 for r in rows if r["blank_bucket"])
    unreadable_items = sum(1 for r in rows if (r["unreadable_frame_count"] or 0) > 0)
    unreadable_total = sum(r["unreadable_frame_count"] or 0 for r in rows)
    p1_ok = sum(1 for r in rows if r["pipeline1_fusion_ok"])
    p2_ok = sum(1 for r in rows if r["pipeline2_ok"])

    def fidelity_rate(field: str, kind: str, key: str = "grounded_in_ocr") -> tuple[int, int]:
        total = grounded = 0
        for r in rows:
            for e in r[field][kind]:
                total += 1
                grounded += e[key]
        return grounded, total

    sizes = [r["apify_file_size_bytes"] for r in rows if r["apify_file_size_bytes"]]
    durations = [r["apify_duration_sec"] for r in rows if r["apify_duration_sec"]]

    print("\n--- aggregate summary (for docs/M0_FINDINGS.md) ---")
    print(f"n items: {n}")
    print(f"apify success: {apify_success}/{n} ({apify_success / n:.0%})")
    print(f"ytdlp success: {ytdlp_success}/{n} ({ytdlp_success / n:.0%})")
    print(f"pipeline1 fusion ok: {p1_ok}/{n}")
    print(f"pipeline2 ok: {p2_ok}/{n}")
    print(f"VAD speech detected: {vad_speech_n}/{n}")
    print(f"lyric-like transcripts: {lyric_n}/{vad_speech_n if vad_speech_n else 1}")
    print(f"blank bucket: {blank_n}/{n}")
    print(
        f"unreadable-text items: {unreadable_items}/{n}, "
        f"total unreadable strings: {unreadable_total}"
    )
    print("\nfidelity vs OCR only (strict, matches the literal §3 AC-3.1 gate):")
    for kind in ("urls", "handles", "titles"):
        g1, t1 = fidelity_rate("pipeline1_fidelity", kind)
        g2, t2 = fidelity_rate("pipeline2_fidelity", kind)
        print(
            f"  {kind}: pipeline1 {g1}/{t1}"
            f"{f' ({g1 / t1:.0%})' if t1 else ''}, "
            f"pipeline2 {g2}/{t2}{f' ({g2 / t2:.0%})' if t2 else ''}"
        )
    print("\nfidelity vs OCR-or-transcript (fairer: this is what pipeline1's own fusion")
    print("prompt actually allowed it to cite from):")
    for kind in ("urls", "handles", "titles"):
        g1, t1 = fidelity_rate("pipeline1_fidelity", kind, "grounded_in_ocr_or_transcript")
        g2, t2 = fidelity_rate("pipeline2_fidelity", kind, "grounded_in_ocr_or_transcript")
        print(
            f"  {kind}: pipeline1 {g1}/{t1}"
            f"{f' ({g1 / t1:.0%})' if t1 else ''}, "
            f"pipeline2 {g2}/{t2}{f' ({g2 / t2:.0%})' if t2 else ''}"
        )
    if sizes:
        avg_size = sum(sizes) / len(sizes)
        print(
            f"avg media size: {avg_size / 1e6:.2f} MB over {len(sizes)} items; "
            f"projected for 1870 items (at same survival-adjusted mix): "
            f"{avg_size * 1870 / 1e9:.2f} GB raw media"
        )
    if durations:
        print(f"avg duration: {sum(durations) / len(durations):.1f}s over {len(durations)} items")


if __name__ == "__main__":
    main()
