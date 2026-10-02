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
> **Last completed:** Wave 0 + Wave 1 built and tested on fake data (452 tests, clean).
> M0 judged: Gemini 31, pipeline 1 5, tie 14. Owner decisions 2026-10-01: Gemini Flash-Lite
> (paid, standard) reads the reel with local OCR **and** the Whisper transcript in its prompt
> as evidence (D19); bulk videos via yt-dlp, Apify for carousels (D20); unhide kept (D21);
> AC-3.1 becomes "confirmed or visibly flagged, titles checked word by word"; queries file
> committed; 36% unreadable text accepted, re-measured on the real run.
> **Next:** Wave 2, starting with the fetch (yt-dlp videos, Apify carousels). While it runs:
> build the Gemini card writer, the gate changes (flag not drop, word-by-word titles), extra
> categories, category editing and Links & titles on fake data; draft the per-reel-type
> prompt with the owner, then the owner judges it on 35 random reels (AC-3.4: ≥30 good).
> **All plan sections LOCKED** (2026-10-01). Classification model chosen at M7.
> **Before labelling:** back up `data/eval_salt` and `data/eval_lookup.json` off this machine.

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
| §1 Product form | 🟢 LOCKED | Re-locked 2026-10-01 after `decisions/007`, `008` |
| §2 Acquisition | 🟢 LOCKED | Re-locked 2026-10-01 after `decisions/002`, `006` |
| §3 Extraction | 🟢 LOCKED | Re-locked 2026-10-01 after `decisions/001`, `004`, `005`; AC-3.1 rewritten |
| §4 Categorisation | 🟢 LOCKED | Re-locked 2026-10-01 after `decisions/008` |
| §5 Search | 🟢 LOCKED | |
| §6 Models and where they run | 🟢 LOCKED | Re-locked 2026-10-01; D14 gate closed (`decisions/005`, `006`); classification model chosen at M7 by owner decision |
| §7 Evaluation | 🟢 LOCKED | |
| §8 System architecture | 🟢 LOCKED | Re-locked 2026-10-01 after `decisions/001`, `002`, `005`, `006` |
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
| D7 | *(superseded by D19)* **OCR reads. The language model interprets. Never the reverse.** | Vision-language models score ~45% F1 on non-semantic text (URLs, handles, codes) where humans score 97% — they guess from plausibility rather than pixels. OCR fails loudly and filterably (`c0urser@.0rg`); models fail silently and plausibly (a URL that is wrong by one word). |
| D8 | **VAD-gate before Whisper, always.** | Whisper fabricates fluent text on music-only audio — a documented training artefact. Ungated, this silently poisons hundreds of records in an archive full of music-backed text-slide reels. Empty is a valid answer, not a retry trigger. |
| D9 | *(superseded by D17)* **Open-weight models for all inference; Apple Vision excepted.** | Fusion and classification run `gpt-oss-20b` on Groq, not Gemini — once OCR owns the reading, fusion is a pure text task and an open model does it for the same money. Apple Vision OCR is closed-source but on-device, free, and transmits nothing, which satisfies the actual reasons for preferring open weights. |
| D10 | **Fine-tuning is out of v1.** | 1,870 examples sits at the viable floor and cannot beat an off-the-shelf model by enough to matter. Its original justification was portfolio depth, which no longer applies. Transcripts and summaries are kept in clean JSONL from day one, so a later fine-tune is a weekend rather than a rewrite. |
| D11 | *(note: media is deleted after v1, see DESIGN_RATIONALE §8, so revisiting this later means re-downloading)* **No thumbnails on cards.** | They help the ~486 movie items and do nothing for technical content, while costing storage, serving and layout work. Video files are retained, so this is cheap to revisit if text-only cards prove hard to scan. |
| D12 | **The fetch is the attrition probe.** No separate probing stage. | `memo23` charges only for successful retrievals and returns an error row otherwise, so alive/dead comes free as a side effect. A dedicated Bright Data pass would be an extra stage to learn the same thing. |
| D13 | **No written visual rules, no screenshot evidence.** The owner checks the UI manually. | He is the only user and the only person whose opinion of the design matters, so a written rulebook would be a proxy for a judgement he can make directly. Consequences: the `design-reviewer` agent is deleted (nothing to review) and `/checkpoint` drops its screenshot requirement. |
| D14 | **Model selection is a hard gate before any building.** | All six stages — fetch, OCR, speech, fusion, classification, embeddings — must be agreed in a dedicated discussion first. Recorded so it cannot be skipped by momentum. |
| D15 | *(amended by D21)* **The owner can hide and edit any card; those actions are permanent.** | No acceptance criterion can detect "this passed every check and is still worthless to me." Hiding is a soft delete — the record stays, marked, so a re-run cannot resurrect it. Same authority as corrections. |
| D16 | **Non-English content is tagged, not special-cased.** | A `language` tag per record, exposed as a UI filter. Makes the Devanagari OCR gap visible and inspectable instead of a silent hole, and means cutting the Tesseract fallback degrades the product honestly rather than invisibly. |
| D17 | **Hosted models are allowed; the rule is the cheapest option that meets the ACs.** Owner prefers free/near-free; first-run target under ~$6. Supersedes D9. D7 and D8 unchanged. Per-stage choice still pending the D14 gate. | D9's real motive was cost, and hosted options are now as cheap or cheaper, while removing the overnight transcription run. Gives up: closed providers may see reel content; hosted models can change under us. See `decisions/001`. |
| D18 | *(amended by D20)* **Vendor (`memo23`) for the bulk first run; logged-out, throttled `yt-dlp` allowed for top-ups (<100/month).** Logged-in scraping stays forbidden. Amends D6. | D6's ban-rate argument applies to logged-in scraping. Gives up: a single fetch path, and top-up rate limits land on the owner's home connection. See `decisions/002`. |
| D19 | **Gemini Flash-Lite reads the reel (video, audio, carousel slides), with the reel's local OCR text in its prompt.** OCR still runs locally and `ocr_verbatim` stays write-once. Supersedes D7. Settles the OCR and fusion rows of the §6 gate. | Owner's blind M0 judgement: Gemini 31, pipeline 1 5, tie 14; wrong links on only 2/50 Gemini cards. OCR text restores small print Gemini's 1-frame-per-second sampling misses. Gives up: the guarantee that only OCR reads; all reels go to Google; ~$3.30–3.80 vs ~$0.75. See `decisions/005`. |
| D20 | **Bulk run: logged-out, throttled yt-dlp for the 1,714 videos; Apify only for the 156 carousels and for videos yt-dlp fails on.** ~$2.85. Amends D18. | M0: Apify really costs ~$23.24 for the corpus; yt-dlp fetched 97% of videos. Gives up: rate limits on the owner's connection, ~a day of runtime, two fetch paths. See `decisions/006`. |
| D21 | **Hiding survives every pipeline re-run, and the owner can reverse it.** Amends D15's "permanent". | Hiding was already a soft delete; unhide recovers a mis-tap. Gives up: a hide is no longer final. See `decisions/007`. |
| D22 | **Extra categories.** The classifier assigns one main category and is graded on it; the owner can add a card to any other categories by hand. | Full control without rebuilding the grading. Gives up: extras are invisible to the grading. See `decisions/008`. |
| D23 | **The category list is editable from the app: rename, add, delete.** Delete moves its cards to a chosen category or `other`, and remaps holdout labels. Stored append-only. | The owner's fallback when the model is wrong. Gives up: the taxonomy is no longer frozen after one edit. See `decisions/008`. |
| D24 | **Every card shows a Links & titles section** — extracted URLs (clickable), @handles, titles, unconfirmed ones marked. | Links were stored but only visible inside raw on-screen text. See `decisions/008`. |

