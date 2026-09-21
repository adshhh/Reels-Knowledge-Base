"""M0 step 4 -- Pipeline 1: local OCR + VAD-gated Whisper + Groq fusion.

For each of the 50 sample items (using whichever media Fetch A/B retrieved,
preferring Apify's copy):

  Video items:
    ffmpeg scene-change frame sampling (top 5-8 scene frames + frame 0 +
    a fixed-interval floor for single-shot reels, deduped) -> Apple Vision
    OCR (ocrmac, recognition_level='accurate', per-string confidence kept)
    -> audio extracted -> Silero VAD -> only if speech: Groq
    whisper-large-v3-turbo -> Groq gpt-oss-120b fusion over
    caption + OCR text + transcript.

  Carousel/image items (all /p/ posts in this sample came back as
  carousels -- see data/m0/apify_results.jsonl): OCR every slide image,
  no audio stage, same fusion call minus the transcript.

Frame sampling method (DECIDED, documented here because §3 leaves the exact
algorithm unspecified beyond "scene-change ... top 5-8 ... frame 0 ... fixed
interval floor ... deduped"):
  1. `ffmpeg -vf "select='gte(scene,0.08)',metadata=print" -f null -` prints
     each selected frame's pts_time and lavfi.scene_score to stderr. Parsed
     and sorted by score descending; top SCENE_FRAMES_MAX kept.
  2. Frame 0 (t=0.0) is always added (the hook-text frame).
  3. Floor: if fewer than FLOOR_MIN_FRAMES scene-change frames were found
     (typical of a single continuous shot), fixed-interval frames are added
     at duration/(FLOOR_COUNT+1) spacing.
  4. Dedup: sorted by timestamp, any candidate within DEDUP_WINDOW_SEC of an
     already-kept timestamp is dropped.
  5. Each surviving timestamp is extracted as its own JPEG via a seeked
     single-frame ffmpeg call (simple and robust for reel-length video;
     not the fastest way, doesn't need to be for 50 items).

Unreadable-on-screen-text heuristic (DOCUMENTED, no ground truth available):
Apple Vision's `recognize()` returns every candidate string down to
confidence 0.0 (we pass confidence_threshold=0.0 deliberately, see below).
A frame is counted as "text present but unreadable" when it has at least
one OCR candidate whose confidence is below UNREADABLE_CONF_THRESHOLD --
i.e. Vision found and attempted a text region but was not confident in the
transcription. This is a heuristic, not a ground-truth judgement; the M0
findings report the count under that caveat.

Sung-vocal / lyric-like transcript heuristic (DOCUMENTED): a transcript is
flagged "lyric-like" when it contains a repeated phrase of
LYRIC_NGRAM_WORDS+ words appearing LYRIC_MIN_REPEATS+ times (chorus-style
repetition), or when >LYRIC_FILLER_RATIO of its words are sung filler
tokens (la, na, ooh, yeah, oh, mmm, ...). No audio classifier is used; this
is a cheap text-only proxy and is reported as such.

"Blank" bucket (DOCUMENTED): no VAD speech AND zero OCR strings survive
BLANK_OCR_MIN_LEN AND the caption, with hashtags stripped, is shorter than
BLANK_CAPTION_MIN_CHARS -- deliberately the same "uninformative caption"
threshold `01_sample.py` already uses for hashtag-heavy detection.

Writes (all gitignored, under data/m0/):
  extract/<shortcode>/frames/*.jpg      -- sampled frames (video only). Carousel
                                            items are OCR'd and referenced directly
                                            from media/<shortcode>_slideN.jpg instead
                                            of being copied -- both are kept on disk
                                            for the judge.html page either way
  extract/<shortcode>/audio.wav         -- extracted mono 16kHz audio (video only,
                                            deleted immediately after VAD+Whisper to
                                            save disk -- never persisted)
  pipeline1.jsonl                       -- one aggregate row per item (see RowP1):
                                            ocr_verbatim, transcript, fusion and
                                            everything else live ONLY here, not as
                                            separate per-item ocr.json/fusion.json/
                                            transcript.txt files (an earlier version
                                            of this docstring promised those; nothing
                                            downstream needs them since the aggregate
                                            row already has every field)
"""

