# Design Rationale

Why things are the way they are. One entry per decision, numbered, never renumbered.
Changes to anything LOCKED in `docs/PLAN.md` also get a record in `docs/decisions/`.

---

## 1. Hosted models allowed; the rule becomes "cheapest that works" (supersedes D9)

**The situation.** D9 required open-weight models for all inference. It was chosen when the
owner assumed every stage would be self-built and wanted free models. While preparing the
§6 model gate, the owner researched services that extract reel content end to end (Supadata,
Apify all-in-one actors, Gemini video understanding) and asked for every workable route to be
compared on cost.

**Options considered.**
- **A. Supadata for everything.** ~$47 first run (Mega plan: ~1,300 reels × ~5.5 credits),
  then $5–17/month, because the free tier covers only ~20 reels/month. Returns only the AI's
  interpretation, with no verbatim on-screen text.
- **B. Apify all-in-one actor** (`afanasenko/instagram-reel-script-extractor`). ~$100 first
  run ($0.075/reel). It doesn't document how it reads on-screen text, and it has zero ratings.
- **C. Gemini watches every video.** ~$11–25 first run. Same URL-guessing risk as A.
- **D. Current plan, with hosted speech-to-text and a stronger text model.** ~$6.
- **E. D plus Gemini on every video, with OCR as the fact-check.** ~$12–20.
- **Keep D9 as it is:** open-weight only.

**Decision.** D9 is superseded. Hosted and closed models are allowed wherever they are the
cheapest option that meets the acceptance criteria. The owner prefers free or near-free
options; the target for the first run stays under ~$6. Which model runs each stage is still
**not decided**: the §6 model gate (D14) stays open.

**Why / trade-off.** The owner's original reason for open weights was cost, and hosted
open-weight or budget models (Groq Whisper, `gpt-oss-120b`, Gemini Flash-Lite) are now as cheap
as local ones or cheaper. Some of them also remove the 4–8 hour overnight transcription run.
**What was given up:**
- **The "no closed model sees the content" property.** Reel content can now go to Google
  (Gemini) as well as Groq.
- **Being able to rerun on models whose weights are published.** A hosted model can change
  or be retired without warning, so a rerun may not reproduce the same results.

D7 ("OCR reads, the model interprets") is **not** affected: options A, B and C were kept out
of the recommendation because they cannot satisfy AC-FIDELITY without a verbatim OCR channel.

---

## 2. Vendor for the bulk fetch; yt-dlp allowed for monthly top-ups (amends D6)

**The situation.** The owner asked why the plan used a paid Apify actor instead of the free
`yt-dlp`. Looking again showed that D6's main argument (reported 11–17% account-ban rates) applies
to **logged-in** scraping. Logged-out yt-dlp from a home internet connection never touches the
owner's account, and home connections are not blocked the way datacentre IPs are.

**Options considered.**
- **Apify `memo23` for everything** (D6 as written). ~$3.74 first run, minutes to an hour.
- **yt-dlp for everything.** Free, but 5–15 hours for 1,870 reels at the 10–30s delay
  needed to avoid rate limits.
- **Instaloader.** Free, but it hits login walls quickly when used logged out.
- **Web downloaders (frominsta, imginn, downloot).** They have no developer API, use bot
  protection and have no terms. Rejected.
- **Hybrid: vendor for the bulk run, yt-dlp for top-ups.**

**Decision.** The hybrid. Apify `memo23` fetches the initial ~1,870 reels. **Logged-out**
yt-dlp, throttled, is allowed for the later small batches (<100 reels/month). Logged-in
scraping of any kind stays forbidden.

**Why / trade-off.** For the bulk run, $3.74 buys back ~10 hours, which matters for the
one-week target. At <100 reels/month, yt-dlp's speed doesn't matter and it costs nothing.
**What was given up:**
- **One fetch path.** There are now two, which means two sets of failure handling.
- **Some risk to the owner's own internet connection.** Top-ups run from the owner's home
  connection, the same one his personal phone and Instagram account use, so an Instagram
  rate limit there could cause temporary login challenges on the real account.
- **Stability.** yt-dlp's Instagram support breaks from time to time and needs updating.

---

## 3. No Tesseract fallback for Devanagari; tag and review by hand

**The situation.** §3 planned a Tesseract `hin` second pass for native-Devanagari on-screen
text, which Apple Vision may not read. The plan already lists this fallback as the first
thing to cut under time pressure.

**Options considered.**
- **Tesseract `hin` second pass,** as planned.
- **Cut it:** tag affected cards and let the owner watch them.

**Decision.** Cut it. Cards whose on-screen text couldn't be read get a visible tag and a UI
filter, and the owner watches those reels himself. The tag covers more than Devanagari. It is
set whenever a frame visibly contains text but OCR couldn't read it (Devanagari, stylised
fonts, handwriting). M0 counts how many reels this affects. **If the count is large, this
entry is revisited**; the owner decides what "large" means once he sees the number.