---

## §1. Product form

*Rewritten and re-locked 2026-10-01 after `decisions/007` and `decisions/008`.*

A **category feed**. The landing page lists the categories with counts. Selecting one opens a scrollable feed of cards — title, then a provenance line (link to the original reel, source account, date saved), then the summary. Selecting a card opens a detail view: title, provenance and "Open original" link, warning tags (non-English, unreadable on-screen text, lyrics, unconfirmed names), summary, bullets, a **Links & titles** section (D24) listing every extracted URL (clickable), @handle and title with unconfirmed ones marked, and the full evidence underneath (caption, on-screen text, speech transcript). A search bar is present on every screen.

**Curation — the owner has the final say over every card.** From the detail view he can edit the title or summary, change the card's main category, add it to or remove it from any number of **extra categories** (D22), and **hide** it. Hiding is a soft delete: the record stays, a pipeline re-run cannot bring it back, and the owner can reverse it from the Hidden page (D21). From a **Categories** page he can rename, add and delete categories (D23); deleting moves every card in it to a category he picks, or to `other`.

Every owner action is written to an append-only log next to the database (`curation.jsonl`, `corrections.jsonl`, and a category-edits log) and laid over the database whenever cards are read. No re-run overrides them.

The feel is a set of personal subreddits, not an admin dashboard.

**Why not a chatbot:** see D1. A conversational version remains a cheap later addition on top of the same search index, because grounding a chatbot requires exactly the index this product already builds.

**Acceptance criteria**

1. **AC-1.1** — From the landing page, every category is reachable in one click, and each shows an item count matching the database, counting a card once in each category it belongs to (main or extra), excluding hidden cards.
   *Proof: `tests/serve/test_landing.py`, extended in Wave 2 for extra categories.*
