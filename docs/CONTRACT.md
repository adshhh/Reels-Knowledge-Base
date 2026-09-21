# The data contract

How the parts of this project fit together: what data exists, who is allowed to write it,
and who owns which folder. Every builder works against this document. The code version
lives in `src/reelkb/contract/`.

## The big picture

```
message_1.json ──▶ ingest ──▶ fetch ──▶ ocr ─┐
                                   └──▶ speech ┴──▶ fusion (+ fidelity gate) ──▶ classify ──▶ embed
                                                                                        │
                        curation.jsonl / corrections.jsonl (your edits) ──────────┐     │
                                                                                  ▼     ▼
                                                              web app (read-only) + search
```

Data flows one way. Each **stage** is a program that reads what earlier stages wrote and
adds its own table to one SQLite database, `data/kb.db`. Nothing flows backwards.

## Who may write what (enforced by the database itself)

| Table | Written only by | Holds |
|---|---|---|
| `items` | ingest (M2) | One row per thing in the export: shortcode, kind, URL, decoded caption, account, date |
| `fetch_status` | fetch (M3) | The manifest: pending / fetched / dead / unrecoverable / excluded, with a reason |
| `ocr_verbatim`, `ocr_runs` | ocr (M4) | Exactly what Apple Vision read, string by string. **Write-once: nobody can change a row** |
| `transcripts` | speech (M4) | VAD verdict and transcript (`''` when nobody spoke) |
| `fusion` | fusion (M5) | Title, summary, bullets, entities, **after** the fidelity gate. Also `dropped_entities` (what the gate removed) and `unverified_names` (names it could not confirm but deliberately left in the prose — `decisions/004`) |
| `categories`, `classification` | classify (M6/M7) | The taxonomy and each item's category |
| `embedding_rows` (+ `data/embeddings.npy`) | embed (M8) | Which row of the vector file belongs to which item |

A stage opens the database with `connect_stage(path, "<stage>")`. SQLite then refuses its
writes to any table it doesn't own. The web app uses `connect_readonly(path)` and can write
nothing (AC-8.2). Proven in `tests/contract/test_schema_boundaries.py`.

**Your edits never go in the database.** Hide, edit and recategorise are appended to
`data/curation.jsonl` and `data/corrections.jsonl`, and laid on top whenever cards are read.
A pipeline re-run rebuilds the database but never touches those files, so your edits always
survive (AC-1.3, AC-4.3).

## What the product reads: a Card

`load_cards(conn, curation)` returns one **Card** per fetched and fused item, with curation
applied: title, summary, bullets, category, date, account, and the three channels (caption,
on-screen text, speech) each labelled. Hidden cards are left out. Search returns
`SearchHit(item_id, score, matched_on)` through the `Searcher` interface in
`contract/search_api.py`.

## Folder ownership (Wave 1)

Each builder writes only inside its own folders. `contract/` and `testing/` belong to the lead.

| Builder | Milestone | Code | Tests |
|---|---|---|---|
| A | M2 export parser | `src/reelkb/ingest/` | `tests/ingest/` |
| B | M3 fetch + manifest | `src/reelkb/fetch/` | `tests/fetch/` |
| C | M5 fusion + fidelity gate | `src/reelkb/fusion/` | `tests/fusion/` |
| D | eval harness + search (M7/M8 code) + labelling page | `src/reelkb/eval/`, `src/reelkb/search/`, `src/reelkb/label/` | `tests/eval/`, `tests/search/`, `tests/label/` |
| E | M9/M10 web app | `src/reelkb/serve/` | `tests/serve/` |
| lead | contract, integration, M4, M6 | `src/reelkb/contract/`, `src/reelkb/testing/` | `tests/contract/` |

Builders develop against the fake corpus in `src/reelkb/testing/fake_db.py` (27 made-up
cards covering every awkward case), never against `data/`.

## What leaves this machine

You asked to be told whenever content is sent anywhere. The complete list:

| Service | What is sent | When |
|---|---|---|
| **Apify** (`memo23`) | Reel URLs/shortcodes; Apify downloads the public videos | Fetch (M0, M3) |
| **Instagram** (via yt-dlp) | Reel URLs, from your home connection, logged out | Top-ups only (M0 test, later) |
| **Groq** | Audio of reels with detected speech; caption + on-screen text + transcript text | Speech + fusion + classification |
| **Google Gemini** (free tier) | Whole videos, only for "blank" reels if M0 justifies it; the 50 M0 test items | M0; maybe later |
| **GitHub** | Code and docs only; never anything under `data/` | When you push |

Nothing else leaves: OCR, speech detection and search embeddings all run on your Mac.

## Rules every builder follows

- Unit tests use fake data only: no network, no models (`tests/conftest.py` enforces it).
  Anything that needs a real model or API goes in a test marked `@pytest.mark.realmodel`.
- No git commands, ever. No new dependencies without the lead's approval.
- Nothing from the archive appears in code, tests, docs or commit-able files.
- Pipeline stages run one at a time (8 GB of RAM).
