# Reel Knowledge Base — Master Plan

## Context

Around 1,870 Instagram reels were sent to a dummy account's DM over four years — ML resources, free courses, research papers, movie recommendations, book lists, and a long tail of miscellany. The content is genuinely useful. The storage makes it useless: no search, no structure, no way to find something you know you saved two months ago.

This project turns that dump into a **knowledge base you can browse and search**, organised into categories that emerge from the content itself rather than ones maintained by hand.

It is a personal project, built to the standard of a portfolio project, in a public GitHub repository. The owner is a recent Computer Science graduate; the architecture is meant to be understood and explained by him, not merely to work.

**The constraints that shape every decision:**

1. **The owner writes no code.** The plan, not code review, is the defence against scope drift.
2. **The hardest problem is extraction** — finding out what each reel actually contains. Captions lie by omission. Solve extraction and most of the project is solved.
3. **The scope contract is `eval/holdout_v1.jsonl` and `eval/queries_v1.jsonl`** — two hand-labelled fixture files — not a list of features.
4. **The repository is public; the data is private.** Nothing derived from the archive is ever committed.

> ### ⏸ Resume here
>
> **CAPPED AT 20 LINES. REWRITTEN EACH MILESTONE, NEVER APPENDED TO.**
> Narrative history lives in `docs/checkpoint_report.md`.
>
> **Last completed:** nothing — planning phase
> **Next:** M0 — attrition probe and extraction bake-off
> **Open:** §6 model gate unresolved (D14). §2, §3, §6, §8 reopened by `decisions/001–002` (D17, D18) and must be rewritten and re-locked before building. Owner to create Apify + Groq accounts and run `git init`; kit adaptation awaiting sign-off

---

## Glossary

Terms used throughout this document, defined once here.

| Term | Plain meaning |
|---|---|
| **Inference** | Running a model to get an answer out of it. "Where inference happens" = on your Mac, or on a server you call over the internet. |
| **OCR** | Optical Character Recognition — reading text that appears *in a picture*. Here: text shown on screen in a reel. |
| **VAD** | Voice Activity Detection. A small, cheap model answering one question: is anyone actually speaking? Used to stop Whisper inventing speech over music. |
| **Whisper** | OpenAI's open-weight speech-to-text model. Turns spoken audio into text. |
| **Embedding** | A piece of text converted into a list of numbers that captures its meaning, so similarity can be measured. Two reels about free ML courses get similar number-lists even with no words in common. |
| **Edit distance** | How many single-character changes turn one string into another. `coursera.org` → `coursero.org` is 1. |
| **Clustering** | Grouping items by similarity without being told the groups in advance. |
| **k-means** | A clustering method where you specify how many groups you want. |
| **Taxonomy** | The list of categories. Here: a file, `taxonomy.yaml`. |
| **Holdout** | Items set aside and hand-labelled, used only to *test* the system, never to train or tune it. |
| **Manifest** | A record of what has been processed and what hasn't, so a long job can stop and resume. |
| **Idempotent** | Safe to run twice. Re-running skips finished work instead of redoing or duplicating it. |
| **ZDR** | Zero Data Retention — a provider setting meaning they don't store what you send. |
| **Open-weight** | A model whose parameters are published, so it can be downloaded, inspected, and self-hosted. |

---

## Status board

| Section | Status | Reopened by |
|---|---|---|
| §1 Product form | 🟢 LOCKED | |
| §2 Acquisition | 🟡 OPEN | `decisions/002` (yt-dlp for top-ups) |
| §3 Extraction | 🟡 OPEN | `decisions/001` (hosted models allowed) |
| §4 Categorisation | 🟢 LOCKED | |
| §5 Search | 🟢 LOCKED | |
| §6 Models and where they run | 🟡 OPEN | `decisions/001`; model gate D14 still unresolved |
| §7 Evaluation | 🟢 LOCKED | |
| §8 System architecture | 🟡 OPEN | `decisions/001`, `decisions/002` |
| §9 Out of scope | 🟢 LOCKED | |
| §10 Definition of done | 🟢 LOCKED | |

**Reopening rule:** changing a LOCKED section requires an entry in `docs/decisions/` stating what changed, why, and which sections it invalidates. Those revert to open, get listed here, and must be re-locked before building resumes.

A section may only be marked 🟢 LOCKED once it has **written acceptance criteria**.

---

## Decisions

Numbered, permanent, never renumbered. When one is superseded, mark it *(superseded by Dn)* rather than editing it — the history is the point.