2. **AC-1.2** — Every card links to a detail view that displays the reel's original Instagram URL, **every non-empty extraction channel labelled with its source** (empty channels omitted, never shown blank), and — when the card has any — a Links & titles section in which every URL is a working link and every unconfirmed entry is visibly marked. No detail view renders with zero channels.
   *Proof: `tests/serve/test_detail_view.py` over all 27 fake cards; Links & titles assertions added in Wave 2.*
3. **AC-1.3 (curation)** — A hidden card disappears from every feed, every search result and every category count, and stays hidden after a full pipeline re-run until the owner unhides it. An edited title, summary, main category or extra category likewise survives a re-run.
   *Proof: `tests/serve/test_curation.py` and `tests/contract/test_cards_and_curation.py` on fake data; repeated on the real corpus after the first classification re-run in Wave 2.*
4. **AC-1.4 (category editing)** — Renaming a category changes its name everywhere and its id nowhere. An added category can be chosen for any card and is in the list the classifier uses next run. Deleting a category leaves **zero** cards, extra-category memberships or holdout labels pointing at it. All three survive a re-run.
   *Proof: `tests/serve/test_categories.py`, written in Wave 2.*

---

## §2. Acquisition — how content gets in

*Rewritten and re-locked 2026-10-01 after `decisions/002` and `decisions/006`.*

Two stages, in order.

**Stage 1 — the export (done).** Meta's "Download Your Information" gives `message_1.json`: 2,254 messages total. The breakdown matters:

| | Count | Usable? |
|---|---|---|
| Shared items with full metadata | 1,889 (1,870 unique) | ✅ link + caption + source account |
| "Sent an attachment" with **no share data at all** | **358** | ❌ no link, no caption — unrecoverable |
| Typed text messages | ~7 | ⚠️ a few are real content ("Your lie in april") |

So **~16% of the archive is lost before we start**, on top of the link attrition below. The 358 are recorded as permanently unrecoverable and never retried. The JSON is mojibake-encoded — UTF-8 bytes read as Latin-1 — and needs one decoding step.

**Stage 2 — fetching the media (D20).** Two fetchers, chosen by what each handles:

| Media | Fetcher | Why |
|---|---|---|
| 1,714 videos (`/reel/`) | Logged-out yt-dlp, throttled 10–30 s per item, no cookies | M0: 34 of 35 videos (97%). Free. The owner's account is never involved. |
| 156 carousels (`/p/`) | `memo23` Apify actor | yt-dlp cannot fetch carousels (M0: 0 of 15). Apify got 50 of 50. |
| Any video yt-dlp fails on | `memo23` Apify actor | A yt-dlp failure is never treated as proof the reel is gone. |

Only Apify's verdict can mark an item `dead`, because `dead` is terminal and a wrong one permanently loses a live reel. yt-dlp stops for the batch after 5 consecutive login-wall or rate-limit errors, leaving the rest pending. **Cost ≈ $2.85** (M0 invoice rates); about a day of run time; ≈ 8.7 GB of media against ~14 GB free. Instagram's CDN links expire within hours, so files are downloaded to local disk as soon as they are resolved.

**Attrition is measured by the fetch itself** (D12). The plan's estimate is that **60–80% of the 1,870 are still alive**; M0 cannot confirm it, because its sample was drawn from reels that still resolved. Dead items are recorded with a reason and never retried.

**Acceptance criteria**

1. **AC-2.1** — `message_1.json` parses to exactly 1,870 unique records, each with a resolvable shortcode (1,714 `/reel/` + 156 `/p/`, measured 2026-09-19). Caption and source account are decoded where present; the export lacks them on a handful of shares, which are counted, not invented. 10 items are recorded as `external` and excluded from the 1,870: 8 links to non-Instagram hosts, 1 share whose `link` key is absent entirely, and 1 Instagram profile share. A further 7 items are `note`. Mojibake is corrected: no record contains the literal sequence `ð`.
   *Proof: `tests/ingest/test_export_parser.py`, asserting counts and running a Unicode sanity check over all captions.*
2. **AC-2.2** — Every one of the 1,870 ends in a terminal state — fetched, dead, or unrecoverable — with a recorded reason, and the pipeline never re-requests a terminal item.
   *Proof: `fetch_status` in `data/kb.db` has 1,870 rows with no `NULL` status after the run; `tests/fetch/test_manifest.py` and `tests/fetch/test_manifest_resume.py` assert a second run issues zero requests for terminal items.*
3. **AC-2.3** — The 358 attachment-only messages are recorded as `unrecoverable` and are excluded from every downstream count.
   *Proof: `tests/ingest/test_export_parser.py` asserts the count and that the extraction queue excludes them.*
4. **AC-2.4 (routing)** — Carousels are never sent to yt-dlp; every video yt-dlp fails on is retried through Apify before it can be marked `dead`; and no item is marked `dead` on yt-dlp's word alone.
   *Proof: a routing test in `tests/fetch/`, written in Wave 2, using fake fetchers that fail on chosen items.*