**Why / trade-off.** It saves a stage, a dependency and a slow, weaker OCR engine, for content
the owner can read himself. **What was given up:** those reels are not searchable by their
on-screen text. They are still found through the caption, the speech transcript and the tag.

---

## 4. Parallel build in waves, reviewed in batches (changes "How the build actually runs")

**The situation.** The owner wants v1 in about a week. (The Fable 5.1 credit that first
motivated this turned out to have already expired; the subagents run on Sonnet instead. The
reasoning below doesn't depend on which model builds.) The plan's loop builds one milestone at a time, and the owner reviews each
before the next starts.

**Options considered.**
- **Sequential, as planned.** About 4–6 weeks.
- **Parallel waves.** Build everything that doesn't need real data at the same time, using
  subagents that each own separate folders and test against a shared fake-data contract. Then
  run the real-data stages one at a time.

**Decision.** Parallel waves. Wave 0: M1 plus the data contract. Wave 1: M2, M3, M5, the
eval/search code, and M9/M10, built by parallel subagents. M4 waits for M0's findings. Wave 2:
real-data runs, one stage at a time. Every milestone still gets its own `/checkpoint` and a
`checker` verdict; the owner reviews them in batches. No git worktrees, because creating
branches is forbidden to the agent; the subagents are kept apart by folder ownership instead.

**Why / trade-off.** Build time is the part of the schedule that can be compressed; machine
time and the owner's labelling can't. **What was given up:**
- **Per-milestone review before the next build starts.** A wrong assumption in the shared
  contract can now spread into five pieces before anyone reviews it.
- **Building against real data.** The UI is built on fake data, so a UI pass after real data
  is expected.
- **One branch per milestone.** The owner commits the wave's results.

---

## 5. Frontend: server-rendered HTML from FastAPI

**The situation.** The plan never specified a frontend technology.

**Options considered.**
- **FastAPI + Jinja templates.** FastAPI builds each page as finished HTML on the server,
  with a little plain JavaScript for small interactions (hide, edit).
- **React single-page app.** The browser downloads a JavaScript application, which fetches
  data from a FastAPI API and draws the pages itself.

**Decision.** FastAPI + Jinja templates.

**Why / trade-off.** The product is a feed, a detail view and a search box, for one user. Server
rendering means one language (Python), one process and no frontend build step, and pages load
fast on a phone over Tailscale. It is also much easier for the owner to follow end to end.
**What was given up:** rich interactivity (instant filtering without a page reload, app-like
transitions). Adding it later means rewriting the templates as components.

---

## 6. A local labelling page for the evaluation fixtures (adds scope, traceable to §7)

**The situation.** §7 requires the owner to hand-label 150 holdout reels and judge the pooled
search results for 50 queries. That is the project's critical path (~5 hours).

**Options considered.**
- **Hand-edit JSONL files.** No new code, but slow and easy to get wrong.
- **A small local labelling page.** Shows one reel's evidence plus the category buttons
  (or one query's candidate results with 2/1/0 buttons) and writes the fixture files.

**Decision.** Build the labelling page.

**Why / trade-off.** It saves an estimated 1–2 hours on the critical path and removes a way to
corrupt the fixtures. It only writes the files; the owner still makes every judgement, so §7's
"not AI-generated" rule holds. **What was given up:** a little build time spent on a tool the
product doesn't ship, plus one more thing to maintain.

---

## 7. Continuous integration (CI) on GitHub Actions

**The situation.** The audit for M0/M1 found the plan referred to "CI" (tests run automatically
by GitHub on every push) but no milestone owned setting it up. The owner chose to have it.

**Options considered.**
- **No CI.** Rely on local `check.sh`.
- **CI in M1.** A GitHub Actions workflow that runs ruff, mypy and the unit tests on every push.

**Decision.** Set up CI in M1. It runs on fake data only: the archive is never in the repo, so
nothing personal can reach GitHub's servers.

**Why / trade-off.** It gives a public, independent record that the tests pass on a clean
machine, which also covers the gap left by gitignoring `.claude/` and `.githooks/`.
**What was given up:** a small amount of setup, and a failing badge whenever the owner pushes
broken code (which is the point).

---

## 8. Media and intermediate files are deleted after v1

**The situation.** The disk showed 21 GB free in `df` (60 GB in Finder, which also counts
space macOS can reclaim on demand). The owner plans to delete downloaded videos, extracted
audio and sampled frames once v1 is done.

**Decision.** Keep all media during the v1 build, and delete it after v1. The extracted
records (OCR text, transcripts, summaries, embeddings) are kept.

**Why / trade-off.** Media is only needed while extraction is being tuned. **What was given
up:** D11's justification ("video files are retained, so thumbnails are cheap to revisit") no
longer holds after v1. Re-extracting or adding thumbnails later means downloading again, and
reels deleted by their creators in the meantime cannot be recovered.

---

## 9. External links and typed notes deferred to v2

**The situation.** The export holds 17 non-reel items: 10 `external` (8 non-Instagram links,
1 share with no link key, 1 profile share) and 7 `note`. (Counted 2026-09-19 by the M2
checker; the first estimate said ~16.)
The plan never mentioned them.

**Decision.** v1 records them in the manifest as `external` or `note` and excludes them from
the pipeline. **v2** adds a small pipeline that brings them into the app under their own tag.
Recorded in `decisions/003`.

**Why / trade-off.** 15 items do not justify new pipeline code on the one-week path. **What was
given up:** those items don't appear in the v1 app.

---

## 10. Gemini free tier accepted

**The situation.** D17 proposed Gemini's paid tier so that Google would not use the content.
The owner considers the content (public reels about ML courses, movies, food) not sensitive and
accepts the free tier. He asked to be told whenever content leaves the machine.

**Decision.** The free tier is acceptable. Every stage that sends content off the machine is
listed in `docs/CONTRACT.md` under "What leaves this machine".

**Why / trade-off.** It saves a small bill and the billing setup. **What was given up:** Google
may use what is sent to it to improve its products. Free-tier rate limits may also slow a
full-corpus Gemini run.

---

## 11. Unverified names in card prose are flagged, not removed

**The situation.** The M5 checker found the fidelity gate never looked at the card's prose for
names at all. It checked the model's declared `entities` list thoroughly, and scanned the
title/summary/bullets for URLs and @handles only. So a name could be thrown out of the entity
list and still stand as the card's headline. Reproduced against the real code: a card titled
`Nosferatu (2024)` for a reel whose on-screen text never mentions it, with `dropped_entities`
empty. That is AC-3.1's exact failure mode, on the one field the owner actually reads.

The obvious fix -- strip unverified names the way URLs are stripped -- was measured against the
50 real M0 items first, and it is destructive. AC-3.1 verifies against **on-screen text only**,
and 3 of the 50 items have no on-screen text whatsoever. One card reads *"Source Code movie
recommendation"*: the model identified a real 2011 film from speech, correctly, and the gate
rejects both "Source Code" and "Hulu" purely because the reel shows no text. Stripping would
retitle that card *"movie recommendation"* -- destroying a correct card, which is the precise
failure the project exists to prevent. 35 of 50 items carry at least one name in this position.

**Options considered.**
1. Strip unverified names from prose. AC-3.1 met as written; correct cards destroyed.
2. Leave the gap open. No cost today, but no record, no count, and no way to know which cards
   carry an unconfirmed name.
3. Flag and record without editing the text.
4. Widen the evidence to OCR + transcript, so spoken names count. Rescues the *Source Code*
   case, but weakens the guarantee (Whisper can mishear a name) and changes AC-3.1.

**Decision.** Option 3 now; option 4 deferred. The gate finds name-shaped phrases in prose,
records each one it cannot confirm in the new `fusion.unverified_names` column with its
location, and leaves the prose byte-for-byte unchanged. The card shows a
"N unverified names" badge listing them. The owner will decide between stripping and widening
the evidence after judging the 50 M0 reels, and **AC-3.1 will be rewritten then** -- that
judgement measures precisely whether a thin card reads as "subject not named".

**Why / trade-off.** It makes the doubt visible and countable without destroying anything, and
it defers an irreversible choice until there is evidence for it. **What was given up:**
**AC-3.1 is NOT met.** A stored card can still contain a name that on-screen text does not
confirm -- it is merely marked now. This is recorded as a miss, not a redefinition; §3 is
reopened in the plan's status board until the post-judging decision closes it.

**Known limits, measured rather than assumed.**
- Where prose is Title Case, capitalisation carries no signal, so the scan stands down and
  only names the model itself declared are caught. Scanning anyway flagged 46 of 50 cards,
  which would make the badge meaningless. Proper detection needs name recognition or a
  dictionary; both are out of scope for v1.
- After tuning against the real M0 output, 32 of 50 cards carry at least one flag (144 flags
  total). That number is high because it is honest: on-screen-text-only verification genuinely
  cannot confirm most names in this archive.

---

## 12. Provenance on every card

**The situation.** The owner asked for the original reel/post link, source account and date on
the card, directly under the title and above the summary, so any card can be traced back to
the thing it came from -- and said to fall back to the link alone if account or date cost extra
from Apify.

**Decision.** All three are shown. Nothing was dropped and nothing extra is paid: `url`,
`source_account` and `sent_at` all come from the Instagram export that `ingest` already parses,
not from the fetch vendor. The "Open original" link moved from the bottom of the detail page
into that line, and the same line now appears on list and search results.

**Why / trade-off.** A knowledge base whose entries cannot be traced to a source is a pile of
assertions. **What was given up:** a little horizontal space on the card, and one more outbound
link per card on list pages.
