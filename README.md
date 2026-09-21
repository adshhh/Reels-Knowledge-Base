# Reel Knowledge Base

A searchable, browsable knowledge base built from ~1,870 Instagram reels I saved to a dummy
account's DM over four years.

> **Status: v1 in development.** Every stage is built and tested end-to-end on synthetic
> data. It has not yet been run on the real archive.

---

## What this is, and why

For four years I forwarded anything worth keeping — ML resources, free courses, papers, film
and book recommendations — to a second Instagram account. It worked as a place to *put*
things and failed completely as a place to *find* them. Roughly 1,870 useful items,
effectively write-only.

This turns that dump into something I can browse and search, organised into categories that
emerge from the content itself rather than ones I maintain by hand. It runs entirely on my
own machine and will be reachable from my phone over Tailscale. The repository is public; the
archive never leaves my laptop.

**The hard problem is extraction.** Captions routinely describe a reel without
naming its subject. The example that shaped the design: *"Not only was this movie visually
stunning, I loved it & so did Kuma"* — the film is **Flow**, a word appearing nowhere but on
screen. No amount of clever matching finds a name that was never written down, so the content
has to be recovered from pixels and audio.

Hence the central rule: **OCR reads and the language model interprets.**
Vision-language models score ~45% F1 on non-semantic text like URLs and handles, where humans
score 97%. OCR fails loudly and filterably (`c0urser@.0rg` is obviously broken); a model fails 
silently, handing you a URL wrong by one word. So verbatim OCR output is written by exactly 
one stage and immutable after, enforced by a database trigger rather than discipline, and every 
entity a model emits is checked back against what was actually on screen before it reaches a card.

---

## How it's built

The plan, its acceptance criteria and every design decision live in
[`docs/PLAN.md`](docs/PLAN.md). Nothing gets built that isn't traceable to a section there.

```
export → parse → fetch media → OCR + speech → fusion → embeddings
                                                           ↓
         browse + search UI ← classification ← taxonomy discovery
```

Two stages carry most of the risk. **Verbatim** runs Apple Vision OCR for on-screen text and
gates speech-to-text behind voice-activity detection, so a music-only reel yields an empty
transcript instead of an invented one. **Fusion** has a model combine caption, OCR and
transcript into a title and summary (a fidelity gate discards anything the on-screen
text doesn't corroborate). Search is hybrid: dense embeddings for meaning, sparse lexical
matching for exact terms, fused into one ranking.

Work runs in three waves: the foundation (data contract, commit guards, CI, and a bake-off on
50 real reels to pick the extraction models), then everything buildable against fake data in
parallel, then the real archive one stage at a time — the machine has 8 GB of RAM, and two
model-holding processes at once is the defining failure mode.

Quality is enforced structurally: the suite runs after every edit, no unit test may touch the
network or load a model, an independent agent re-verifies each milestone with no knowledge of
how it was built, and success is measured against hand-labelled fixtures frozen before any
tuning.

---

## What I'm responsible for

**I don't write the code.** I direct AI agents that do, and own the parts that can't be
delegated:

- **Architecture and decisions.** Every significant choice is numbered and recorded with its
  cost — what was *given up*, not just what was picked. Changing one already marked LOCKED
  requires an entry in [`docs/decisions/`](docs/decisions/) naming what it invalidates.
- **The ground truth.** 150 hand-labelled reels and 50 search queries I write and grade
  myself. I'm also judging the extraction bake-off blind, not knowing which pipeline produced
  which output.
- **Reviewing evidence, not code.** Each stage reports how every claim is *proven* — a named
  test, a measured number — including whether the check could pass while the thing is broken.
- **Judging the product.** - Acceptance criteria and reviews validate the specifications, but 
  they don't assess whether the final product is actually good enough.
- **Every git operation, personally.** The agents are blocked from any command that changes
  repository state. The repo is public and the archive is personal, so what gets committed is
  a decision I make by hand.

The aim is that I can explain the architecture, not merely run it.

---

## Where it is now

**Pipeline complete end-to-end; not yet run against production data.**

Every stage — media fetch, OCR + ASR (automatic speech recognition), fusion, embedding,
classification, and the search/browse UI — is implemented and passing its test suite against a
synthetic corpus. It has not yet been run against the real archive (~1,870 reels). This is
intentional: iterating against synthetic fixtures is near-zero-cost, while a full run against
the real archive incurs non-trivial API spend and wall-clock time, so the pipeline is fully
validated before that cost is paid.

Two workstreams are active:

1. **Model selection via blind A/B evaluation.** Two candidate extraction pipelines were run
   over a 50-reel holdout set (deliberately hard cases — low-text-density frames, overlapping
   speech, non-English captions). Outputs are being scored pairwise without knowledge of which
   pipeline produced which output, to eliminate expectation bias from the evaluation. **In
   progress.** The winner becomes the extraction method for the full corpus run.
2. **Interim results** are published in
   [`docs/M0_FINDINGS.md`](docs/M0_FINDINGS.md) as aggregate counts and percentages — no
   underlying reel content included.

Next: full corpus ingestion through the pipeline, followed by retrieval evaluation — a
hand-written query set scored against actual search output to quantify recall/precision rather
than assert it.

Current CI status: 452 tests passing, lint and type checks clean, green on every push.

Stage-by-stage history, including defects found in review, is in
[`docs/checkpoint_report.md`](docs/checkpoint_report.md).

---

## Layout and running it

[`src/reelkb/`](src/reelkb/) — pipeline and web app, one package per stage ·
[`tests/`](tests/) — unit suite, no network or models ·
[`m0/`](m0/) — bake-off scripts ·
[`docs/`](docs/) — plan, contract, rationale, decisions, findings

`data/` and the media files are not here and never will be — enforced by `.gitignore` and a
pre-commit hook, not by memory.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"      # ".[dev,pipeline]" for the model-backed stages
pytest
```

The tests run against a synthetic corpus, so they pass on a clean clone with no archive and
no API keys.
