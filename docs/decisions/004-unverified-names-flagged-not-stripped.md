# 004 — Unverified names in card prose are flagged, not stripped

Date: 2026-09-20. Decided by the owner after the M5 checker's report and a measurement against
the 50 real M0 items.

## 1. What changed

AC-3.1 says: *"No stored record contains a URL, @handle, or proper-noun title absent from that
reel's OCR output within edit distance 2."*

As built, the gate now:

- enforces that for **URLs and @handles** everywhere, including inside the card's prose — a URL
  or handle it cannot confirm is removed from the text and recorded in `dropped_entities`;
- enforces it for **every entity in the model's declared `entities` list**, of all three kinds;
- **does not remove proper-noun titles from the prose.** It finds them, records each one it
  cannot confirm in a new `fusion.unverified_names` column with its location, and leaves the
  title, summary and bullets exactly as the model wrote them. The card displays a
  "N unverified names" badge.

So a stored card **can** still contain a proper-noun title that on-screen text does not
confirm. It is marked, not removed.

## 2. Why it changed

Two findings, both reproduced against the real code before anything was changed.

**The gate never checked prose for names at all.** It scanned prose for URLs and handles only.
A name could be rejected from the declared entity list and still stand as the card's headline —
demonstrated with a card titled `Nosferatu (2024)` for a reel that never mentions it, with
`dropped_entities` empty.

**The obvious repair destroys correct cards.** AC-3.1 verifies against on-screen text *only*.
Measured on the 50 M0 items: 3 have no on-screen text at all, and 35 of 50 carry at least one
name that is correct but unconfirmable this way. The clearest case is a card reading *"Source
Code movie recommendation"* — the model identified a real 2011 film from speech, correctly, and
the gate rejects both "Source Code" and "Hulu" only because the reel shows no text. Stripping
would retitle it *"movie recommendation"*: a correct card destroyed by the mechanism meant to
protect it.

The owner chose to make the doubt visible and defer the irreversible choice until the 50-reel
judgement provides evidence — that judgement measures exactly whether a thin card reads as
"subject not named".

## 3. Which sections of the plan this invalidates

- **§3 Extraction — the heart of the project**, specifically **AC-3.1 (AC-FIDELITY)**. Set back
  to **open** in the status board. AC-3.1 is **NOT MET** as written and must be rewritten once
  the owner decides, after judging, between:
  1. stripping unverified names from prose (AC-3.1 stands as written), or
  2. widening the allowed evidence to OCR **plus transcript**, so spoken names count (AC-3.1
     is reworded and the guarantee weakens), or
  3. keeping flag-only permanently (AC-3.1 is rewritten around marking rather than absence).

No other section changes. **§8** is untouched: the new column is written by the fusion stage
and read by the serving layer, which remains read-only (proven in
`tests/serve/test_provenance_and_flags.py`).

## 4. Trade-offs / what was given up

- **AC-3.1 is not met, and is recorded as a miss** rather than reworded to fit what was built.
  The target was not moved.
- A card can display a name the reel never showed. The badge says so; nothing silently claims
  it was verified.
- Where prose is Title Case, capitalisation carries no signal, so detection stands down there
  and relies on the declared-entity net. Scanning anyway flagged 46 of 50 cards and would make
  the badge meaningless. Closing that gap needs name recognition or a dictionary, both out of
  scope for v1.
- 32 of 50 M0 cards carry at least one flag. The badge is therefore common, which is itself the
  finding: on-screen-text-only verification cannot confirm most names in this archive.

## 5. Related

- `DESIGN_RATIONALE.md` #11 (this decision) and #12 (card provenance).
- The separate, still-open question of whether the **transcript** should count as evidence is
  deferred to the same post-judging decision; the owner parked it deliberately.