| | Decision | Why |
|---|---|---|
| D1 | **Browse, not converse.** The product is a browsable feed, not a chatbot. | Extraction is imperfect, so seeing the evidence beside the claim matters; a chatbot hides errors behind fluent prose. At 1,870 items, search is complete rather than a needle-hunt. Categories are inherently spatial. Search quality is machine-checkable; chatbot answer quality is not. |
| D2 | **Category feed.** Discovered categories are the primary navigation; each is a feed of cards. | Renders "emergent categories" as the thing you actually use. Degrades gracefully for both movies and text-heavy ML content, unlike a thumbnail grid which is useless for the latter. |
| D3 | **Captions are insufficient as a source of truth.** | Proven against this archive. A caption can be fluent, long, and never name its subject: *"Not only was this movie visually stunning, I loved it & so did Kuma"* — the film is *Flow*, named only on screen. Pattern-matching cannot detect a name that was never written. |
| D4 | **Categorisation weighs content similarity and owner corrections only.** | Source account rejected: 1,193 of 1,420 accounts appear exactly once, so it is signal for almost nothing. Hashtags rejected: demonstrably noisy — one reel tagged `#funny #comedy #memes` describes a Honda Civic Type R. |
| D5 | **Runs locally, reachable from phone via Tailscale.** | No authentication to build, no hosting bill, no personal data on anyone else's server. The repo publishes code; `data/` never leaves the machine. |
| D6 | *(amended by D18)* **Media is fetched through a vendor, never by DIY scraping.** | Vendors work logged-out through their own residential proxies, so the owner's account is never involved and cannot be banned. DIY carries reported 11–17% quarterly ban rates, and datacentre IPs are blocked on first request anyway. |
| D7 | **OCR reads. The language model interprets. Never the reverse.** | Vision-language models score ~45% F1 on non-semantic text (URLs, handles, codes) where humans score 97% — they guess from plausibility rather than pixels. OCR fails loudly and filterably (`c0urser@.0rg`); models fail silently and plausibly (a URL that is wrong by one word). |
| D8 | **VAD-gate before Whisper, always.** | Whisper fabricates fluent text on music-only audio — a documented training artefact. Ungated, this silently poisons hundreds of records in an archive full of music-backed text-slide reels. Empty is a valid answer, not a retry trigger. |
| D9 | *(superseded by D17)* **Open-weight models for all inference; Apple Vision excepted.** | Fusion and classification run `gpt-oss-20b` on Groq, not Gemini — once OCR owns the reading, fusion is a pure text task and an open model does it for the same money. Apple Vision OCR is closed-source but on-device, free, and transmits nothing, which satisfies the actual reasons for preferring open weights. |
| D10 | **Fine-tuning is out of v1.** | 1,870 examples sits at the viable floor and cannot beat an off-the-shelf model by enough to matter. Its original justification was portfolio depth, which no longer applies. Transcripts and summaries are kept in clean JSONL from day one, so a later fine-tune is a weekend rather than a rewrite. |
| D11 | **No thumbnails on cards.** | They help the ~486 movie items and do nothing for technical content, while costing storage, serving and layout work. Video files are retained, so this is cheap to revisit if text-only cards prove hard to scan. |
| D12 | **The fetch is the attrition probe.** No separate probing stage. | `memo23` charges only for successful retrievals and returns an error row otherwise, so alive/dead comes free as a side effect. A dedicated Bright Data pass would be an extra stage to learn the same thing. |
| D13 | **No written visual rules, no screenshot evidence.** The owner checks the UI manually. | He is the only user and the only person whose opinion of the design matters, so a written rulebook would be a proxy for a judgement he can make directly. Consequences: the `design-reviewer` agent is deleted (nothing to review) and `/checkpoint` drops its screenshot requirement. |
| D14 | **Model selection is a hard gate before any building.** | All six stages — fetch, OCR, speech, fusion, classification, embeddings — must be agreed in a dedicated discussion first. Recorded so it cannot be skipped by momentum. |
| D15 | **The owner can hide and edit any card; those actions are permanent.** | No acceptance criterion can detect "this passed every check and is still worthless to me." Hiding is a soft delete — the record stays, marked, so a re-run cannot resurrect it. Same authority as corrections. |
| D16 | **Non-English content is tagged, not special-cased.** | A `language` tag per record, exposed as a UI filter. Makes the Devanagari OCR gap visible and inspectable instead of a silent hole, and means cutting the Tesseract fallback degrades the product honestly rather than invisibly. |
| D17 | **Hosted models are allowed; the rule is the cheapest option that meets the ACs.** Owner prefers free/near-free; first-run target under ~$6. Supersedes D9. D7 and D8 unchanged. Per-stage choice still pending the D14 gate. | D9's real motive was cost, and hosted options are now as cheap or cheaper, while removing the overnight transcription run. Gives up: closed providers may see reel content; hosted models can change under us. See `decisions/001`. |
| D18 | **Vendor (`memo23`) for the bulk first run; logged-out, throttled `yt-dlp` allowed for top-ups (<100/month).** Logged-in scraping stays forbidden. Amends D6. | D6's ban-rate argument applies to logged-in scraping. Gives up: a single fetch path, and top-up rate limits land on the owner's home connection. See `decisions/002`. |