import json
import os
import re
import subprocess
import time
import wave
from collections import Counter
from pathlib import Path

from groq import Groq

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "m0" / "sample.jsonl"
APIFY_RESULTS = ROOT / "data" / "m0" / "apify_results.jsonl"
MEDIA_DIR = ROOT / "data" / "m0" / "media"
EXTRACT_DIR = ROOT / "data" / "m0" / "extract"
OUT = ROOT / "data" / "m0" / "pipeline1.jsonl"

FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"

# --- frame sampling ---
SCENE_THRESHOLD = 0.08
SCENE_FRAMES_MAX = 8
FLOOR_MIN_FRAMES = 4
FLOOR_COUNT = 5
DEDUP_WINDOW_SEC = 1.0

# --- OCR ---
UNREADABLE_CONF_THRESHOLD = 0.5
BLANK_OCR_MIN_LEN = 2  # OCR strings shorter than this don't count as "text"

# --- lyric-like heuristic ---
LYRIC_NGRAM_WORDS = 3
LYRIC_MIN_REPEATS = 3
LYRIC_FILLER_WORDS = {
    "la",
    "na",
    "ooh",
    "oh",
    "ohh",
    "yeah",
    "mmm",
    "hmm",
    "woah",
    "whoa",
    "hey",
    "ay",
    "uh",
    "da",
    "doo",
    "ra",
}
LYRIC_FILLER_RATIO = 0.35

# --- blank bucket ---
BLANK_CAPTION_MIN_CHARS = 15

GROQ_WHISPER_MODEL = "whisper-large-v3-turbo"
GROQ_FUSION_MODEL = "openai/gpt-oss-120b"

FUSION_SYSTEM_PROMPT = """You are organising evidence extracted from a saved Instagram \
reel into a structured record. You are given three independent, already-extracted \
channels: the creator's caption, verbatim on-screen text read by OCR, and a speech \
transcript. Some channels may be empty.

Your job is to interpret and summarise, never to invent. Every URL, @handle, or \
proper-noun title you output MUST be copied verbatim from the OCR text or transcript \
provided -- never guess or complete a URL/handle you were not given in full. If you are \
not sure a URL/handle is complete and correct as given, omit it.

Return ONLY a JSON object with this exact shape:
{
  "title": "short descriptive title, <=80 chars",
  "summary": "one sentence summary",
  "bullets": ["3 to 5 short content bullets"],
  "entities": {
    "urls": ["any URLs present verbatim in OCR or transcript"],
    "handles": ["any @handles present verbatim in OCR or transcript"],
    "titles": ["any proper-noun titles: film/course/book/product names"]
  }
}"""


