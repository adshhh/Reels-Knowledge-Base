---
description: Audit a milestone's plan sections for contradictions, then write an implementation plan in a fixed, skimmable shape
---

# /plan-milestone <number>

**Wave loop step 2** (see *"How the build actually runs"* in `docs/PLAN.md`). Two parts, in
this order: **audit first, plan second.** The audit exists because plan sections written
before any code existed are routinely wrong, and finding that out mid-build costs far more
than finding it out now.

**Scope: one plan per wave, covering every milestone in it** — or, where a wave is built by
parallel builders, this becomes the lead's written brief to each builder rather than a
document the owner reviews (that is what happened in Wave 1). **Part 1 is not optional in
either case.** When the owner does not see a plan, the audit is the only thing standing
between a stale plan section and six builders acting on it at once, so it runs and is
reported either way.

## Part 1 — Pre-build audit

Read the milestone row in the Build milestones table, then read **every plan section it
names, in full**. Never work from memory or from a summary of the plan. Then check for:

1. **Unowned work** — anything the plan promises that no milestone actually owns.
2. **Impossible sequencing** — a criterion scheduled before the thing it depends on exists.
3. **False claims about the codebase** — the plan saying "X already does Y." Open X and
   confirm. This is the highest-yield audit check by a wide margin: plans routinely assert
   that some earlier component produces a reusable artifact it does not produce.
4. **Contradictions with neighbouring sections or numbered decisions.**
5. **Criteria that cannot be verified** as written, or that need a human.

Report findings as a numbered list. For each: what the plan says, what is actually true, and
what you propose. **Fix the plan at the source**, not locally in this milestone — a
correction that lives only in the implementation is a correction the next milestone won't see.

If a finding changes something LOCKED, stop and run `/log-decision` before continuing.

## Part 2 — The implementation plan

Write it in exactly this shape. The owner is reviewing a paragraph, not code — keep it
skimmable and put the decisions that need them at the top, not buried.

### ⚠️ Needs your decision
Anything that changes how the tool looks or teaches, adds scope, touches a LOCKED decision,
adds a dependency, or is expensive to reverse later. **Each with a recommendation and a
one-line trade-off.** If there is nothing, write "nothing — this milestone is fully
determined by the plan." Do not pad this section; a real empty is more useful than a
manufactured question.

### Acceptance criteria this milestone closes
The AC ids, quoted verbatim, and for each: **how it will be proven.** A named test, a
screenshot, a measured number. If an AC has no proof plan, say so now — that is the single
best moment to catch it.

### What I'm building
Plain language, no file names. Three sentences maximum.

### Files
New and modified, one line each.

### Deciding independently
Naming, file structure, small visual details. Listed so the owner can object, not so they
must approve.

### Riskiest part
The one thing most likely to go wrong, and what I'll do if it does.

### Out of scope
What this milestone deliberately does not touch. Prevents scope drift by naming it up front.