---

## §1. Product form

A **category feed**. The landing page lists discovered categories with counts. Selecting one opens a scrollable feed of cards — title, one-line summary, source account, date. Selecting a card opens a detail view showing the full extracted evidence (caption, on-screen text, speech transcript) and a link to the original reel. A search bar is present on every screen.

**Curation.** The owner can **hide** any card and **edit** its title, summary or category directly from the detail view. Hiding is a soft delete: the record stays in the database marked `hidden`, so a later pipeline run cannot resurrect it, and nothing is destroyed. This is the escape hatch for reels that survive every automated quality check and are still worthless to him — which no acceptance criterion can detect, because "worthless to me" is not a property of the content.

Hidden and edited items are written to `curation.jsonl` alongside corrections, and are authoritative in exactly the same way: no re-run overrides them.

The feel is a set of personal subreddits, not an admin dashboard.

**Why not a chatbot:** see D1. A conversational version remains a cheap later addition on top of the same search index, because grounding a chatbot requires exactly the index this product already builds.

**Acceptance criteria**

1. **AC-1.1** — From the landing page, every discovered category is reachable in one click, and each shows an item count matching the database.
   *Proof: Playwright test asserting link count equals category count in SQLite, and each count matches a `SELECT COUNT(*)`.*
2. **AC-1.2** — Every card links to a detail view that displays the reel's original Instagram URL plus **every non-empty extraction channel, each labelled with its source** (caption / on-screen text / speech). Empty channels are omitted rather than shown blank. No detail view renders with zero channels.
   *Proof: `tests/test_detail_view.py` over a sample of 20 records covering all channel combinations, asserting each non-empty channel appears with its source label and that a record with no channels cannot exist in the database.*
3. **AC-1.3 (curation)** — A hidden card disappears from every feed, every search result and every category count, and **stays hidden after a full pipeline re-run**. An edited title, summary or category likewise survives a re-run.
   *Proof: `tests/test_curation_persists.py` — hide one item and edit another, re-run extraction, classification and indexing, then assert the hidden item appears in no query result and the edited fields are unchanged.*

---

## §2. Acquisition — how content gets in

Two stages, in order.

**Stage 1 — the export (already done).** Meta's "Download Your Information" gives `message_1.json`: 2,254 messages total. The breakdown matters:

| | Count | Usable? |
|---|---|---|
| Shared items with full metadata | 1,889 (1,870 unique) | ✅ link + caption + source account |
| "Sent an attachment" with **no share data at all** | **358** | ❌ no link, no caption — unrecoverable |
| Typed text messages | ~7 | ⚠️ a few are real content ("Your lie in april") |

So **~16% of the archive is lost before we start**, and that sits on top of the link attrition below. The 358 are recorded as permanently unrecoverable and never retried.

The JSON is mojibake-encoded — UTF-8 bytes read as Latin-1 — and needs one decoding step.

**Stage 2 — fetching the media.** The `memo23/instagram-video-downloader` Apify actor, ~$3.74 for the corpus. It re-hosts the video files to permanent URLs, which matters because Instagram's own CDN links are signed and expire within hours — you cannot fetch a list today and download tomorrow. Files are pulled to local disk promptly.

**Attrition is measured by the fetch itself, not by a separate probe.** These permalinks are up to four years old; creators delete posts and accounts go private. Expect **60–80% of the 1,870 to still be alive**. Because `memo23` charges only for items it successfully retrieves and returns an error row for the rest, the fetch *is* the probe — a dedicated Bright Data pass would cost an extra stage to learn the same thing. Dead items are recorded with a reason and never retried.

*(Superseded: an earlier draft ran a free Bright Data probe first. Dropped as redundant — see D12.)*

**Acceptance criteria**

1. **AC-2.1** — `message_1.json` parses to exactly 1,870 unique records, each with a resolvable shortcode, decoded caption, and source account. Mojibake is corrected: no record contains the literal sequence `ð`.
   *Proof: `tests/test_export_parser.py`, asserting counts and running a Unicode sanity check over all captions.*