---

## §3. Extraction — the heart of the project

*Rewritten and re-locked 2026-10-01 after `decisions/004` and `decisions/005`. D7 is superseded by D19.*

This is where the project succeeds or fails. Each reel becomes one card written by a model that **watches the reel itself**, checked against **three independent text channels** gathered beforehand.

| Input | Source | What it gives |
|---|---|---|
| **The reel** | Gemini 3.5 Flash-Lite watching the video — one frame per second plus the audio — or every carousel slide | The picture, the speech, the scene. What M0 showed pipeline 1 could never see. |
| **Caption** | The export, free | The creator's framing. Often useful, frequently withholds the subject entirely. |
| **On-screen text** | Apple Vision OCR on sampled frames, local | Exact text, including small print Gemini's low-resolution frames miss and text shown for under a second. Stored verbatim. |
| **Speech** | Silero VAD → Groq Whisper large-v3-turbo | A word-for-word transcript, multilingual. Stored and searchable. |

**Frame sampling (for OCR).** ffmpeg scores scene changes, and the top 5–8 frames are taken, plus frame zero (which usually carries the hook text), plus a fixed-interval floor for single-shot reels with no scene changes. Frames are deduplicated afterwards.

**Writing the card (D19).** Gemini receives the video (or slides), the caption, the OCR text and the transcript. It is told to use the OCR text and transcript to recover anything it could not read or hear clearly, and to check every link, @handle and title against them before writing. It returns a title, a one-line summary, three to five bullets, the entities (URLs, handles, titles) and a language tag. The instructions differ by kind of reel — a movie list, a course or resource, a career tip, a scene — and are drafted with the owner from his M0 notes. `ocr_verbatim` is written by the OCR stage only; no model output ever overwrites it.

**Before the corpus run**, the owner judges the prompt on **35 randomly drawn reels**, with notes. Random, not hard-selected: M0 measured the hard cases; this measures the typical reel.

**The fidelity gate.** Every URL, @handle and title on the card — in the entity list and in the prose — is checked against that reel's on-screen text:
- URLs and handles: within a length-scaled edit budget (0 edits under 4 characters, 1 up to 7, 2 above), with the domain suffix matching what was on screen, and exact characters required for any non-ASCII lookalike.
- Titles: **word by word** — every word of the title must appear on screen, in order, across consecutive lines. This confirms a title like "The Long Quiet Road" shown as "THE LONG" and "QUIET ROAD" on two lines, and still rejects an invented string glued together across a line break.

Anything not confirmed is **kept and visibly marked "unconfirmed"**, never silently removed. Since Gemini now reads more than OCR does, deleting would throw away correct links: in M0, 5 of the 7 URLs OCR could not confirm were real text OCR had failed to read.

**Overlapping and ambiguous audio.**

| Case | Behaviour | Status |
|---|---|---|
| Speech over background music | VAD detects speech, Whisper transcribes it | ✅ works |
| Two people talking at once | Whisper may merge or drop a speaker | ⚠️ accepted. Imperfect ≠ fabricated |
| **Music with singing** | Whisper transcribes the lyrics | ⚠️ known gap. M0: 3 of 25 reels with speech (12%). Flagged as low-confidence and accepted. |

