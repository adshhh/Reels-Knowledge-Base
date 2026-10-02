# 005 — Gemini reads the reel, OCR text in its prompt (supersedes D7)

**Date:** 2026-10-01 · **Status:** accepted · **Rationale:** `docs/DESIGN_RATIONALE.md` §13

## 1. What changed

D7 ("OCR reads. The language model interprets. Never the reverse.") is superseded by **D19**:
the card is written by Gemini Flash-Lite (`gemini-3.5-flash-lite`), which watches the whole
video (frames and audio) or every carousel slide, with the reel's local Apple Vision OCR text
supplied in its prompt. OCR still runs locally, and `ocr_verbatim` is still written only by the
OCR stage and never overwritten -- that hard rule is unchanged.

This settles the **on-screen text** and **fusion** rows of the §6 model gate (D14). Fetch,
speech and classification rows are still open.

## 2. Why it changed

The owner's blind M0 judgement: Gemini 31, pipeline 1 5, tie 14 (p < 0.001), and only 2 of 50
Gemini cards with a wrong link. Detail in `docs/M0_FINDINGS.md` §12.

## 3. Sections this invalidates

- **§3 Extraction** -- the fusion step ("its job is organising and interpreting, never
  reading"), the validation gate ("dropped and flagged"), and AC-3.1's wording all assume D7.
- **§6 Models and where they run** -- the fusion row names `gpt-oss-20b`; the cost total.
- **§8 System architecture** -- the diagram's fusion stage.

## 4. Trade-offs / what was given up

- A link or title can now come from the model's own reading of pixels or audio. The fidelity
  gate checks it against OCR, which reads less than Gemini does, so it must **flag** what it
  cannot confirm rather than drop it.
- Every reel's video and audio goes to Google.
- ~$3.30–3.80 for the corpus (standard) instead of ~$0.75.

## 5. Settled by the owner, 2026-10-01

1. **Paid tier, standard mode** (~$3.30–3.80). Google's terms: paid-tier prompts and files are
   not used to improve its products; free-tier content can be, and may be human-reviewed.
2. **Whisper is kept** (Groq free tier) and its transcript goes into Gemini's prompt alongside
   the OCR text, as evidence Gemini checks itself against before writing the card.
3. **AC-3.1 rewritten:** every link, @handle and title on a card is confirmed against
   on-screen text or visibly marked unconfirmed -- never silently deleted. Titles are checked
   word by word.
4. **The prompt is checked on 35 random reels**, judged by the owner with notes, before it
   runs on the corpus.
