# 003 — External links and typed notes deferred to v2 (adds to §9)

**Date:** 2026-09-19 · **Status:** accepted · **Rationale:** `docs/DESIGN_RATIONALE.md` §9

## 1. What changed
§9 (Out of scope for v1) gains an item: the export's 17 non-reel items -- 10 `external`
(8 non-Instagram links, 1 share with no link key, 1 profile share) and 7 `note` -- are
recorded in the manifest but do not appear in
the v1 app. A v2 pipeline will surface them under their own tag.

## 2. Why it changed
The pre-build audit for M0/M1 found these items, which no section mentioned. Handling them
properly is new pipeline and UI work that isn't on the v1 path.

## 3. Sections this invalidates
- **§9 Out of scope for v1:** one item added. Re-locked in the same change; nothing else in
  §9 is affected.

## 4. Trade-offs / what was given up
17 items are not browsable in v1 (counted 2026-09-19; the original estimate said ~16). They are still in the manifest, so nothing is lost.