**Languages.** Nothing is translated. **Every card carries a `language` tag**, shown as a filter. Apple Vision cannot read Devanagari, and the Tesseract fallback was cut (DESIGN_RATIONALE #3), but Gemini reads Devanagari from the frames itself, so that gap now affects only the fidelity gate's ability to confirm a name, not the card. M0 found **36% of reels had some on-screen text OCR could not read**, mostly dense carousels. The owner accepted this on 2026-10-01; it is re-measured on the real run.

**Known limit.** The gate checks on-screen text only. A title heard only in speech — the *Flow* case — is shown on the card but marked unconfirmed.

**Acceptance criteria**

1. **AC-3.1 (AC-FIDELITY)** — Every URL, @handle and proper-noun title on a stored card, in its entities and in its prose, is either confirmed against that reel's on-screen text by the rules above, or carries a visible "unconfirmed" mark. None is silently removed; none is shown unmarked without confirmation.
   *Proof: `tests/fusion/test_fidelity_gate.py` and `tests/fusion/test_fidelity_short_and_prose.py`, extended in Wave 2: every planted fake ends up marked, a real title split across two OCR lines is confirmed, and a string glued across a line break is not.*
   *(Rewritten 2026-10-01. The previous wording — "no stored record contains an unconfirmed entity" — was not met, `decisions/004`; it is replaced, not quietly relaxed, because the owner chose to see unconfirmed names rather than lose correct ones.)*
2. **AC-3.2** — On reels where VAD detects no voice at all, the transcript field is empty. Zero fabricated transcripts on a hand-checked sample of 50 instrumental-music-only reels.
   *Proof: `tests/test_vad_gate.py` with silent and instrumental-music fixtures, written in Wave 2 (M4); plus a recorded manual check of 50 reels in `docs/checkpoint_report.md`.*
3. **AC-3.3** — OCR output is stored with per-string confidence and timestamp, in a field no model writes to.
   *Proof: `tests/contract/test_schema_boundaries.py` and `tests/fusion/test_ownership_boundary.py`.*
4. **AC-3.4 (the prompt)** — Before the corpus run, the owner judges the card-writing prompt on 35 randomly drawn reels, and at least **30 of 35** are judged acceptable. Otherwise the prompt is revised and judged again on a fresh draw.
   *Proof: the owner's judgements file and the count, recorded in `docs/checkpoint_report.md`.*

---

## §4. Categorisation

*Rewritten and re-locked 2026-10-01 after `decisions/008`.*

**Discovery and assignment are deliberately separate systems.** This is what makes categories emerge *and* stay stable.

1. **Discovery happens once.** k-means clustering over embeddings at several values of k; a language model names each cluster; the result is a draft taxonomy of roughly 12–20 categories.
2. **The owner edits that draft into `taxonomy.yaml`.** Each category has an immutable `id`, an editable display `name`, a description, three to five positive examples, and two to three boundary examples. **IDs never change**, so renaming a category never orphans the items in it.
3. **After that, the owner can still edit the list from the app (D23)**: rename, add, delete. Delete moves every card and holdout label in the category to one he picks, or to `other`. These edits are stored append-only and laid over `taxonomy.yaml`, so a pipeline re-run never undoes them. A new category joins the list the classifier uses; existing reels move into it by hand or by a re-classification run.
4. **Assignment is classification against the current list** — the model picks **one main category** and returns a confidence and a short rationale, with an explicit `other` option. New reels never trigger re-clustering.
5. **Extra categories are the owner's (D22).** He can add a card to any number of other categories. They appear in feeds, counts and the search category filter, and are never graded.
6. **`other` is a quarantine pool** and the only thing ever re-clustered. When it exceeds 40 items, cluster just that pool and propose new categories. Promotion requires **≥15 items and the owner's approval**.
7. **Corrections are append-only and authoritative.** A main category the owner sets is never overridden by the classifier. Corrections serve as examples in the classification prompt, and a category absorbing many corrections *out of* it is a signal that it is too broad.

**Why not BERTopic**, the obvious off-the-shelf choice: on short multi-domain text — precisely this corpus — its clustering step labels a *majority* of documents as outliers, and its dimensionality-reduction step reshuffles category identities between runs. Categories that rename themselves weekly are worse than no categories.

**Acceptance criteria**

1. **AC-4.1 (AC-CAT)** — On `eval/holdout_v1.jsonl` (150 reels, stratified, every category floored at ~10 items), measured on the **main category only**: top-1 matches the human label for **≥80%**; top-1-or-top-2 **≥92%**; no category with ≥10 holdout items has recall below **0.60**; Cohen's κ **≥0.60**; `other` **≤15%** of the corpus.
   *Proof: `python -m reelkb.eval` prints all five numbers against the frozen holdout and exits non-zero on a miss (`tests/eval/test_main.py`, `tests/eval/test_runner.py`).*
2. **AC-4.2 (stability)** — Re-running the pipeline after ingesting new items changes **≤3%** of existing main-category assignments and **zero** category IDs. Owner edits are not pipeline changes and are excluded.
   *Proof: `tests/test_taxonomy_stability.py`, written in Wave 2 (M7): assignment twice with 50 new items injected, results diffed.*
3. **AC-4.3** — A recorded owner correction, extra category or category edit survives a full re-classification run.
   *Proof: `tests/test_corrections_authoritative.py`, written in Wave 2 (M7).*

*Cohen's κ measures agreement between the system and the human labels, corrected for the agreement you would get by guessing. 0.60–0.80 is "substantial", above 0.80 "strong". 80% rather than 90% because two humans labelling this kind of fuzzy personal taxonomy only agree at about that rate — claiming 90% against a single labeller would be fitting noise.*

---

## §5. Search

Hybrid retrieval over BGE-M3 embeddings: a dense component matching on meaning, and a sparse component matching on exact terms. The sparse half matters specifically because part of this archive is transliterated Hindi in Latin script, which every dense embedding model handles poorly and which no benchmark covers.

Storage is a numpy array plus a SQLite table. **2,000 items × 1,024 numbers is about 8 MB** *(corrected 2026-09-19: BGE-M3's dense vectors are 1,024-dimensional, not 768; the conclusion is unchanged)* — a vector database at this scale solves a problem that does not exist, and brute-force comparison is faster than the network call that would reach a database server.

Filters: category, source account, date range, language (D16). Hidden items (D15) are excluded from all results.

**Acceptance criteria**

1. **AC-5.1 (AC-SEARCH)** — On `eval/queries_v1.jsonl` (50 hand-written queries with relevance graded 2/1/0): Recall@10 **≥0.85**, nDCG@10 **≥0.60**, MRR@10 **≥0.70**, and **no query returns Recall@10 = 0**.
   *Proof: `/eval` prints all four. The zero-recall check is a hard-fail list of queries that must always work.*
2. **AC-5.2** — Searching for a reel whose caption never named its subject returns it in the top 10. The *Flow* case is a named canary.
   *Proof: that reel's shortcode is in the hard-fail canary list in `eval/queries_v1.jsonl`.*

*Recall@10 = "of the reels that should have matched, what fraction appeared in the top 10." MRR = how high up the first correct answer lands. nDCG = a score rewarding good ordering, not just presence. 50 queries is the established minimum for these numbers to be stable.*

---

## §6. Models and where they run

*Rewritten and re-locked 2026-10-01. The D14 model gate is closed by `decisions/005` and `decisions/006`; the classification model is deliberately chosen at M7 (owner, 2026-10-01), once the taxonomy it classifies against exists.*

| Stage | Where | What | Cost (corpus) |
|---|---|---|---|
| Media fetch | Local + vendor | Logged-out yt-dlp for videos; `memo23` Apify for carousels and yt-dlp failures (D20) | **≈ $2.85** |
| On-screen text | **Local** | Apple Vision via `ocrmac`, `accurate` level | **$0** |
| Speech | Local VAD, hosted transcription | Silero VAD → Groq `whisper-large-v3-turbo`, free tier | **$0** (~2 days at 8 h of audio/day; ≈ $0.65 if paid) |
| Card writing | **Hosted** | Gemini 3.5 Flash-Lite, **paid tier, standard** (D19) | **≈ $3.30–3.80** |
| Classification | Hosted | Chosen at M7 — a text-only task | ≈ $0.60 |
| Embeddings | **Local** | BGE-M3 | **$0** |

**Total ≈ $6.75–7.25 for the first run.** This is **over D17's ~$6 target by about $1** — recorded as a miss, not hidden. The owner chose standard Gemini over batch (~$1.70 cheaper, results within a day) on 2026-10-01, knowing this. Monthly top-ups of under 100 reels cost about $0.20.

**What leaves the machine.** Every reel's video and audio goes to Google. On the paid tier, Google's terms say prompts and files are **not used to improve its products** and are logged for a limited time for abuse detection only; on the free tier they would be used for training and could be human-reviewed — which is why the paid tier was chosen. Audio goes to Groq for transcription. Carousels and failed videos are fetched through Apify.

**The reasoning.** Local wherever a free local tool is good enough — OCR, voice detection, embeddings. Hosted where only a hosted model can do the job: understanding the whole reel. M0 showed that capability, not cost, decides the result: watching the reel won 31 to 5.

**Hardware reality.** macOS holds 3–4 GB of the Mac's 8 GB. The real working budget is ~4 GB, so **pipeline stages run sequentially, never concurrently** — two model-holding processes at once is the defining failure mode on this machine. `faster-whisper` is CPU-only on Apple Silicon and must not be used. Local vision-language models are ruled out entirely: 16 GB is the floor for even a 3-billion-parameter model.

**Acceptance criteria**

1. **AC-6.1** — Peak memory across the full pipeline stays under 5 GB, measured.
   *Proof: a memory-profiling run over the real pipeline, recorded in `docs/checkpoint_report.md` (M11; M0 recorded an early number).*
2. **AC-6.2** — No unit test makes a network call or loads a model **from within the test process**. *(Scope stated honestly 2026-09-19: the guards patch this process's sockets and imports, so a test that shells out to another program could still reach the network. No test does.)*
   *Proof: the socket and import guards in `tests/conftest.py`, proven by `tests/test_guards.py`, and run on every push by CI.*

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

*Rewritten and re-locked 2026-10-01 after `decisions/001`, `002`, `005`, `006`.*

Four layers, one database (`data/kb.db`), each stage owning its own tables. Data flows one direction; nothing downstream writes back upstream.

```
┌─ INGEST ───────────────────────────────────────────────────────┐
│  message_1.json  →  parser  →  items  (1,870 reels)             │
└──────────────────────────────────┬──────────────────────────────┘
                                   │  reads "what still needs doing"
┌─ EXTRACT ─────────────────────────▼─────────────────────────────┐
│  yt-dlp (videos) / Apify (carousels, failures) → data/media/    │
│  ffmpeg            → sampled frames + audio track                │
│  Apple Vision OCR  → ocr_verbatim   ── never overwritten         │
│  VAD → Groq Whisper → transcript                                 │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌─ UNDERSTAND ──────────────────────▼─────────────────────────────┐
│  Gemini  ← video/slides + caption + OCR text + transcript       │
│          → title, summary, bullets, entities, language          │
│  fidelity gate   → confirms each link/handle/title, or marks it │
│  BGE-M3          → embeddings.npy + sparse weights              │
│  classifier + taxonomy → one main category                      │
│  owner logs (curation, corrections, category edits)             │
│                  → laid over everything, authoritative          │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
┌─ SERVE ───────────────────────────▼─────────────────────────────┐
│  FastAPI  ──  read-only connection to kb.db + embeddings        │
│  Web UI: categories · feed · card · search · curation           │
│  Tailscale → phone                                               │
└──────────────────────────────────────────────────────────────────┘
```

**Why this shape.** The `fetch_status` table sits between ingest and extract so any stage can stop and resume — a day-long fetch *will* be interrupted, and without it every interruption means starting over. The one-directional flow means a bug in the UI can never corrupt extracted data. `ocr_verbatim` being write-once by a single stage keeps an untouchable record of what was actually on screen, which the fidelity gate checks the card against. Owner edits live outside the database in append-only logs, so no pipeline stage can reach them.

**Acceptance criteria**

1. **AC-8.1** — Killing any pipeline stage mid-run and restarting it processes only unfinished items and produces no duplicates.
   *Proof: `tests/fetch/test_manifest_resume.py` (fetch) and `tests/fusion/test_fusion_stage.py` (card writing); the OCR and speech stages get the same test in Wave 2 (M4).*
2. **AC-8.2** — The serving layer cannot write to any extraction table.
   *Proof: `tests/serve/test_readonly.py` — the app's connection is opened read-only, and a write attempt fails.*

---

## §9. Out of scope for v1

Named explicitly so that adding them later is a decision rather than a drift.

- **Fine-tuning** any model (D10). Training data is preserved in clean JSONL so this stays cheap to revisit.
- **A conversational interface.** The index this project builds is what a chatbot would need; adding one later is a layer, not a rewrite.
- **Automatic ingestion of new DMs.** v1 processes the export. Adding new reels means re-exporting and re-running, which is acceptable at a few hundred per year.
- **Multi-user anything.** One user, one machine.
- **Public deployment.** Tailscale only. No authentication layer is built because none is needed.
- **Recovering reels that no longer exist.** Dead permalinks are recorded as dead.
- **External links and typed notes** (17 items, measured: 10 `external` = 8 non-Instagram links + 1 link-less share + 1 profile share; 7 `note`). Recorded in the manifest as `external`/`note`; a v2 pipeline surfaces them under their own tag. See `decisions/003`.
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
| 0 | **Extraction bake-off** | §2, §3, §6 | Exits on a written finding, not ACs. On 50 hard items (including ~10 `/p/` posts and the *Flow* reel) it measures: survival via `memo23`; whether logged-out yt-dlp works; OCR + Groq Whisper + `gpt-oss-120b` vs Gemini Flash-Lite on subject naming and URL accuracy; **the sung-vocal rate**; the size of the blank bucket; the unreadable-on-screen-text count; whether `/p/` posts are videos or images; and **average media size, projected to the full corpus against free disk**. Feeds the §6 model gate (D14). ~$5 and a few hours. |
| 1 | **Scaffold, kit adaptation, both guards proven** (plus CI on GitHub Actions, the shared data contract, and database-level enforcement of AC-3.3 write-once and AC-8.2 read-only; see `DESIGN_RATIONALE.md` §7) | §6, §7, §8 | The Python check hook and the data-commit guard both break *silently* if wrong. Proven by deliberate failure, not assertion. |
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
| 10 | **Search UI + corrections + curation** | §1, §4 | Split from M9 because it is a second distinct review question. Includes hide/edit (D15, D21); extra categories, category editing and the Links & titles section (D22–D24) are added in Wave 2. |
| 11 | **Tailscale + verification** | §10, §6 | Owns **AC-6.1** (peak memory under 5 GB, measured on the real full-pipeline run; M0 records an early number). Optional: a GitHub Actions workflow running the unit tests. |

**Rules for this table**

- **Any boundary that can break silently goes in milestone 1**, not milestone 11.
- **Testing is distributed, not a phase.** Each test layer is assigned to the first milestone that can produce it.
- **Every promised deliverable appears in some row.** Work owned by no milestone silently never happens.
- **Split a milestone the moment it grows two distinct review questions.**

**Cuttable under time pressure, in this order:** Devanagari OCR fallback → the `other`-pool re-clustering loop → search filter chips. Nothing else is cut before quality is.

---

## How the build actually runs

*Rewritten 2026-09-19 to match how the build actually works (`DESIGN_RATIONALE.md` §4). The
earlier one-milestone-at-a-time loop was replaced by **waves**.*

### Who does what

| Role | Who | Job |
|---|---|---|
| **Owner** | You | Make decisions, judge and label real data, review the evidence, run every git command |
| **Lead** | The main Claude session you talk to | Plans, writes the shared contract, briefs the builders, re-runs their tests, fixes integration problems, writes the checkpoint |
| **Builders** | Subagents the lead launches (Sonnet), several at once | Each builds one milestone inside **its own folders only** (map in `docs/CONTRACT.md`), against fake data |
| **`checker`** | A subagent with no build history | Verifies each milestone's acceptance criteria independently, so it can't be talked round by the builder's story |

### The three waves

| Wave | What | How it runs | Milestones |
|---|---|---|---|
| **0: Foundation** | The skeleton everything plugs into: the data contract (database layout, who may write what), the test guards, CI, plus the M0 extraction test on 50 real reels | The lead builds it alone, because every builder depends on it | M0, M1 |
| **1: Parallel build** | Everything that can be built and tested with **fake data** | Builders work **at the same time**, each in its own folders | M2, M3, M5, M9, M10, eval + search code (M7/M8), labelling page |
| **2: Real data** | Run the pipeline on your archive, then measure and tune | **One stage at a time** (8 GB of RAM), run by the lead, with your tasks in between | M4, M6, M7, M8 (measuring), M11 |

**Wave 2 order:** fetch → OCR + speech (M4) → fusion → embeddings → taxonomy draft (M6) →
**you edit the taxonomy and label 150 reels** → classify (M7) → **you write and grade 50 queries** →
eval and tuning (M8) → Tailscale and final verification (M11).

### The loop for each wave

| | Who | What |
|---|---|---|
| 1 | **Owner** | Create one branch for the wave (`git checkout -b wave-N`) |
| 2 | Lead | `/plan-milestone`: audit the plan against reality and write the plan. **Wave 0 had a full plan you approved. Wave 1's builders got detailed written briefs from the lead instead, with no separate plan for you to review** |
| 3 | **Owner** | ⭐ Answer the ⚠️ *Needs your decision* items |
| 4 | Builders / lead | Build. `check.sh` checks each edit (only the edited folder plus the contract, so builders don't block each other) and blocks on failure |
| 5 | Lead | Collect every builder's report and **re-run their tests independently**: a builder's "it passes" is a claim, not evidence |
| 6 | Lead | Run the **full** test suite over the combined work and fix integration problems |
| 7 | Lead | `checker` on each milestone (no build context), then `/code-review` on the combined changes, fixing what they find |
| 8 | Lead | **One batched `/checkpoint`** for the wave. For each milestone: a short retroactive audit (plan vs. what was built), an evidence table, every decision a builder made on its own, and how to see it yourself |
| 9 | **Owner** | ⭐ Try the apps, compare the evidence with `checker`'s verdicts, reject any independent decision you disagree with, and ask `/prove-it` on anything important |
| 10 | **Owner** | Commit and push the wave's branch, then merge |

**Your two leverage points are steps 3 and 9.** Step 3 is the cheapest place to redirect,
because it's a paragraph, not code. Step 9 catches what no automated check can: is this what
was agreed, and does it look right.

**What parallel building gave up, and what makes up for it:**
- **You no longer review each milestone's plan before it's built.** A wrong assumption can
  spread across several builders before anyone sees it. Covered by the shared contract
  (builders can't disagree about data shapes), the retroactive audit in step 8, and your
  veto over every independent decision in step 9.
- **The UI is built on fake data.** Expect one UI polish pass after real data arrives.
- **The owner reviews in batches,** so each review is bigger. The checkpoint leads with the
  decisions that need you, so the reading stays short.

**Why the lead re-runs tests and runs `checker`:** builders report on their own work and
sometimes get it wrong (one reported 74 tests where 33 existed). The lead's re-run catches
false reports. `checker` catches "this was the wrong approach", which the builder and lead
can both miss, because both know the build story.

### Pausing and resuming

You can say "halt" at any time. The lead stops every builder **and** any program they left
running (downloads, model runs), then reports where each piece stands. Unfinished work stays on
disk, unreviewed. On "resume", stopped builders are relaunched and told to **continue from their
existing files**, not start over. Nothing is committed until step 10.

---

## Verification — how to confirm v1 is actually done

Run against the real system. Record the result in `docs/VERIFICATION.md`, **including which steps failed.**

1. Fresh clone, install dependencies, run `pytest` → green, and no test makes a network call
2. Introduce a deliberate Python type error → `check.sh` **blocks**. Revert → green
3. `git add -f data/raw/message_1.json && git commit` → **blocked** by the pre-commit hook (`-f` because `.gitignore` already refuses a plain add; the hook is the second line of defence). `.githooks/` is committed (only `.claude/settings.json` is gitignored), so `tests/test_precommit_hook.py` runs on CI too; a fresh clone must still run `git config core.hooksPath .githooks` to activate the hook.
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