2. **AC-2.2** — Every one of the 1,870 ends in a terminal state — fetched, dead, or unrecoverable — with a recorded reason, and the pipeline never re-requests a terminal item.
   *Proof: `manifest.db` row count equals 1,870 with no `NULL` status; a second run issues zero fetch requests for terminal items, asserted by a request counter.*
3. **AC-2.3** — The 358 attachment-only messages are recorded as `unrecoverable` and are excluded from every downstream count, so corpus totals never silently include items that cannot exist.
   *Proof: `tests/test_export_parser.py` asserts the unrecoverable count and that the extraction queue excludes them.*

---

## §3. Extraction — the heart of the project

This is where the project succeeds or fails. Each reel becomes one record built from **three independent channels**, because no single channel is reliable.

| Channel | Source | Covers |
|---|---|---|
| **Caption** | The export, free | The creator's framing. Often useful, frequently withholds the subject entirely. |
| **On-screen text** | Apple Vision OCR on sampled frames | Titles, lists, URLs, course names, code. **Where the technical content lives.** |
| **Speech** | VAD → Whisper | What someone says. Talking-head reels, movie takes, explainers. |

**Frame sampling.** ffmpeg scores scene changes, and the top 5–8 frames are taken, plus frame zero (which usually carries the hook text and is often not a scene change), plus a fixed-interval floor for single-shot reels that produce no scene changes at all. Frames are deduplicated afterwards, because overlay text often persists across cuts.

**The fusion step.** An open-weight language model (`gpt-oss-20b`) receives caption + OCR text + transcript and produces a structured record: title, one-line summary, three to five content bullets, and extracted entities (film titles, URLs, course names). Its job is *organising and interpreting*, never *reading* — the OCR strings are stored verbatim and separately, and no model output overwrites them.

**The validation gate.** Every URL, @handle, and proper-noun title in the model's output must appear in that reel's OCR text within edit distance 2, or it is dropped and flagged. Edit distance 2 forgives OCR misreading `l` as `1`, but not a model substituting a different URL. This converts a trust problem into a test. It is the highest-value small piece of code in the project.

**Overlapping and ambiguous audio.** Three cases, handled differently:

| Case | Behaviour | Status |
|---|---|---|
| Speech over background music | VAD detects speech, Whisper transcribes it | ✅ works; this is normal training-distribution audio |
| Two people talking at once | Whisper transcribes but may merge or drop a speaker | ⚠️ accepted. Speaker separation (diarisation) is out of scope. Imperfect ≠ fabricated |
| **Music with singing** | VAD hears voice, Whisper transcribes song lyrics | ⚠️ **known gap** — lyrics enter the record as if they were content |

The third is real and unsolved without adding a music-detection model. v1 accepts it, flags lyric-like transcripts as low-confidence so they can be down-weighted, and **M0 measures how often it actually occurs**. If it is frequent, it earns a fix; if it is rare, it stays flagged and ignored.

**Languages.** Content is kept in its original language — nothing is translated, so nothing is lost in translation. **Every record carries a `language` tag**, detected per channel, and non-English records are flagged rather than special-cased. The tag is a visible filter in the UI, so the Devanagari gap below is something the owner can see and inspect rather than a silent quality hole.

| Channel | Non-English handling |
|---|---|
| Speech | Whisper large-v3-turbo is multilingual and handles Hindi well. No special path. |
| On-screen text | Apple Vision covers many scripts but **not Devanagari**. Hindi in Latin letters ("Hinglish") works — those are just Latin characters. Native Devanagari overlays are tagged `hi-Deva` and routed to a Tesseract `hin` second pass; if that is cut under time pressure, the tag still marks them as known-incomplete. |
| Search | BGE-M3 is multilingual, and its exact-term-matching half specifically rescues transliterated text that meaning-based matching misses. |

**Acceptance criteria**

1. **AC-3.1 (AC-FIDELITY)** — No stored record contains a URL, @handle, or proper-noun title absent from that reel's OCR output within edit distance 2.
   *Proof: `tests/test_fidelity_gate.py` feeds fusion outputs containing deliberately planted fake URLs and asserts every one is caught. The milestone fails if a planted fake survives.*
2. **AC-3.2** — On reels where VAD detects no voice at all, the transcript field is empty. Zero fabricated transcripts on a hand-checked sample of 50 instrumental-music-only reels.
   *Proof: `tests/test_vad_gate.py` with silent and instrumental-music audio fixtures; plus a recorded manual check of 50 reels in `docs/checkpoint_report.md`.*
   *Scope note: this criterion covers instrumental audio only. Sung vocals legitimately trigger VAD — see the known gap above. M0 reports the rate.*
