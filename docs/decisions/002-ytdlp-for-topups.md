# 002 — yt-dlp allowed for monthly top-ups (amends D6)

**Date:** 2026-09-19 · **Status:** accepted · **Rationale:** `docs/DESIGN_RATIONALE.md` §2

## 1. What changed

D6 ("media is fetched through a vendor, never by DIY scraping") is amended by **D18**:
- the **bulk first run** (~1,870 reels) still uses the Apify `memo23` actor
- later **small top-ups** (<100 reels/month) may use **logged-out, throttled** `yt-dlp`
- logged-in scraping of any kind stays forbidden

## 2. Why it changed

D6's ban-rate argument applies to logged-in scraping. Logged-out yt-dlp from a home
connection doesn't involve the owner's account. For small monthly batches, its slowness
doesn't matter and it costs nothing.

## 3. Sections this invalidates

- **§2 Acquisition.** Stage 2 names `memo23` as the only fetch path.
- **§8 System architecture.** The EXTRACT layer shows a single fetch source.

## 4. Trade-offs / what was given up

- Two fetch paths instead of one, so two sets of failure handling.
- Instagram rate limits during top-ups hit the owner's home connection, which his personal
  Instagram account also uses.
- yt-dlp's Instagram support breaks from time to time and needs updating.
