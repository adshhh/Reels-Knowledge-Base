-- The shared data contract: one SQLite database, data/kb.db.
--
-- Every table has exactly ONE owning pipeline stage. Each connection declares its stage
-- (see db.py), and the triggers below refuse writes from any other stage. A connection that
-- declares no stage cannot write to an owned table at all, because the stage() function
-- doesn't exist on it and the trigger errors out. The serving layer goes further and opens
-- the file read-only (AC-8.2).
--
-- Owner / curation edits never touch this database: they live in append-only curation.jsonl
-- and corrections.jsonl, which are laid over the database at read time (see curation.py).

PRAGMA foreign_keys = ON;

-- INGEST (M2). One row per thing in the export, including things we can never fetch.
CREATE TABLE IF NOT EXISTS items (
    item_id        TEXT PRIMARY KEY,   -- Instagram shortcode, or 'att-<ms>' / 'ext-<ms>' / 'note-<ms>'
    kind           TEXT NOT NULL CHECK (kind IN ('reel', 'post', 'attachment', 'external', 'note')),
    url            TEXT,
    caption        TEXT,               -- decoded (mojibake fixed); NULL if the export had none
    source_account TEXT,               -- NULL if the export had none
    sent_at        TEXT NOT NULL,      -- ISO-8601 UTC, from the message timestamp
    caption_language TEXT              -- D16; detected from the caption
);

-- FETCH (M3). The manifest: every item ends in a terminal state with a reason (AC-2.2).
CREATE TABLE IF NOT EXISTS fetch_status (
    item_id     TEXT PRIMARY KEY REFERENCES items(item_id),
    status      TEXT NOT NULL CHECK (status IN ('pending', 'fetched', 'dead', 'unrecoverable', 'excluded')),
    reason      TEXT,
    fetched_via TEXT CHECK (fetched_via IN ('apify', 'ytdlp')),
    media_type  TEXT CHECK (media_type IN ('video', 'image', 'carousel')),
    media_path  TEXT,                  -- relative to data/
    duration_s  REAL,
    bytes       INTEGER,
    updated_at  TEXT NOT NULL
);

-- OCR (M4). ocr_verbatim: what Apple Vision read, string by string. WRITE-ONCE (AC-3.3):
-- only the 'ocr' stage may insert or delete (delete = redo an item), and NOBODY may update.
CREATE TABLE IF NOT EXISTS ocr_verbatim (
    item_id    TEXT NOT NULL REFERENCES items(item_id),
    frame_ts_s REAL NOT NULL,          -- where in the video the frame was taken
    text       TEXT NOT NULL,
    confidence REAL NOT NULL,
    bbox       TEXT,                   -- JSON [x, y, w, h], normalised 0..1
    PRIMARY KEY (item_id, frame_ts_s, text)
);

CREATE TABLE IF NOT EXISTS ocr_runs (
    item_id          TEXT PRIMARY KEY REFERENCES items(item_id),
    frames_sampled   INTEGER NOT NULL,
    unreadable_text  INTEGER NOT NULL DEFAULT 0 CHECK (unreadable_text IN (0, 1)),  -- text seen but not read
    ocr_language     TEXT,
    completed_at     TEXT NOT NULL
);

-- SPEECH (M4). transcript is '' when VAD heard no speech (D8): empty is an answer.
CREATE TABLE IF NOT EXISTS transcripts (
    item_id      TEXT PRIMARY KEY REFERENCES items(item_id),
    vad_speech   INTEGER NOT NULL CHECK (vad_speech IN (0, 1)),
    text         TEXT NOT NULL,
    language     TEXT,
    lyric_like   INTEGER NOT NULL DEFAULT 0 CHECK (lyric_like IN (0, 1)),  -- low confidence, §3 known gap
    model        TEXT,
    completed_at TEXT NOT NULL
);

-- FUSION (M5). The model's organised record, AFTER the fidelity gate has run.
CREATE TABLE IF NOT EXISTS fusion (
    item_id          TEXT PRIMARY KEY REFERENCES items(item_id),
    title            TEXT NOT NULL,
    summary          TEXT NOT NULL,
    bullets          TEXT NOT NULL,    -- JSON list of strings
    entities         TEXT NOT NULL,    -- JSON {"urls": [...], "handles": [...], "titles": [...]}, gate-approved only
    dropped_entities TEXT NOT NULL DEFAULT '[]',  -- JSON list the gate removed, with reasons
    unverified_names TEXT NOT NULL DEFAULT '[]',  -- JSON list the gate FLAGGED but kept (AC-3.1 miss)
    language         TEXT,             -- D16: overall record language
    model            TEXT NOT NULL,
    completed_at     TEXT NOT NULL
);

-- CLASSIFY (M6/M7). categories mirrors taxonomy.yaml; ids are immutable.
CREATE TABLE IF NOT EXISTS categories (
    category_id TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS classification (
    item_id      TEXT PRIMARY KEY REFERENCES items(item_id),
    category_id  TEXT NOT NULL REFERENCES categories(category_id),
    confidence   REAL NOT NULL,
    runner_up_id TEXT REFERENCES categories(category_id),
    rationale    TEXT NOT NULL DEFAULT '',
    model        TEXT NOT NULL,
    completed_at TEXT NOT NULL
);

-- EMBED (M8). Row i of data/embeddings.npy belongs to embedding_rows.item_id where row = i.
CREATE TABLE IF NOT EXISTS embedding_rows (
    row     INTEGER PRIMARY KEY,
    item_id TEXT NOT NULL UNIQUE REFERENCES items(item_id)
);