3. **AC-3.3** — OCR output is stored with per-string confidence and timestamp, in a field no model writes to.
   *Proof: schema test asserting the `ocr_verbatim` column is written only by the OCR stage; `/prove-it` run attempting to overwrite it from the fusion stage and showing the failure.*

---

## §4. Categorisation

**Discovery and assignment are deliberately separate systems.** This is what makes categories emerge *and* stay stable.

1. **Discovery happens once.** k-means clustering over embeddings at several values of k; a language model names each cluster; the result is a draft taxonomy of roughly 12–20 categories.
2. **The owner edits that draft into `taxonomy.yaml`.** Each category has an immutable `id`, an editable display `name`, a description, three to five positive examples, and two to three boundary examples. **IDs never change**, so renaming a category never orphans the items in it.
3. **All ongoing assignment is classification against that frozen taxonomy** — the model picks a category and returns a confidence and a short rationale, with an explicit `other` option. New reels never trigger re-clustering.
4. **`other` is a quarantine pool** and the only thing ever re-clustered. When it exceeds 40 items, cluster just that pool and propose new categories. Promotion requires **≥15 items and the owner's approval**.
5. **Corrections are append-only and authoritative.** When the owner recategorises something, that label is never overridden by the classifier. Corrections serve as examples in the classification prompt, and a category absorbing many corrections *out of* it is a signal that it is too broad.

**Why not BERTopic**, the obvious off-the-shelf choice: on short multi-domain text — precisely this corpus — its clustering step labels a *majority* of documents as outliers, and its dimensionality-reduction step reshuffles category identities between runs. Categories that rename themselves weekly are worse than no categories.

**Acceptance criteria**

1. **AC-4.1 (AC-CAT)** — On `eval/holdout_v1.jsonl` (150 reels, stratified, every category floored at ~10 items): top-1 category matches the human label for **≥80%**; top-1-or-top-2 **≥92%**; no category with ≥10 holdout items has recall below **0.60**; Cohen's κ **≥0.60**; `other` **≤15%** of the corpus.
   *Proof: `/eval` prints all five numbers against the frozen holdout. Thresholds fail the build.*
2. **AC-4.2 (stability)** — Re-running the pipeline after ingesting new items changes **≤3%** of existing assignments and **zero** category IDs.
   *Proof: `tests/test_taxonomy_stability.py` runs assignment twice with 50 new items injected and diffs the results.*
3. **AC-4.3** — A recorded owner correction survives a full re-classification run.
   *Proof: `tests/test_corrections_authoritative.py` — write a correction, re-run classification, assert the corrected label is intact.*

*Cohen's κ measures agreement between the system and the human labels, corrected for the agreement you would get by guessing. 0.60–0.80 is "substantial", above 0.80 "strong". 80% rather than 90% because two humans labelling this kind of fuzzy personal taxonomy only agree at about that rate — claiming 90% against a single labeller would be fitting noise.*

---

## §5. Search

Hybrid retrieval over BGE-M3 embeddings: a dense component matching on meaning, and a sparse component matching on exact terms. The sparse half matters specifically because part of this archive is transliterated Hindi in Latin script, which every dense embedding model handles poorly and which no benchmark covers.

Storage is a numpy array plus a SQLite table. **2,000 items × 768 numbers is about 6 MB** — a vector database at this scale solves a problem that does not exist, and brute-force comparison is faster than the network call that would reach a database server.

Filters: category, source account, date range, language (D16). Hidden items (D15) are excluded from all results.

**Acceptance criteria**

1. **AC-5.1 (AC-SEARCH)** — On `eval/queries_v1.jsonl` (50 hand-written queries with relevance graded 2/1/0): Recall@10 **≥0.85**, nDCG@10 **≥0.60**, MRR@10 **≥0.70**, and **no query returns Recall@10 = 0**.
   *Proof: `/eval` prints all four. The zero-recall check is a hard-fail list of queries that must always work.*
2. **AC-5.2** — Searching for a reel whose caption never named its subject returns it in the top 10. The *Flow* case is a named canary.
   *Proof: that reel's shortcode is in the hard-fail canary list in `eval/queries_v1.jsonl`.*

*Recall@10 = "of the reels that should have matched, what fraction appeared in the top 10." MRR = how high up the first correct answer lands. nDCG = a score rewarding good ordering, not just presence. 50 queries is the established minimum for these numbers to be stable.*

