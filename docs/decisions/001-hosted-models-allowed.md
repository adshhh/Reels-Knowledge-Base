# 001 — Hosted models allowed (supersedes D9)

**Date:** 2026-09-19 · **Status:** accepted · **Rationale:** `docs/DESIGN_RATIONALE.md` §1

## 1. What changed

D9 ("open-weight models for all inference; Apple Vision excepted") is superseded by **D17**:
hosted and closed models are allowed wherever they are the cheapest option that meets the
acceptance criteria. The owner prefers free or near-free options, with a first-run target
under ~$6. D7 (OCR reads, the model interprets) and D8 (VAD before speech-to-text) are
unchanged.

The model for each stage is **not** chosen by this record. The §6 model gate (D14) stays open.

## 2. Why it changed

D9 existed because the owner expected to run every stage himself on free open models. Hosted
options now cost the same or less, and hosted speech-to-text removes a 4–8 hour overnight
run on the 8 GB machine.

## 3. Sections this invalidates

- **§3 Extraction.** It names `gpt-oss-20b` as the fusion model.
- **§6 Models and where they run.** The whole table was built on the open-weight rule.
- **§8 System architecture.** The diagram names specific models per stage.

## 4. Trade-offs / what was given up

- Reel content may be sent to closed-model providers (Google), not only Groq.
- Hosted models can change or be retired without notice, so reruns are less reproducible.
