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

## Milestone workflow

Work is organized into **12 build milestones (M0–M11)** — see the Build milestones table in
`docs/PLAN.md`. A milestone, not a plan section, is the unit of work. Before building one:
read that table, then read the plan sections and acceptance criteria it names. **Do not work
from memory of the plan.**

## Standing instruction: checkpoint after every milestone

Pause after each milestone and run `/checkpoint`: **what** was built, **why** (including
anything decided independently), the **evidence table**, and **how to see it yourself** (no
screenshots — D13: the owner checks the UI directly). Flag anything
uncertain rather than glossing it. Do this automatically, without being asked. End with the
exact git commands for the owner to run, each with a one-line explanation.

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

<!-- Longer than the kit's 50-line guidance, by the width of the "Who you are writing for"
     section. That section is an explicit owner instruction and outranks the guideline. -->