---

## §6. Models and where they run

> ### ⛔ This section is a hard gate (D14)
>
> **No building starts until every row below is agreed in a dedicated discussion.** The table
> records the current recommendation, not a settled choice. Six decisions are open: media
> fetch, on-screen text, speech, fusion, classification, embeddings.

| Stage | Where | What | Open-weight | Cost |
|---|---|---|---|---|
| Media fetch (and attrition, D12) | Vendor | `memo23` Apify actor | n/a | **~$3.74** |
| On-screen text | **Local** | Apple Vision via `ocrmac`, `accurate` level | on-device, transmits nothing | **$0** |
| Speech | **Local** | Silero VAD → `mlx-whisper` large-v3-turbo | ✅ | **$0** |
| Fusion + classification | **Hosted** | `gpt-oss-20b` on Groq, ZDR enabled | ✅ | **~$0.60** |
| Embeddings | **Local** | BGE-M3 | ✅ | **$0** |

**Total: under $5 for the entire corpus.**

**The reasoning.** The pipeline is fetch-bound, not compute-bound — vendor rate limits dominate, so hosted inference speed buys nothing on stages that could run locally. Those stages happen to be exactly the ones handling raw personal content. So: local where the data is sensitive and speed is irrelevant, hosted only where 8 GB of RAM genuinely cannot hold a capable model.

**Hardware reality.** macOS holds 3–4 GB of the Mac's 8 GB. The real working budget is ~4 GB, so **pipeline stages run sequentially, never concurrently** — two model-holding processes at once is the defining failure mode on this machine. `faster-whisper`, the usual tutorial default, is CPU-only on Apple Silicon and must not be used. Local vision-language models are ruled out entirely: 16 GB is the floor for even a 3-billion-parameter model, and the compression that makes small ones fit is architecturally what destroys their ability to read small text.

**Acceptance criteria**

1. **AC-6.1** — Peak memory across the full pipeline stays under 5 GB, measured.
   *Proof: a memory-profiling run over 50 reels, recorded in `docs/checkpoint_report.md`.*
2. **AC-6.2** — No unit test makes a network call or loads a model.
   *Proof: `pytest` run with network disabled in CI; a socket-blocking fixture fails any test that attempts a connection.*

---

## §7. Evaluation — the scope contract

Two hand-labelled fixture files. **The owner produces these; they cannot be AI-generated**, because a system cannot generate the ground truth it is then graded against.

**`eval/holdout_v1.jsonl` — 150 reels.** Stratified by category in proportion to the corpus, with every category floored at ~10 items so per-category recall is measurable. Roughly 45–60 minutes of labelling. 150 rather than 100 because at 100 items the statistical margin of error is ±7 percentage points — too wide to distinguish a real regression from noise.

**`eval/queries_v1.jsonl` — 50 queries** the owner would actually type, each judged 2 (exactly this) / 1 (related) / 0 (irrelevant) over a pooled candidate set. Judging only the pooled top-10 from a few retrieval methods keeps this to ~3–4 hours.

**Both are quarantined.** Holdout items are never used as examples in any prompt, or the measurement becomes self-congratulatory.

**Storage:** committed with **hashed document IDs**, so the thresholds and results are public and auditable in CI while nobody can resolve an entry back to a specific reel the owner saved. A local lookup table maps hashes back for debugging.

**What we deliberately do not measure on:** silhouette score, C_v, NPMI and similar intrinsic coherence metrics. They correlate weakly with human judgement and are unreliable on embedding spaces. They are monitored as diagnostics and never fail a build.

**Acceptance criteria**

1. **AC-7.1** — `/eval` runs both fixture sets and prints every threshold in §4 and §5 with a pass/fail verdict, exiting non-zero on any failure.
   *Proof: run it; deliberately degrade the classifier and show it fails.*
2. **AC-7.2** — No holdout document ID appears in any prompt template or few-shot example.
   *Proof: `tests/test_holdout_quarantine.py` greps all prompt files against the holdout ID list.*

---

## §8. System architecture — what talks to what

Four layers. Data flows one direction; nothing downstream writes back upstream.

