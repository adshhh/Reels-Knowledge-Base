# M0 Findings — Extraction Bake-off

Aggregates only (counts, %, $, timings, sizes). No captions, URLs, account names or
transcripts appear below — those live only in `data/m0/` (gitignored, local) and in
`data/m0/external_items.md` where relevant (not applicable this round: none of the 50
sampled items were `external`/`note` kind).

**Sample:** 50 items drawn from the 1,870-item export (see `m0/01_sample.py` for the
stratified sampling logic), deliberately weighted toward hard cases: 15 `/p/` posts, 10
hashtag-heavy captions, 15 empty/short captions, 5 Hindi-hint items, the *Flow* canary, and
9 random items. 35 resolved to `reel`/video, 15 to `/p/`.

**How to reproduce every number below:** `m0/02_fetch_apify.py`, `m0/03_fetch_ytdlp.py`,
`m0/04_pipeline1.py`, `m0/05_pipeline2.py`, `m0/06_aggregate_results.py` in that order,
writing to `data/m0/*.jsonl` (all gitignored). `06_aggregate_results.py`'s stdout is the
direct source for every aggregate in this document; `data/m0/results.jsonl` holds the
per-item detail behind it.

---

## 1. Survival: Apify vs yt-dlp

| Fetcher | Success | Rate |
|---|---|---|
| Apify (`memo23/instagram-video-downloader`) | 50/50 | **100%** |
| yt-dlp (logged out, throttled) | 34/50 | 68% |

**Apify's 100% is a real surprise against the plan's 60–80% survival estimate for the full
archive** (§2). This is a 50-item sample, not the full 1,870, and it is not a random
sample — it was deliberately built from *currently resolvable* hard cases, so this number
should not be read as "the full corpus will survive at 100%." Recorded as measured, not
adjusted to fit the plan's expectation.

**yt-dlp's 68% collapses into two very different numbers once split by media type**, which
the flat percentage hides:

| Media type | n | yt-dlp success |
|---|---|---|
| video (`/reel/`) | 35 | 34/35 (97%) |
| carousel (`/p/`) | 15 | 0/15 (**0%**) |

Every carousel failure returned the same yt-dlp error, `"No video formats found!"` — yt-dlp's
Instagram extractor does not handle image carousels at all, only video. This is a hard
limitation, not a rate-limit or login-wall artifact (no run hit the 5-consecutive-failure
early-stop condition; `data/m0/ytdlp_stopped_early.txt` was never written). One video item
also failed ("Instagram sent an empty media response"), plausibly a genuinely dead/private
post independent of yt-dlp itself.

**Implication for D18 (yt-dlp for monthly top-ups):** yt-dlp is a fine top-up path for
`/reel/` items (97% survival here) but **cannot top up `/p/` posts at all**. Since `/p/`
posts are ~8.3% of the full corpus (156/1,870, per AC-2.1), any future top-up batch containing
carousels needs Apify (or another vendor) for those specifically — yt-dlp alone cannot cover
them.

---

## 2. `/p/` media types

All 15 `/p/` posts in the sample came back as **carousels** (multi-slide), none as single
static images. 0 came back as plain single images. This confirms the working assumption
already documented in `m0/04_pipeline1.py`'s docstring, now with a measured n=15 behind it,
not an assumption.

---

## 3. Apify: the 403 cause and the non-paying-account cap

