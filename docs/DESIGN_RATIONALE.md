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

**The situation.** The owner wants v1 in about a week and has Fable 5.1 credit expiring
within a day. The plan's loop builds one milestone at a time, and the owner reviews each
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
