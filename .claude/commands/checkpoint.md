---
description: Report what was built this wave as a per-milestone evidence table, and give the owner git commands to run
---

# /checkpoint

**Wave loop step 8** (see *"How the build actually runs"* in `docs/PLAN.md`). The owner
reviews **evidence**, not code. So this report leads with a table they can audit without
reading a line of the implementation.

**One batched checkpoint per wave, with a section per milestone in it** — not one per
milestone. A wave is the unit of owner review; a milestone is the unit of verification, so
every milestone still gets its own evidence table, its own independent decisions and its own
uncertainties, inside the one report. Write a mid-wave checkpoint only when the owner asks
for one, or when a wave has run long enough that batching would bury something he must act
on — and say which it is.

## 1. Update `docs/PLAN.md`

**The "Resume here" box is capped at 20 lines and is REWRITTEN, never appended to.** It
answers exactly three things: what was last completed, what is next, what is currently open.
The narrative history belongs in `docs/checkpoint_report.md`, which exists for it. A resume
box that grows every milestone stops doing its job and costs context in every future session.

Also update the **Status board**: if a section was reopened and re-locked this milestone,
confirm it shows LOCKED again. Anything genuinely still open stays listed with its status.

## 2. Append to `docs/checkpoint_report.md`

### `## Wave <n> Completed` — then `### Milestone <n>` for each milestone in it

Everything below repeats **once per milestone**, under its own heading. A batched report is
not a merged one: two milestones sharing an evidence table is how an unproven AC disappears.

### Evidence table — put this FIRST

| AC | What it requires | How it's proven | Where to see it | Could this pass while broken? |
|---|---|---|---|---|

One row per acceptance criterion this milestone claimed. Rules:

- **"How it's proven" must be checkable by someone who cannot read the code.** A named test,
  a committed snapshot, a screenshot, a measured number, a URL. Never the word "verified."
- **The last column is not optional and is not decorative.** Answer it honestly for every
  row. If a test asserts a component rendered but not that it rendered *correctly*, that
  column says so. Writing "no" in every row without thinking is how the review becomes
  theatre.
- **Any AC you could not prove gets a row saying so**, not a row omitted. A missing row is
  the failure mode this table exists to prevent.

### `### What was built`
Plain language. What the owner could now do that they couldn't before.

### `### Why`
The reasoning behind anything decided independently — a library pick, a file structure, a
naming choice. If nothing, write "nothing decided independently this milestone."

### `### Files created/modified`
Path, new-or-modified, one line on what's in it.

### `### Uncertain / worth double-checking`
Anything you are unsure about, stated plainly. **Never write "none this milestone" unless it
is actually true** — a milestone with genuinely nothing uncertain is rare, and an empty
section here is usually a failure of nerve rather than a fact.

### `### How to see it yourself`
No screenshots (D13): the owner checks visual quality directly. For a visual change, give the
exact command to start the app and the URL/page to open, plus **what specifically to look
at**. For a non-visual change, include the terminal output that proves it works.

### `### Git commands for this wave`
Written **once for the wave**, not per milestone — the owner commits the wave, not each
milestone. The exact commands to run, each with a one-line plain-English explanation.

## 3. Close

One sentence: which wave is next, and the first thing in it. If a wave completed, name the
owner tasks that gate the next one.

---

**`checker` runs BEFORE this command, not after** — wave loop step 7, once per milestone,
with no knowledge of the build narrative, followed by `/code-review` on the combined changes.
Both happen while there is still time to fix what they find, which is the whole point of
their position in the loop.

So this report must **carry their verdicts into the evidence table**, not replace them.
Anywhere your table says proven and `checker` said `CLAIMED, UNPROVEN`, the table says so and
explains the discrepancy. That disagreement is the real review; a checkpoint that quietly
overrides it has inverted the loop.