```
┌─ INGEST ───────────────────────────────────────────────────┐
│  message_1.json  →  parser  →  manifest.db                  │
│                                  (1,870 rows, one per reel) │
└─────────────────────────────────┬───────────────────────────┘
                                  │  reads "what still needs doing"
┌─ EXTRACT ────────────────────────▼──────────────────────────┐
│  memo23 fetch      → data/media/*.mp4  (+ alive/dead, free) │
│  ffmpeg            → sampled frames + audio track           │
│  Apple Vision OCR  → ocr_verbatim   ── never overwritten    │
│  VAD → Whisper     → transcript                             │
└─────────────────────────────────┬───────────────────────────┘
                                  │
┌─ UNDERSTAND ─────────────────────▼──────────────────────────┐
│  gpt-oss-20b fusion    → title, summary, bullets, entities  │
│  validation gate       → drops anything OCR didn't see      │
│  BGE-M3                → embeddings.npy                     │
│  classifier + taxonomy.yaml → category_id                   │
│  corrections.jsonl     → overrides, authoritative           │
└─────────────────────────────────┬───────────────────────────┘
                                  │
┌─ SERVE ──────────────────────────▼──────────────────────────┐
│  FastAPI  ──  reads SQLite + embeddings.npy                 │
│     ↓                                                        │
│  Web UI: category feed · detail view · search · correct     │
│     ↓                                                        │
│  Tailscale → phone                                          │
└──────────────────────────────────────────────────────────────┘
```

**Why this shape.** `manifest.db` sits between ingest and extract so that any stage can stop and resume — a fetch job over hundreds of items *will* be interrupted, and without a manifest every interruption means starting over. The one-directional flow means a bug in the UI can never corrupt extracted data. And `ocr_verbatim` being write-once by a single stage is what makes AC-FIDELITY enforceable rather than aspirational.

**Acceptance criteria**

1. **AC-8.1** — Killing any pipeline stage mid-run and restarting it processes only unfinished items and produces no duplicates.
   *Proof: `tests/test_manifest_resume.py` — kill at 50%, restart, assert final count and zero duplicates.*
2. **AC-8.2** — The serving layer cannot write to any extraction table.
   *Proof: an architectural boundary test asserting the API's database connection is read-only for those tables.*

---

## §9. Out of scope for v1

Named explicitly so that adding them later is a decision rather than a drift.

- **Fine-tuning** any model (D10). Training data is preserved in clean JSONL so this stays cheap to revisit.
- **A conversational interface.** The index this project builds is what a chatbot would need; adding one later is a layer, not a rewrite.
- **Automatic ingestion of new DMs.** v1 processes the export. Adding new reels means re-exporting and re-running, which is acceptable at a few hundred per year.
- **Multi-user anything.** One user, one machine.
- **Public deployment.** Tailscale only. No authentication layer is built because none is needed.
- **Recovering reels that no longer exist.** Dead permalinks are recorded as dead.
- **Video content beyond text.** No scene description, object detection, or face recognition. Text is the payload.

---

## §10. Definition of done for v1

The honest top-level target: **the owner opens this instead of scrolling the DM.**

Underneath it, concretely — v1 is done when all of the following are true:

1. Every surviving reel from the export has a record with at least one populated extraction channel.
2. AC-FIDELITY holds: no invented URLs, no fabricated transcripts on silent reels.
3. Categories exist, are stable across runs, and meet AC-CAT.
4. Search meets AC-SEARCH, including the *Flow* canary.
5. The owner can browse categories and search from his phone.
6. A correction made in the UI survives the next full re-classification.
7. `docs/VERIFICATION.md` records a real end-to-end run, including anything that failed.

---

## Build milestones — the definition of a "section"

The numbered sections above are *planning topics*, not equal units of work. This table is the operative definition: **one milestone = one checkpoint = one branch = one merge.**

| # | Milestone | Plan sections | Why this boundary |
|---|---|---|---|
| **Phase A — Foundation** | | | |
| 0 | **Extraction bake-off** | §2, §3, §6 | Exits on a written finding, not ACs. Answers what nothing else can: how many reels survive, whether OCR-led or model-led extraction wins on the hardest 50, and **how often sung vocals trigger the VAD gate**. Feeds the §6 model gate. ~$4 and an hour. |
| 1 | **Scaffold, kit adaptation, both guards proven** | §6, §7 | The Python check hook and the data-commit guard both break *silently* if wrong. Proven by deliberate failure, not assertion. |
| 2 | **Export parser as the scope contract** | §2 | Fully testable with zero ML and zero network. Getting the contract right is its own judgement call. |
| **Phase B — Extraction** | | | |
| 3 | **Vendor fetch + manifest** | §2, §8 | Resumability is the whole point; it belongs with the first long-running job. |
| 4 | **The verbatim layer** | §3 | OCR and VAD-gated speech. Two distinct review questions would make this unreviewable if merged with fusion. |
| 5 | **Fusion + fidelity gate** | §3 | The single most important correctness boundary in the project. |
| **Phase C — Understanding** | | | |
| 6 | **Taxonomy discovery** | §4 | Ends with an owner decision, not a merge-ready artefact. |
| 7 | **Classification + AC-CAT** | §4, §7 | Needs the 150-item holdout to exist first. The local labelling page (for the holdout and query judgements) is built in Wave 1 so it is ready by M6 — see `DESIGN_RATIONALE.md` §6. |
| **Phase D — Product** | | | |
| 8 | **Embeddings + search + AC-SEARCH** | §5, §7 | |
| 9 | **Category feed UI** | §1 | Visual quality is checked by the owner directly (D13), not by written rules or screenshots. |
| 10 | **Search UI + corrections + curation** | §1, §4 | Split from M9 because it is a second distinct review question. Includes hide/edit (D15). |
| 11 | **Tailscale + verification** | §10 | |

