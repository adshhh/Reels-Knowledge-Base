# 007 — Hiding a card is reversible (amends D15)

**Date:** 2026-10-01 · **Status:** accepted · **Rationale:** `docs/DESIGN_RATIONALE.md` §15

## 1. What changed

D15 said hide and edit actions are "permanent". A Wave 1 builder added `unhide`, the one place
a builder overrode a locked decision. The owner keeps it: **D21** -- hiding survives every
pipeline re-run, as before, but the owner can reverse it from the Hidden page.

## 2. Why it changed

Hiding was already a soft delete -- the record stays. Unhide only makes a mis-tap recoverable.
"Permanent" was meant against the pipeline undoing the owner, not against the owner.

## 3. Sections this invalidates

- **§1 Product form** -- the Curation paragraph. Wording only; no acceptance criterion changes.

## 4. Trade-offs / what was given up

- A hide is no longer a final verdict; a later mis-tap on "unhide" brings a card back.
