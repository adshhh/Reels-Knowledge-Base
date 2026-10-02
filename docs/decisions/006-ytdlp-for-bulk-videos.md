# 006 — yt-dlp fetches the bulk run's videos; Apify only for carousels (amends D18)

**Date:** 2026-10-01 · **Status:** accepted · **Rationale:** `docs/DESIGN_RATIONALE.md` §14

## 1. What changed

D18 allowed logged-out yt-dlp only for monthly top-ups (<100/month) and kept the bulk first
run on the `memo23` Apify actor. Now **D20**: the bulk run fetches the 1,714 videos with
logged-out, throttled yt-dlp, and uses Apify only for the 156 carousels (which yt-dlp cannot
fetch) and for any video yt-dlp fails on. Logged-in scraping stays forbidden.

## 2. Why it changed

M0 measured the real Apify cost at ~$23.24 for the corpus (the plan estimated ~$3.74), most of
it per-run Actor Start fees forced by the non-paying account's 5-event cap. yt-dlp fetched 34 of
35 M0 videos (97%). This route costs ~$2.85.

## 3. Sections this invalidates

- **§2 Acquisition** -- stage 2 names `memo23` as the bulk fetcher and ~$3.74 as its cost.
- **§6 Models and where they run** -- the media-fetch row.
- **§8 System architecture** -- the fetch stage.

## 4. Trade-offs / what was given up

- Rate limits and any blocking land on the owner's home connection, not a vendor's proxies.
- Slower: 10–30 s throttle per video, roughly a day for the bulk run.
- Two fetch paths to maintain instead of one.