**Rules for this table**

- **Any boundary that can break silently goes in milestone 1**, not milestone 11.
- **Testing is distributed, not a phase.** Each test layer is assigned to the first milestone that can produce it.
- **Every promised deliverable appears in some row.** Work owned by no milestone silently never happens.
- **Split a milestone the moment it grows two distinct review questions.**

**Cuttable under time pressure, in this order:** Devanagari OCR fallback → the `other`-pool re-clustering loop → search filter chips. Nothing else is cut before quality is.

---

## How the build actually runs

> **Amended 2026-09-19** (`DESIGN_RATIONALE.md` §4): milestones that need no real data are
> built **in parallel waves** by subagents that own separate folders; the owner reviews their
> checkpoints and `checker` verdicts in batches and commits per wave. Steps 3–8 below still
> apply to every milestone; steps 1 and 10 happen once per wave.

| | Who | What |
|---|---|---|
| 1 | **Owner** | Create a branch for the milestone |
| 2 | **Owner** | Plan mode, name the milestone |
| 3 | Agent | `/plan-milestone <n>` — audit the plan sections, then write the implementation plan |
| 4 | **Owner** | ⭐ Review the ⚠️ *Needs your decision* section and the proof plan. Approve or redirect |
| 5 | Agent | Build. `check.sh` runs after every edit and blocks on failure |
| 6 | Agent | `/checkpoint` — evidence table, resume box, git commands |
| 7 | Agent | `checker` subagent verifies the ACs with no build context |
| 8 | Agent | `/code-review` on the diff; fix what it finds |
| 9 | **Owner** | ⭐ Open the app. Check the evidence table against `checker`'s verdicts. Ask `/prove-it` on anything load-bearing |
| 10 | **Owner** | Commit, push, merge |

**Steps 4 and 9 are the leverage points.** Step 4 is cheap to redirect — it is a paragraph, not code. Step 9 catches what automated checks structurally cannot: is this actually what was agreed, and does it look right.

**Why the agent runs `/code-review` (step 8) rather than the owner:** it comes before the owner's time is spent, so a milestone that review would reject never reaches step 9. The known weakness is that the agent reviewing its own diff carries the build narrative and is therefore blind to "this was the wrong approach" — which is precisely the gap `checker` fills at step 7 with no build context. The two together are stronger than either alone; neither replaces step 9.

---

## Verification — how to confirm v1 is actually done

Run against the real system. Record the result in `docs/VERIFICATION.md`, **including which steps failed.**

1. Fresh clone, install dependencies, run `pytest` → green, and no test makes a network call
2. Introduce a deliberate Python type error → `check.sh` **blocks**. Revert → green
3. `git add data/raw/message_1.json && git commit` → **blocked** by the pre-commit hook
4. Plant a fabricated URL in a fusion output → the fidelity gate **catches it**
5. Pick three music-only reels → the speech field is empty, not invented
6. `/eval` → AC-CAT and AC-SEARCH numbers printed against the frozen fixtures
7. Open the app **on the phone** over Tailscale → land on the category list
8. Search for the *Flow* reel, whose caption never named the film → appears in the top 10
9. Recategorise an item, refresh, re-run classification → the correction persists
10. `checker` subagent verifies every AC with no build narrative

---

## Open questions

- Exact split of the `other` category once real data exists — the 15% ceiling in AC-CAT is a target, not yet an observation.
- Whether the Devanagari OCR fallback is needed at all, or whether transliterated Latin-script Hindi covers the real cases. M0 should indicate this.
- How large the "no speech, no on-screen text, uninformative caption" bucket is. If it is meaningful, a vision-model fallback enters scope as a later phase; if it is 30 items, it never does.
