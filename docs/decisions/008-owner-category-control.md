# 008 — Extra categories, an editable category list, and a links section (adds to §1, §4)

**Date:** 2026-10-01 · **Status:** accepted · **Rationale:** `docs/DESIGN_RATIONALE.md` §16

## 1. What changed

Three owner-requested features, so the owner can correct anything the model gets wrong:

- **D22 — extra categories.** The classifier still assigns one main category per reel and is
  graded only on that. The owner can add a card to any number of extra categories by hand; it
  appears in each of those feeds and counts.
- **D23 — the category list is editable from the app**: rename, add, delete. Delete never
  leaves a card without a category: its cards move to a category the owner picks, or to
  `other`, and holdout labels pointing at it are remapped the same way. A new category joins
  the list the classifier uses for future reels; existing reels move by hand or by a
  re-classification run (~$0.60). Ids still never change. All edits are stored append-only,
  like other owner edits, so no pipeline re-run can undo them. Merge was not requested.
- **D24 — a "Links & titles" section on every card**, showing the extracted URLs (clickable),
  @handles and titles, with unconfirmed ones visibly marked.

## 2. Why it changed

The owner wants the final say over every card even when the model is right most of the time.
The links section closes a gap found on 2026-10-01: extracted entities were stored but only
visible buried in the raw on-screen text.

## 3. Sections this invalidates

- **§1 Product form** -- the detail view and curation actions.
- **§4 Categorisation** -- "the owner edits that draft into `taxonomy.yaml`" (once, as a file)
  and the single-category model of a reel.

§7's measurements are deliberately untouched: grading stays on the main category only.

## 4. Trade-offs / what was given up

- The taxonomy is no longer frozen after one edit; the owner can change it any time, so the
  holdout's category set can drift from what it was labelled against (remapping limits this).
- An extra category is invisible to the grading, so a classifier that is right on the main
  category but wrong on what the owner considers a second category scores as fully correct.
- More UI and curation code to build and test in Wave 2.
