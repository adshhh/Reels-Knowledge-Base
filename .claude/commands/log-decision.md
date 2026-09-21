---
description: Log an architectural or design decision; open an ADR if it changes something LOCKED
---

# /log-decision

Two tasks. The first always runs; the second only when a LOCKED decision actually changed.

## Task 1 — always: write in `docs/DESIGN_RATIONALE.md`

Number the heading as the next sequential number after the last entry. Structure:

- **The situation** — what prompted this decision
- **Options considered** — what was genuinely on the table
- **Decision** — what was chosen
- **Why / trade-off** — the reasoning, and **what was given up**

The trade-off line is the one that matters. An entry with no cost recorded is a
justification, not a decision — if nothing was given up, there was no decision to log.

## Task 2 — only when this changes something marked LOCKED in the plan

1. Find the highest number in `docs/decisions/` and take the next (`NNN`, zero-padded).
   Create `docs/decisions/NNN-short-title.md`.
2. It must answer:
   1. What changed
   2. Why it changed
   3. **Which section(s) of the plan this invalidates** — named explicitly, by number and title
   4. Trade-offs / what was given up
3. In the plan's Status board, set each section named in 2.3 back to **open**, listed with
   what reopened it.
4. Once that section is actually fixed — not merely reopened — set it back to LOCKED.

## Task 3 — always: check the instructions, not just the docs

Every task above writes to `docs/`. **Nothing there steers a future session.** `CLAUDE.md` is
read on every single turn and `.claude/commands/` defines how the commands behave, and until
this step existed, no part of this process ever looked at either.

So before finishing, grep both for anything this decision has just made false:

```
grep -rn "<the thing that changed>" CLAUDE.md .claude/
```

Fix what you find, in the same breath as the decision. Say in the response which instruction
files changed, or state plainly that you checked and none needed to.

**How this was learned:** the build moved from one-milestone-at-a-time to waves. `PLAN.md`
and `DESIGN_RATIONALE.md` were both updated properly. `CLAUDE.md` went on saying *"a
milestone is the unit of work"* and *"checkpoint after every milestone"* for the whole of
Wave 1, and `/checkpoint` went on calling itself *"Loop step 7"* of a loop that no longer
existed. Nothing broke, because the session that made the change knew better and silently
ignored the instruction — which is exactly why it survived. **A stale instruction that
produces no error is only discovered when a fresh session obeys it**, and a fresh session
reads these files and none of the conversation where it was agreed otherwise.

## The rule this protects

A locked decision that can be changed silently was never locked. The cost of an ADR is what
makes "LOCKED" mean something, and that cost should be paid every time, including when the
change is obviously correct.

**Record failures the same way.** If a target is missed, log the miss and explain why the
target was wrong — do not move the target to fit the result. A plan that only ever records
successes is not a record of anything.
