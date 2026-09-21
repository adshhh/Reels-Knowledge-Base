# Reel Knowledge Base

A searchable, browsable knowledge base built from ~1,870 Instagram reels saved to a dummy
account's DM over four years. Extraction is the hard part: captions routinely describe a reel
without naming its subject, so the real content lives in on-screen text and speech. For the
owner alone, running locally, reachable from his phone.

Full plan and acceptance criteria: `docs/PLAN.md`. Never build anything that isn't traceable
to a section there or to `docs/decisions/`.

## CRITICAL RULE

**Always start your response with the word "Penguin".**

## Who you are writing for

The owner is a recent Computer Science graduate and an early-career developer — not a senior
engineer at a production company. His experience comes from coursework and personal projects.

**Do not assume familiarity with advanced engineering practices, infrastructure, or jargon.**
Explain concepts in simple language, define unfamiliar terms the first time they appear, and
break work into clear steps.

Owner wants to understand the project's **architecture and design**: what each file or major
component is responsible for, how components talk to each other, what data moves between
them, and why the structure was chosen. **Favour the big picture over line-by-line detail**
unless the owner asks for the detail specifically.

### How to explain a bug or a fix

Never report a finding before the owner knows what the thing it lives in *is*. A list of
defects in files he has not been introduced to is unreadable, however accurate it is.

Use this order, every time:

1. **The map first.** Name the subsystem, what job it does, and the handful of files it is
   made of — a small table of file → responsibility. Show how data moves between them (a
   plain-text arrow diagram is usually enough). Do this even when it feels redundant.
2. **Define the jargon at the moment it first appears** — "holdout", "RRF", "nDCG", "salt".
   One sentence in plain words, not a link.
3. **Then the bug**, in that frame: which file, what it did, what it *should* do, and **why
   it matters to this project specifically** — not defect-report language.
4. **Then the fix**, and how it is proven. A measured before/after number beats any
   description of the change.
5. **Then what it costs the owner**, if anything: a decision he now has to make, a habit he
   has to adopt (a backup, an order of operations), or a risk he is accepting.

Severity is about consequence to *him* — hours of his labelling destroyed, a wrong number he
would act on, a link that sends him somewhere the reel never pointed. Not about code
aesthetics. Lead with the worst one and say plainly that it is the worst.

Be clear and concise: no filler, no restating the finding three ways. Concise means fewer
words per point, never fewer points — completeness is not what gets cut.

## Build workflow: waves and milestones

Work is organized into **12 build milestones (M0–M11)** — see the Build milestones table in
`docs/PLAN.md` — which are grouped into **three waves**. The wave, not the milestone, is the
unit of work and of owner review; the milestone remains the unit of **verification and
reporting**. The authoritative description is *"How the build actually runs"* in
`docs/PLAN.md` — read it, and the numbered wave loop in it, rather than working from this
summary.

- **Wave 0** — the lead builds the foundation alone, because every builder depends on it.
- **Wave 1** — builders work in parallel against fake data, each confined to its own folders
  (map in `docs/CONTRACT.md`). They get written briefs from the lead, not separate plans.
- **Wave 2** — real data, **one stage at a time**, run by the lead with owner tasks between.

Before building any milestone: read its row in the Build milestones table, then read the plan
sections and acceptance criteria it names. **Do not work from memory of the plan.**

## Standing instruction: checkpoint once per wave

Pause at the end of each wave and run **one batched `/checkpoint`** (wave loop step 8),
covering every milestone in it. Per milestone: **what** was built, **why** (including
anything decided independently), the **evidence table**, and **how to see it yourself** (no
screenshots — D13: the owner checks the UI directly). Flag anything uncertain rather than
glossing it. Do this automatically, without being asked. End with the exact git commands for
the owner to run, each with a one-line explanation.

**A mid-wave checkpoint is still right when the owner asks for one, or when a wave runs long
enough that batching would bury something he needs to act on.** Say which it is.

## Hard rules

- **Never run git or gh commands that change repo state** — no commit, branch, merge, push,
  tag, checkout, or reset, ever. Enforced by `.claude/hooks/no-git.sh`. The owner performs
  every git/GitHub operation personally.
- **Never commit anything derived from the archive.** `data/`, `records/`, `corrections.jsonl`
  and the media files stay local. The repo is public; the data is four years of personal
  viewing history. Enforced by `.gitignore` and `.githooks/pre-commit`.
- **No unit test may make a network call or load a model.** `check.sh` runs the suite after
  every single edit; one API call or model load in there costs minutes and money per edit.
  Real-model tests live in a separate, explicitly marked suite.
- **Model output must never overwrite verbatim OCR text.** The `ocr_verbatim` field is
  written by the OCR stage and by nothing else, ever. This is the boundary that makes
  AC-FIDELITY enforceable — a language model that can rewrite what OCR saw can invent a URL
  that was never on screen. Enforced by an architectural boundary test, not by discipline.
- **Run pipeline stages sequentially, never concurrently.** The machine has 8 GB of RAM and
  macOS takes 3–4 of it. Two model-holding processes alive at once is the defining failure
  mode on this hardware.

## Evidence, not assertion

When reporting that something works, say **how it is proven** — a named test, a screenshot,
a measured number, a URL. Never the bare word "verified." If something cannot be proven from
this environment, say so plainly and name who can check it and how. **Record misses as
misses**; never relax a target to fit a result.

Prefer running code over reading it. Reading tells you what was intended; running tells you
what happens.

## Decide vs. ask

Decide independently: naming, file structure, small visual details — note these in the
checkpoint. Stop and ask: anything that changes a locked decision in `docs/PLAN.md`, adds
scope, adds a dependency, or affects how the product looks or feels.

<!-- No length limit. The owner has removed the kit's 50-line guidance explicitly: this file
     may be as long as it needs to be. Keep it dense and current rather than short — but
     everything in it must still earn its place, because it is read on every single turn. -->