def run_capture(cmd: list[str]) -> tuple[str, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.stdout, p.stderr


def ffprobe_duration(path: Path) -> float:
    out, _ = run_capture(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


SHOWINFO_RE = re.compile(r"pts_time:([\d.]+)")
SCENE_SCORE_RE = re.compile(r"lavfi\.scene_score=([\d.]+)")


def scene_change_candidates(video_path: Path, duration: float) -> list[float]:
    """Returns timestamps of the top scene-change frames, by score."""
    _, stderr = run_capture(
        [
            FFMPEG,
            "-i",
            str(video_path),
            "-vf",
            f"select='gte(scene,{SCENE_THRESHOLD})',metadata=print",
            "-vsync",
            "vfr",
            "-f",
            "null",
            "-",
        ]
    )
    pts_times = SHOWINFO_RE.findall(stderr)
    scores = SCENE_SCORE_RE.findall(stderr)
    pairs = []
    for t, s in zip(pts_times, scores, strict=False):
        try:
            pairs.append((float(t), float(s)))
        except ValueError:
            continue
    pairs.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in pairs[:SCENE_FRAMES_MAX]]


def sample_frame_timestamps(video_path: Path, duration: float) -> list[float]:
    scene_ts = scene_change_candidates(video_path, duration)
    candidates = [0.0] + scene_ts
    if len(scene_ts) < FLOOR_MIN_FRAMES and duration > 0:
        step = duration / (FLOOR_COUNT + 1)
        candidates += [round(step * i, 2) for i in range(1, FLOOR_COUNT + 1)]
    candidates = sorted(set(round(c, 2) for c in candidates if c >= 0))
    kept: list[float] = []
    for c in candidates:
        if all(abs(c - k) >= DEDUP_WINDOW_SEC for k in kept):
            kept.append(c)
    return kept


def extract_frame(video_path: Path, ts: float, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _, stderr = run_capture(
        [
            FFMPEG,
            "-y",
            "-ss",
            f"{ts:.2f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(dest),
        ]
    )
    return dest.exists() and dest.stat().st_size > 0


def ocr_image(path: Path) -> list[dict]:
    from ocrmac import ocrmac

    results = ocrmac.OCR(
        str(path), recognition_level="accurate", confidence_threshold=0.0
    ).recognize()
    return [{"text": text, "confidence": round(float(conf), 4)} for text, conf, _bbox in results]


def extract_audio(video_path: Path, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    _, stderr = run_capture(
        [
            FFMPEG,
            "-y",
            "-i",
            str(video_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-vn",
            str(dest),
        ]
    )
    return dest.exists() and dest.stat().st_size > 0


def wav_duration_sec(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def read_wav_mono16k(path: Path):
    """Read the mono/16kHz PCM16 WAV that extract_audio() produces, as a
    float32 torch tensor in [-1, 1] -- the shape silero_vad wants.

    BUG WORKED AROUND (found running this script, 2026-09-19): silero_vad's
    own `read_audio()` calls torchaudio, and the installed torchaudio 2.9.1
    refuses to load audio without the separate `torchcodec` package
    ("torchaudio version 2.9.1 requires torchcodec for audio I/O"). No `pip
    install` is allowed mid-M0, so this reads the WAV directly with the
    stdlib `wave` module instead of going anywhere near torchaudio. Confirmed
    this was silently swallowing every video item's VAD+Whisper+fusion step
    (caught by the broad `except Exception` around the per-item body) --
    9 of the first 12 rows in pipeline1.jsonl have fusion_error set to this
    exact torchaudio message and fusion=None. Those 9 rows are deleted and
    reprocessed after this fix.
    """
    import numpy as np
    import torch

    with wave.open(str(path), "rb") as w:
        if w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise ValueError(
                f"expected mono 16-bit PCM wav, got channels={w.getnchannels()} "
                f"sampwidth={w.getsampwidth()}"
            )
        raw = w.readframes(w.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    return torch.from_numpy(samples)


def vad_speech(wav_path: Path, vad_model) -> tuple[bool, float]:
    from silero_vad import get_speech_timestamps

    audio = read_wav_mono16k(wav_path)
    timestamps = get_speech_timestamps(audio, vad_model, sampling_rate=16000)
    total_speech = sum((t["end"] - t["start"]) / 16000 for t in timestamps)
    return (len(timestamps) > 0, round(total_speech, 2))


def whisper_transcribe(client: Groq, wav_path: Path) -> tuple[str, float]:
    t0 = time.time()
    with wav_path.open("rb") as f:
        resp = client.audio.transcriptions.create(
            file=(wav_path.name, f.read()),
            model=GROQ_WHISPER_MODEL,
            response_format="text",
        )
    text = resp if isinstance(resp, str) else getattr(resp, "text", str(resp))
    return text.strip(), round(time.time() - t0, 2)


def fusion_call(
    client: Groq, caption: str, ocr_text: str, transcript: str
) -> tuple[dict | None, str | None, float]:
    user_content = (
        f"CAPTION:\n{caption or '(empty)'}\n\n"
        f"ON-SCREEN TEXT (OCR, may contain noise):\n{ocr_text or '(none)'}\n\n"
        f"SPEECH TRANSCRIPT:\n{transcript or '(none)'}"
    )
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=GROQ_FUSION_MODEL,
            messages=[
                {"role": "system", "content": FUSION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = resp.choices[0].message.content
        return json.loads(raw), None, round(time.time() - t0, 2)
    except Exception as e:
        return None, str(e)[:300], round(time.time() - t0, 2)


def is_lyric_like(transcript: str) -> bool:
    words = re.findall(r"[a-zA-Z']+", transcript.lower())
    if len(words) < 6:
        return False
    filler_ratio = sum(1 for w in words if w in LYRIC_FILLER_WORDS) / len(words)
    if filler_ratio >= LYRIC_FILLER_RATIO:
        return True
    ngrams = Counter(
        tuple(words[i : i + LYRIC_NGRAM_WORDS]) for i in range(len(words) - LYRIC_NGRAM_WORDS + 1)
    )
    return any(c >= LYRIC_MIN_REPEATS for c in ngrams.values())


def caption_uninformative(caption: str) -> bool:
    stripped = re.sub(r"#\S+", "", caption or "").strip()
    return len(stripped) < BLANK_CAPTION_MIN_CHARS


def media_paths_for(shortcode: str, media_type: str) -> list[Path]:
    if media_type == "video":
        p = MEDIA_DIR / f"{shortcode}.mp4"
        return [p] if p.exists() else []
    if media_type == "carousel":
        return sorted(MEDIA_DIR.glob(f"{shortcode}_slide*.jpg")) + sorted(
            MEDIA_DIR.glob(f"{shortcode}_slide*.mp4")
        )
    if media_type == "image":
        p = MEDIA_DIR / f"{shortcode}.jpg"
        return [p] if p.exists() else []
    return []


def already_done() -> set[str]:
    if not OUT.exists():
        return set()
    return {json.loads(line)["shortcode"] for line in OUT.read_text().splitlines() if line.strip()}


def main():
    sample = [json.loads(line) for line in SAMPLE.read_text().splitlines()]
    apify_results = {
        json.loads(line)["shortcode"]: json.loads(line)
        for line in APIFY_RESULTS.read_text().splitlines()
        if line.strip()
    }

    groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

    print("loading Silero VAD model ...")
    from silero_vad import load_silero_vad

    vad_model = load_silero_vad()

    done = already_done()
    todo = [item for item in sample if item["shortcode"] not in done]
    print(f"pipeline1: {len(done)} already done, {len(todo)} remaining")

    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)

    with OUT.open("a") as out_f:
        for i, item in enumerate(todo, 1):
            sc = item["shortcode"]
            caption = item["caption"]
            ar = apify_results.get(sc, {})
            media_type = ar.get("media_type", "unknown")
            print(f"[{i}/{len(todo)}] {sc} media_type={media_type} ...", flush=True)

            item_dir = EXTRACT_DIR / sc
            frames_dir = item_dir / "frames"
            row = {
                "shortcode": sc,
                "media_type": media_type,
                "ocr_verbatim": [],
                "unreadable_frame_count": 0,
                "n_frames_sampled": 0,
                "vad_speech": False,
                "speech_duration_sec": 0.0,
                "transcript": "",
                "lyric_like": False,
                "fusion": None,
                "fusion_error": None,
                "caption_uninformative": caption_uninformative(caption),
                "blank_bucket": False,
                "timings_sec": {},
                "sampled_frame_paths": [],
            }

            t_start = time.time()

            try:
                if media_type == "video":
                    video_path = MEDIA_DIR / f"{sc}.mp4"
                    if not video_path.exists():
                        raise FileNotFoundError(f"no video at {video_path}")
                    duration = ffprobe_duration(video_path)
                    t0 = time.time()
                    timestamps = sample_frame_timestamps(video_path, duration)
                    frame_paths = []
                    for j, ts in enumerate(timestamps):
                        dest = frames_dir / f"frame_{j:02d}_t{ts:.2f}.jpg"
                        if extract_frame(video_path, ts, dest):
                            frame_paths.append((ts, dest))
                    row["timings_sec"]["frame_sampling"] = round(time.time() - t0, 2)
                    row["n_frames_sampled"] = len(frame_paths)
                    row["sampled_frame_paths"] = [str(p.relative_to(ROOT)) for _, p in frame_paths]

                    t0 = time.time()
                    ocr_rows = []
                    unreadable = 0
                    for ts, fp in frame_paths:
                        for r in ocr_image(fp):
                            r["frame_ts"] = ts
                            ocr_rows.append(r)
                            if 0 < r["confidence"] < UNREADABLE_CONF_THRESHOLD:
                                unreadable += 1
                    row["timings_sec"]["ocr"] = round(time.time() - t0, 2)
                    row["ocr_verbatim"] = ocr_rows
                    row["unreadable_frame_count"] = unreadable

                    t0 = time.time()
                    audio_path = item_dir / "audio.wav"
                    has_audio = extract_audio(video_path, audio_path)
                    row["timings_sec"]["audio_extract"] = round(time.time() - t0, 2)

                    if has_audio and wav_duration_sec(audio_path) > 0.3:
                        t0 = time.time()
                        speech, speech_dur = vad_speech(audio_path, vad_model)
                        row["timings_sec"]["vad"] = round(time.time() - t0, 2)
                        row["vad_speech"] = speech
                        row["speech_duration_sec"] = speech_dur
                        if speech:
                            transcript, whisper_t = whisper_transcribe(groq_client, audio_path)
                            row["transcript"] = transcript
                            row["timings_sec"]["whisper"] = whisper_t
                            row["lyric_like"] = is_lyric_like(transcript)
                    if audio_path.exists():
                        audio_path.unlink()  # keep disk small; VAD/Whisper already ran

                elif media_type in ("carousel", "image"):
                    paths = media_paths_for(sc, media_type)
                    t0 = time.time()
                    ocr_rows = []
                    unreadable = 0
                    kept_frames = []
                    for p in paths:
                        if p.suffix.lower() == ".mp4":
                            # a video slide inside a carousel: OCR-only scope
                            # skips it (documented simplification)
                            continue
                        for r in ocr_image(p):
                            r["frame_ts"] = None
                            r["source_file"] = p.name
                            ocr_rows.append(r)
                            if 0 < r["confidence"] < UNREADABLE_CONF_THRESHOLD:
                                unreadable += 1
                        kept_frames.append(p)
                    row["timings_sec"]["ocr"] = round(time.time() - t0, 2)
                    row["ocr_verbatim"] = ocr_rows
                    row["unreadable_frame_count"] = unreadable
                    row["n_frames_sampled"] = len(kept_frames)
                    row["sampled_frame_paths"] = [str(p.relative_to(ROOT)) for p in kept_frames]
                    # no audio channel for image/carousel posts

                else:
                    row["fusion_error"] = f"no usable media (media_type={media_type})"

                ocr_text_joined = "\n".join(
                    r["text"] for r in row["ocr_verbatim"] if len(r["text"]) >= BLANK_OCR_MIN_LEN
                )
                row["blank_bucket"] = (
                    not row["vad_speech"]
                    and not ocr_text_joined.strip()
                    and row["caption_uninformative"]
                )

                if media_type in ("video", "carousel", "image"):
                    fusion, err, fusion_t = fusion_call(
                        groq_client, caption, ocr_text_joined, row["transcript"]
                    )
                    row["fusion"] = fusion
                    row["fusion_error"] = err
                    row["timings_sec"]["fusion"] = fusion_t

            except Exception as e:
                row["fusion_error"] = f"pipeline1 exception: {e}"[:400]

            row["timings_sec"]["total"] = round(time.time() - t_start, 2)
            out_f.write(json.dumps(row, ensure_ascii=False) + "\n")
            out_f.flush()
            print(
                f"    -> frames={row['n_frames_sampled']} "
                f"ocr_strings={len(row['ocr_verbatim'])} "
                f"speech={row['vad_speech']} "
                f"fusion_ok={row['fusion'] is not None} "
                f"total={row['timings_sec'].get('total')}s"
            )

    print("pipeline1 done")


if __name__ == "__main__":
    main()