Two real bugs were found and fixed while building the fetch stage (documented in
`m0/02_fetch_apify.py`'s docstring, dated 2026-09-19):

1. **The undocumented per-run billable-event cap.** This Apify account is non-paying
   (`user_is_paying: '0'` in the run's own ACTOR_ENV log), and the actor enforces an
   undocumented cap of **5 billable events per run** for non-paying accounts. A single post
   typically costs 4 billable events (start + dataset-item + video + cover), so submitting
   all 50 items in one call silently truncated to processing only the first item. **Fix:**
   one actor call per item, sequential. This does not change the per-item cost, but it does
   change the *time* and *run-count* — see the full-corpus projection below.
2. **The 403 on downloading re-hosted media.** The actor's `storeFiles: True` option
   re-hosts video/cover files to Apify key-value-store URLs that this non-paying account's
   plain `GET` request receives as `403 Forbidden` — undocumented; the actor's own README
   implies these are public, permanent links. **Fix:** append the Apify API token as a
   `?token=` query parameter. Confirmed directly: the identical URL 403'd without the token
   and returned `200` with the full, correct byte count with it, for both a `videoUrl` and a
   carousel `coverUrl`.

---

## 4. Timing per stage (measured over 50 items)

**Pipeline 1 (local OCR + VAD + Groq Whisper + Groq fusion), wall time:**

| Stage | Total (50 items) | Avg per item | n (items using this stage) |
|---|---|---|---|
| Frame sampling (ffmpeg) | 18.9s | 0.54s | 35 (video only) |
| OCR (Apple Vision, `ocrmac`) | 87.3s | 1.75s | 50 |
| Audio extraction (ffmpeg) | 3.9s | 0.11s | 35 (video only) |
| VAD (Silero) | 5.5s | 0.16s | 34 |
| Whisper (Groq, only when VAD found speech) | 18.6s | 0.75s (of the 25 that ran it) | 25 |
| Fusion (Groq `gpt-oss-120b`) | 304.4s | 6.09s | 50 |
| **Pipeline 1 total** | **441.9s (7.4 min)** | **8.84s/item** | 50 |

Fusion dominates pipeline 1's wall time (69% of it) — it's a network call to Groq, not local
compute.

**Pipeline 2 (Gemini `gemini-3.5-flash-lite` watching raw video/images), wall time:**

| Stage | Total (50 items) |
|---|---|
| File upload (to Gemini's File API) | 455.5s |
| Generate (model call) | 169.3s |
| **Pipeline 2 total** | **694.2s (11.6 min)** |

Pipeline 2 is **57% slower overall than pipeline 1** (694s vs 442s), and unlike pipeline 1
its dominant cost is upload time (66% of its wall time) — carousels with many slide images
upload one file per slide, which adds up (the largest carousel, 14 images, took ~30s just to
upload+process).

**Apify fetch:** avg 8.05s/item across all 50 (includes the ~5–9s per-run actor-start
latency forced by the non-paying-account cap above), split by media type: video 6.34s/item,
carousel 12.04s/item (more files to download per item).

---

## 5. Projected full-corpus cost, time, and disk

**Disk.** Average media size measured: **4.67 MB/item** (n=50). Projected across the full
1,870-item corpus at the same size mix: **≈8.7 GB raw media**. Comfortably inside the
observed 14 GB free on this machine, though D8 in `DESIGN_RATIONALE.md` (delete media after
v1) still applies for the long term.

**Apify fetch — cost. ⚠️ CORRECTED 2026-09-20 against the owner's real invoice.**

The original figure below was **wrong, and wrong in the dangerous direction** — too low by
roughly 3.5x. It was built from the `cost_usd` field Apify's API returns per run, which summed
to $0.181 across the 50 items. The owner's actual bill for the same run was **$0.71**: the API
field does not include the per-run **Actor Start** fee, nor data transfer. Reading a vendor's
own convenience field and calling it "billed and confirmed" was the mistake; the invoice is the
only source of truth for money.

Rates derived from the invoice (50 items, 52 runs — 2 retries):

| Line item | Events | Charged | Unit rate |
|---|---|---|---|
| Actor Start | 52 | $0.26 | **$0.0050 per run** |
| Post (dataset item) | 52 | $0.10 | $0.0019 |
| Video | 37 | $0.11 | $0.0030 |
| Image (1 cover per video + ~10.3 slides per carousel) | 189 | $0.19 | $0.0010 |
| Data transfer | 0.2347 GB | $0.05 | $0.213/GB |
| **Total** | | **$0.71** | |

Per item: **$0.0119 video, $0.0182 carousel** (transfer included). Measured media volume
0.2336 GB over 50 items corroborates the billed 0.2347 GB.

Reweighted to the corpus's real composition (1,714 `/reel/` + 156 `/p/`, per AC-2.1) rather
than this sample's deliberately carousel-heavy mix (30% here vs. 8.3% in the corpus):

> **≈$23.24 projected for the full 1,870-item fetch** — of which **$9.35 is Actor Start
> alone**, because the non-paying account's 5-billable-event cap (§3) forces one run per item.

**This is a large miss against the plan.** §2 estimated **~$3.74**. The measured projection is
**~6.2x that**. Recorded as a miss, not adjusted.

**A second correction, recorded because it was stated aloud to the owner:** an intermediate
estimate of "~$20–22" was given verbally before the arithmetic was done carefully. The figure
computed from the invoice rates is **$23.24**. The earlier number was not derived, and should
not be quoted.

**The cheap route.** Actor Start plus the per-post and per-video fees are what make videos
expensive, and videos are 92% of the corpus. Fetching videos with logged-out yt-dlp (free,
D18/`decisions/002`) and using Apify only for the 156 carousels it alone can handle costs
**≈$2.85** — about an eighth. M0 measured yt-dlp's survival rate, and that trade-off (vendor
reliability vs. 8x the price) is the owner's Wave 2 decision, deliberately deferred.

**Apify fetch — time.** Reweighted the same way: **≈212 minutes (~3.5 hours)** of
sequential run time, one actor run per item (forced by the non-paying-account cap, §3
above). §2 anticipated "minutes to an hour" — this is also a miss, driven directly by the
undocumented per-run cap forcing one run per item instead of one batch submission for the
whole corpus.

**What a paid Apify plan would likely change:** the 5-billable-event-per-run cap is
documented (via the actor's own run logs) as applying to non-paying accounts specifically.
A paid account would very likely allow submitting all 1,870 items as a single batch run,
removing the ~1,870× repetition of the ~5–9s per-run startup latency (the largest plausible
time saving) and the per-run minimum billing behaviour. The per-item download/processing
charges themselves are unlikely to change, since those are charged per file regardless of
batching. **This is inferred from the actor's observed behaviour, not measured on a paid
account** — the owner would need to either upgrade or contact Apify support to confirm the
exact savings before relying on it.

**Groq (Whisper + fusion) — cost.** Groq's SDK returns no cost field (unlike Apify's
`cost_usd`), so nothing here is billed-and-confirmed the way the Apify number is. Two
things are known, though:
- One fusion call hit a `429` during the run, whose error text read: *"Rate limit reached
  for model `openai/gpt-oss-120b` ... tokens per minute (TPM): Limit 8000 ... Upgrade to
  Dev Tier."* An 8,000 TPM ceiling with an explicit upgrade prompt is consistent with Groq's
  **free tier** (per Groq's own published rate limits: free tier ≈6,000–8,000 TPM
  model-dependent, no credit card required), which strongly suggests this account's Groq
  usage during M0 was billed **$0**, not a metered trial. This is inference from the error
  message, not a checked billing statement — **the owner should confirm on
  console.groq.com's billing page whether a card is on file**, since that changes free vs.
  paid tier.
- As an upper bound in case the account does turn out to be on a paid tier: reconstructing
  the actual audio duration transcribed (0.33 total hours across the 25 items with detected
  speech) and the actual prompt/response text sent to fusion (≈25.7k input / ≈8.5k output
  tokens across all 50 calls, counted from the exact text in `pipeline1.jsonl`, not
  guessed) against Groq's published per-token/per-hour rates for these two models gives an
  estimated **≤$0.02 total** for Groq across all 50 items — negligible either way.

**Gemini (pipeline 2) — cost.** Free tier, owner-approved (see `DESIGN_RATIONALE.md` #10):
**$0**. Total token usage reported by the API across all 50 calls: 285,513 tokens
(prompt+output combined).

**Total measured M0 spend: $0.71** (Apify only — the owner's actual invoice, not the API's
`cost_usd` field, which reported $0.181 and omitted Actor Start and data transfer), against
the $6 M0 budget cap. **Still well under budget for M0 itself**, and Groq and Gemini both
billed $0 (owner checked both consoles). The miss above is about the *projected full-corpus
fetch*, a separate and much larger future spend.

---

## 6. VAD speech and the sung-vocal rate

- VAD detected speech in **25/50 items (50%)** — all from the 35 video items (carousels have
  no audio channel by design).
- **Lyric-like transcripts (the sung-vocal heuristic, `m0/04_pipeline1.py`): 3/25 items with
  detected speech (12%)**, or 6% of the full 50-item sample. Heuristic: a transcript is
  flagged when it contains a 3+-word phrase repeated 3+ times (chorus-style repetition), or
  when over 35% of its words are sung filler tokens (la, na, ooh, yeah, ...). This is a
  cheap text-only proxy, not a ground-truth judgement — see the docstring for the exact
  thresholds.
- Per §3's framing: **12% (of speech-bearing items) is not negligible, but it isn't the
  dominant case either.** It stays flagged-and-accepted per the plan rather than earning a
  dedicated music-detection model at this sample size — the owner should re-check this rate
  once real full-corpus numbers exist, since 3 items is a small base.

---

## 7. The blank bucket

**1/50 items (2%)** fell into the blank bucket (no VAD speech, no OCR text ≥2 characters,
and a caption under 15 non-hashtag characters). This is a small fraction, well short of the
"if it's 30 items [of 1,870, ~1.6%], it never [enters scope]" threshold discussed in §3's
open questions — on this sample, it looks like the vision-model-fallback question stays
closed, though 50 items is a small base to extrapolate 1,870 from with confidence.

---

## 8. Unreadable on-screen text (the Devanagari-fallback question, decision #3)

**18/50 items (36%) had at least one OCR candidate string below the unreadable-confidence
threshold** (0.5), totalling 56 individual unreadable strings across those 18 items.
Heuristic, not ground truth (Apple Vision returns every candidate down to confidence 0.0,
and a low-confidence string means Vision found and attempted a text region but wasn't
confident in the transcription — documented in `m0/04_pipeline1.py`).

Breakdown by why the item was sampled (denominator = items sampled for that reason, not all
have equal group sizes):

| Sample reason | Items with ≥1 unreadable string | Rate |
|---|---|---|
| `p_post` (carousel) | 7/10 | 70% |
| `hindi_hint` | 2/5 | 40% |
| `hashtag_heavy` | 3/10 | 30% |
| `empty_or_short_caption` | 5/15 | 33% |
| `random` | 1/9 | 11% |
| `flow_canary` | 0/1 | 0% |

**This is the single most important flag for `decisions/003`-adjacent review** (the cut
Devanagari-fallback decision, `DESIGN_RATIONALE.md` #3): **36% overall is a large number**,
and it is not concentrated in Hindi content — carousels (dense infographic-style slides,
often with small or stylised text) show the highest rate, higher than the Hindi-hint group
itself. This suggests the unreadable-text tag will cover far more than the Devanagari case
the decision was written about, which is exactly the tag's documented intent ("the tag
covers more than Devanagari... set whenever a frame visibly contains text but OCR couldn't
read it") — but 36% is high enough that **the owner should look at a sample of these 18
items' frames himself** (paths are in `data/m0/results.jsonl` → cross-reference
`pipeline1.jsonl`'s `sampled_frame_paths`) before treating the cut fallback as settled,
since #3 explicitly said "the owner decides what 'large' means once he sees the number."
**Flagged, not resolved, by this document.**

---

## 9. Automatic URL/handle/title fidelity: pipeline 1 vs pipeline 2

This is the bake-off's central comparison. Every URL, @handle, and title either pipeline
output was automatically checked against that item's **OCR text** (`m0/06_aggregate_results.py`,
edit distance ≤2, matching §3 AC-3.1's literal rule), and separately against **OCR-or-transcript**
combined (fairer for pipeline 1 specifically, since `04_pipeline1.py`'s own fusion prompt
explicitly permits citing the transcript, not just OCR — AC-3.1's actual production gate is
stricter than what this test's prompt allowed).

**Grounded-in-OCR-only (strict, matches the production AC-3.1 gate):**

| Entity kind | Pipeline 1 (OCR-constrained fusion) | Pipeline 2 (Gemini watches raw video) |
|---|---|---|
| URLs | 20/20 (**100%**) | 13/20 (65%) |
| Handles | 13/22 (59%) | 17/29 (59%) |
| Titles | 132/203 (65%) | 67/134 (50%) |

**Grounded-in-OCR-or-transcript (fairer to pipeline 1's actual prompt):**

| Entity kind | Pipeline 1 | Pipeline 2 |
|---|---|---|
| URLs | 20/20 (100%) | 13/20 (65%) |
| Handles | 13/22 (59%) | 17/29 (59%) |
| Titles | 147/203 (**72%**) | 72/134 (54%) |

**Findings:**

1. **URLs: pipeline 1 is perfect (100%) on this sample; pipeline 2 fabricates or
   paraphrases roughly a third of the time (65%).** This is exactly the failure mode D7
   predicts for a model reading pixels directly instead of through OCR, and it's the
   strongest single piece of evidence in this bake-off for keeping D7 as written.
2. **Handles are the surprise: pipeline 1 only reaches 59%, not the ~100% its own prompt
   should produce.** Manually inspecting the ungrounded pipeline-1 handles (e.g. items
   sampled from Travis Scott / "Utopia"-branded content) shows the fusion model producing
   real, plausible-sounding handles associated with the apparent subject matter that do
   **not** appear anywhere in that item's actual OCR or transcript — a genuine hallucination
   despite an explicit "copy verbatim, never guess" instruction in the fusion prompt. **This
   is the concrete evidence for why AC-3.1's automated fidelity gate must exist as code, not
   as a prompt instruction alone** — even a model told not to guess, guesses, silently and
   plausibly, exactly as D7 says. Prompting compliance is not a substitute for the gate.
3. **Titles sit lowest for both pipelines (65–72% / 50–54%), and that's expected, not
   alarming** — a film or course title can legitimately live only in speech or in a video's
   visual content without ever being written as on-screen text (the *Flow* canary is exactly
   this case: pipeline 2 correctly named the film from watching the video alone, drawing on
   no OCR at all — verified directly in a smoke-test call before the full run, see below).
   The OCR-only gate will always look stricter than reality for titles specifically; that's
   why the plan's real AC-3.1 only ever governed URLs and handles as hard requirements.
4. **The *Flow* canary:** a manual smoke-test call (outside the aggregate counts above)
   showed pipeline 2 correctly identifying "Flow" as the film's title from the video alone,
   with no caption or OCR support — the reel whose caption never names its subject (D3's
   founding example). Pipeline 1's actual result on this same item is in
   `data/m0/results.jsonl` for direct comparison; the owner's blind judging in `judge.html`
   is what actually scores subject-naming quality, this section reports fidelity only, not
   quality.

**Caveat on the fidelity numbers overall:** the matching heuristic (edit distance ≤2 against
each OCR string, and a sliding same-length window against longer OCR lines) is approximate,
not the exact production fidelity-gate implementation `src/reelkb/fusion/` will eventually
own. Treat the percentages above as directionally reliable, not as a certified pass rate.

---

## 10. Peak memory (local steps)

**Measured, not estimated:** `/usr/bin/time -l` around a script that loads the Silero VAD
model and runs Apple Vision OCR (`ocrmac`, `accurate` level) over 20 real sampled frames
from this run reported:

- **Maximum resident set size: ≈288 MiB** (302,153,728 bytes)
- Peak memory footprint (the macOS-reported figure): ≈254 MiB (265,848,032 bytes)

This covers the two local, model-holding steps in pipeline 1 (VAD model + OCR). Whisper and
both fusion pipelines are network calls (Groq/Gemini), not local models, so they don't add
to local RSS beyond the lightweight HTTP client. **288 MiB is far under the AC-6.1 ceiling of
5 GB** — this is an early number on 50 items with lightweight per-frame OCR, not the full
pipeline's final measurement (owned by M11 per the Build milestones table), but it gives no
reason to expect a problem.

---

## 11. Failures and surprises

- **A real pipeline bug was found and fixed during this run, not before it:** `04_pipeline1.py`'s
  VAD step called `silero_vad`'s own `read_audio()`, which depends on `torchaudio`; the
  installed `torchaudio` 2.9.1 refuses to load audio without a separate `torchcodec`
  package that isn't installed (and `pip install` is out of scope for M0). This silently
  killed the fusion step for **every video item** on the first run attempt (caught by a
  broad `except Exception` around the per-item loop body, so 9 of the first 12 items in
  `pipeline1.jsonl` recorded `fusion=None` with this exact error, before it was noticed and
  fixed). **Fix:** replaced the call with a small stdlib-`wave`-based WAV reader
  (`read_wav_mono16k` in `04_pipeline1.py`), since the extracted audio is already known-format
  mono/16kHz/PCM16 and doesn't need torchaudio's general-purpose loading at all. The 9
  affected rows were deleted from `pipeline1.jsonl` and reprocessed after the fix; the final
  `pipeline1.jsonl` has 50/50 successful fusion calls, one of which needed a second, separate
  retry after a transient Groq 429.
- **Apify's full-corpus cost and time projections both came in worse than planned** — see
  §5. This is the most consequential surprise in this document because it feeds directly
  into the §6 model gate and the overall project budget, not just M0 itself. **The cost half
  of it was itself reported wrongly first**: this document originally projected $6.51 from
  Apify's per-run `cost_usd` field, which silently omits the Actor Start fee and data
  transfer. The owner's real invoice ($0.71 for M0, against the API's claimed $0.181) exposed
  it. Corrected projection: **$23.24**, i.e. 6.2x the plan's $3.74 rather than 1.7x. The
  lesson is recorded rather than smoothed over — a vendor's own cost field is an estimate,
  and only the invoice is evidence.
- **Unreadable on-screen text (36%) is higher than casual intuition would suggest**, and is
  not concentrated in the Hindi-hint group the decision was originally written about — see
  §8.
- Two docstring/implementation mismatches in `04_pipeline1.py` were found and corrected
  in-place (not a data problem, a documentation-accuracy one): the file previously promised
  per-item `ocr.json`/`transcript.txt`/`fusion.json` files that were never actually written
  (all of that data lives only in the `pipeline1.jsonl` aggregate row, which nothing
  downstream needed to be separate files for), and carousel frames are referenced directly
  from `media/` rather than copied into `extract/<shortcode>/frames/`. Both docstrings now
  match what the code actually does.
- One Groq `429` (rate limit) and zero Gemini errors across all 100 model calls (50 fusion +
  50 Gemini) combined — the pipeline held up well operationally once the VAD bug above was
  fixed.

---

## 12. PENDING owner judgement

**Not yet done — requires the owner.** `data/m0/judge.html` is built and ready
(`data/m0/judge_key.json` holds the X/Y→pipeline mapping, kept separate from the page itself
so the blinding is real even under "view source"). It presents, per item: 3 sampled frames,
caption, OCR text, transcript, and both pipelines' fusion output labelled "Output X"/"Output
Y" in a randomised-per-item order. For each item the owner judges: does X name the subject
(yes/partly/no), same for Y, any wrong URL/handle spotted in X, in Y, plus a free-text note.
A Save button downloads the judgements as `judgements.json`, which the owner should place at
`data/m0/judgements.json`.

**What this document cannot tell you without that step:** which pipeline actually produces
*better* human-judged subject-naming quality (§9 above only measures automatic
grounding/fidelity, a different and narrower question), and how the owner's own read of
"wrong URL/handle" compares to the automatic edit-distance check in §9 — the two are
expected to roughly agree given §9's findings, but that's exactly the kind of assumption a
`checker`-style independent judgement should confirm rather than one document asserting on
its own.

**Feeds directly into the §6 model gate (D14):** once judged, this is the deciding evidence
for whether pipeline 1 (OCR-grounded, cheaper wall-time for videos, provably 100% URL-faithful
here) or pipeline 2 (Gemini, slower, provably less URL-faithful, but able to name subjects
OCR never captures — see the *Flow* canary in §9) — or some hybrid — is the production
choice for M4/M5.
