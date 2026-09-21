"""A small, made-up knowledge base for building and testing without the real archive.

Every Wave 1 component develops against this. It deliberately contains the awkward cases:
every combination of empty/non-empty channels, a caption that never names its subject (the
*Flow*-style canary), Hinglish, unreadable on-screen text, sung lyrics, and non-card items
(dead, unrecoverable, external). All content is invented.

    python -m reelkb.testing.fake_db data/fake    # writes data/fake/kb.db
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from reelkb.contract.db import connect_stage, init_db

NOW = "2026-09-19T00:00:00+00:00"

CATEGORIES = [
    ("ml-courses", "ML courses & resources", "Free courses, tutorials and learning paths for ML."),
    ("research-papers", "Research papers", "Explainers and links to specific papers."),
    ("movies", "Movies", "Film recommendations and reviews."),
    ("books", "Books", "Book lists and recommendations."),
    ("food", "Food", "Recipes and places to eat."),
    ("career", "Career", "Jobs, interviews and career advice."),
    ("other", "Other", "Quarantine pool for anything that fits nowhere else."),
]


@dataclass(frozen=True)
class FakeReel:
    item_id: str
    category: str
    title: str
    summary: str
    caption: str
    ocr: tuple[str, ...]
    transcript: str
    account: str
    urls: tuple[str, ...] = ()
    language: str = "en"
    unreadable: bool = False
    lyric_like: bool = False


REELS: list[FakeReel] = [
    FakeReel(
        "FAKEml001",
        "ml-courses",
        "Free deep learning course from fast.ai",
        "A free, practical deep learning course.",
        "Best free course I've found 🔥",
        ("Practical Deep Learning", "course.fast.ai"),
        "",
        "learnwithdata",
        urls=("course.fast.ai",),
    ),
    FakeReel(
        "FAKEml002",
        "ml-courses",
        "Andrew Ng's machine learning specialization",
        "The classic ML specialization, now free to audit.",
        "",
        ("Machine Learning Specialization", "coursera.org"),
        "if you're starting out, audit this specialization first",
        "aiexplained",
        urls=("coursera.org",),
    ),
    FakeReel(
        "FAKEml003",
        "ml-courses",
        "Five GitHub repos to learn LLMs",
        "Five repositories for learning large language models.",
        "Save this for later #ai #llm #coding",
        ("1. llm-course", "2. nanoGPT", "3. transformers", "github.com/mlabonne/llm-course"),
        "",
        "codewithme",
        urls=("github.com/mlabonne/llm-course",),
    ),
    FakeReel(
        "FAKEml004",
        "ml-courses",
        "Stanford CS229 lectures on YouTube",
        "Full CS229 lecture series available free.",
        "Stanford for free?? yes",
        ("CS229", "Stanford"),
        "all the lectures are on youtube for free",
        "gradschoolhacks",
    ),
    FakeReel(
        "FAKEml005",
        "ml-courses",
        "Roadmap to become an ML engineer",
        "A step-by-step roadmap from Python to deployment.",
        "",
        ("Python", "Statistics", "Deep Learning", "MLOps"),
        "",
        "roadmaps.daily",
    ),
    FakeReel(
        "FAKEml006",
        "ml-courses",
        "Kaggle Learn micro-courses",
        "Kaggle's short free courses with certificates.",
        "free certificates 👇",
        ("kaggle.com/learn",),
        "",
        "learnwithdata",
        urls=("kaggle.com/learn",),
    ),
    FakeReel(
        "FAKEpp001",
        "research-papers",
        "Attention Is All You Need explained",
        "The transformer paper in sixty seconds.",
        "the paper that started it all",
        ("Attention Is All You Need", "Vaswani et al. 2017"),
        "the transformer replaced recurrence with attention",
        "paperbites",
    ),
    FakeReel(
        "FAKEpp002",
        "research-papers",
        "LoRA: cheap fine-tuning",
        "How low-rank adaptation fine-tunes big models cheaply.",
        "",
        ("LoRA", "Low-Rank Adaptation"),
        "lora freezes the weights and trains small matrices",
        "paperbites",
    ),
    FakeReel(
        "FAKEpp003",
        "research-papers",
        "Diffusion models, visually",
        "An animated explainer of how diffusion models denoise.",
        "this visual 🤯",
        (),
        "diffusion starts from pure noise and removes it step by step",
        "visualml",
    ),
    FakeReel(
        "FAKEpp004",
        "research-papers",
        "RAG paper summary",
        "Retrieval-augmented generation, summarised.",
        "#rag #nlp",
        ("Retrieval-Augmented Generation", "Lewis et al."),
        "",
        "paperbites",
    ),
    FakeReel(
        "FAKEmv001",
        "movies",
        "Flow (2024) — animated film about a cat",
        "A wordless animated film following a cat through a flood.",
        "Not only was this movie visually stunning, I loved it & so did Kuma",
        ("FLOW",),
        "",
        "filmcorner",
    ),
    FakeReel(
        "FAKEmv002",
        "movies",
        "Perfect Days recommendation",
        "A quiet Wim Wenders film about a Tokyo toilet cleaner.",
        "",
        ("Perfect Days", "Wim Wenders"),
        "this movie changed how I see routine",
        "filmcorner",
    ),
    FakeReel(
        "FAKEmv003",
        "movies",
        "Three underrated sci-fi films",
        "Moon, Coherence and Primer as underrated sci-fi.",
        "watchlist update",
        ("Moon (2009)", "Coherence (2013)", "Primer (2004)"),
        "",
        "scifi.nights",
    ),
    FakeReel(
        "FAKEmv004",
        "movies",
        "Your Lie in April",
        "An anime about a pianist who stopped hearing his own playing.",
        "😭😭",
        (),
        "",
        "animevault",
        unreadable=True,
    ),
    FakeReel(
        "FAKEmv005",
        "movies",
        "Dil Chahta Hai rewatch",
        "Why this 2001 film still holds up.",
        "yaar ye movie abhi bhi best hai",
        ("Dil Chahta Hai",),
        "ye movie dosti ke baare mein hai",
        "bollywoodtalk",
        language="hi-Latn",
    ),
    FakeReel(
        "FAKEmv006",
        "movies",
        "A film score montage",
        "A montage set to a popular film song.",
        "#music #film",
        (),
        "la la la under the moonlight dancing all night",
        "edits.hub",
        lyric_like=True,
    ),
    FakeReel(
        "FAKEbk001",
        "books",
        "Five books for engineers",
        "Five non-fiction books recommended for engineers.",
        "",
        ("Designing Data-Intensive Applications", "The Pragmatic Programmer"),
        "",
        "bookstack",
    ),
    FakeReel(
        "FAKEbk002",
        "books",
        "Atomic Habits in one minute",
        "The core idea of Atomic Habits.",
        "read this",
        ("Atomic Habits",),
        "small habits compound over time",
        "bookstack",
    ),
    FakeReel(
        "FAKEbk003",
        "books",
        "Hindi poetry collection",
        "A recommended collection of Hindi poetry.",
        "kavita 📖",
        (),
        "",
        "kavitaghar",
        language="hi",
        unreadable=True,
    ),
    FakeReel(
        "FAKEfd001",
        "food",
        "Ten-minute paneer bhurji",
        "A quick paneer bhurji recipe.",
        "dinner sorted",
        ("Paneer Bhurji", "10 min"),
        "add the onions first then tomatoes",
        "desikitchen",
    ),
    FakeReel(
        "FAKEfd002",
        "food",
        "Best ramen in Toronto",
        "A ranked list of ramen spots.",
        "",
        ("1. Kinton", "2. Sansotei"),
        "",
        "eatsto",
    ),
    FakeReel(
        "FAKEfd003",
        "food",
        "Cold brew at home",
        "How to make cold brew coffee.",
        "coffee hack ☕",
        (),
        "coarse grind, twelve hours, strain it",
        "brewlab",
    ),
    FakeReel(
        "FAKEcr001",
        "career",
        "Resume tips from a recruiter",
        "Three resume mistakes recruiters reject.",
        "",
        ("Resume Mistakes",),
        "stop listing duties, list results",
        "techcareers",
    ),
    FakeReel(
        "FAKEcr002",
        "career",
        "Meta new-grad program",
        "Details of a new-grad ML engineer program.",
        "apply before it closes",
        ("metacareers.com",),
        "",
        "techcareers",
        urls=("metacareers.com",),
    ),
    FakeReel(
        "FAKEcr003",
        "career",
        "System design interview framework",
        "A four-step framework for system design interviews.",
        "",
        ("1. Requirements", "2. Estimates", "3. Design", "4. Deep dive"),
        "",
        "sysdesign.io",
    ),
    FakeReel(
        "FAKEot001",
        "other",
        "A dog learns to skateboard",
        "A dog skateboarding down a hill.",
        "lmaooo",
        (),
        "",
        "dogsofig",
    ),
    FakeReel(
        "FAKEot002",
        "other",
        "Honda Civic Type R walkaround",
        "A walkaround of a Civic Type R.",
        "#funny #comedy #memes",
        ("Civic Type R",),
        "",
        "carspotter",
    ),
]

# Items that exist in the export but never become cards.
NON_CARDS = [
    ("FAKEdead01", "reel", "dead", "post deleted by creator"),
    ("FAKEdead02", "post", "dead", "account private"),
    ("att-1700000000000", "attachment", "unrecoverable", "export has no share data"),
    ("ext-1700000000001", "external", "excluded", "non-Instagram link (v2, decisions/003)"),
]


def build(data_dir: Path) -> Path:
    """Create data_dir/kb.db filled with the fake corpus and return its path."""
    db = data_dir / "kb.db"
    if db.exists():
        db.unlink()
    init_db(db)
    start = datetime(2023, 1, 1, tzinfo=UTC)

    with connect_stage(db, "ingest") as conn:
        for n, r in enumerate(REELS):
            conn.execute(
                "INSERT INTO items VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    r.item_id,
                    "reel",
                    f"https://www.instagram.com/reel/{r.item_id}/",
                    r.caption,
                    r.account,
                    (start + timedelta(days=40 * n)).isoformat(),
                    r.language,
                ),
            )
        for item_id, kind, _, _ in NON_CARDS:
            conn.execute(
                "INSERT INTO items VALUES (?, ?, ?, NULL, NULL, ?, NULL)",
                (item_id, kind, None if kind == "attachment" else "https://example.com/x", NOW),
            )

    with connect_stage(db, "fetch") as conn:
        for r in REELS:
            conn.execute(
                "INSERT INTO fetch_status VALUES (?, 'fetched', NULL, 'apify', 'video', ?, 30.0, "
                "5000000, ?)",
                (r.item_id, f"media/{r.item_id}.mp4", NOW),
            )
        for item_id, _, status, reason in NON_CARDS:
            conn.execute(
                "INSERT INTO fetch_status (item_id, status, reason, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (item_id, status, reason, NOW),
            )

    with connect_stage(db, "ocr") as conn:
        for r in REELS:
            for i, text in enumerate(r.ocr):
                conn.execute(
                    "INSERT INTO ocr_verbatim VALUES (?, ?, ?, 0.95, NULL)",
                    (r.item_id, float(i), text),
                )
            conn.execute(
                "INSERT INTO ocr_runs VALUES (?, 7, ?, ?, ?)",
                (r.item_id, int(r.unreadable), "en" if r.ocr else None, NOW),
            )

    with connect_stage(db, "speech") as conn:
        for r in REELS:
            conn.execute(
                "INSERT INTO transcripts VALUES (?, ?, ?, ?, ?, 'fake', ?)",
                (
                    r.item_id,
                    int(bool(r.transcript)),
                    r.transcript,
                    r.language if r.transcript else None,
                    int(r.lyric_like),
                    NOW,
                ),
            )

    with connect_stage(db, "fusion") as conn:
        for r in REELS:
            bullets = [r.summary, *r.ocr[:3]] if r.ocr else [r.summary]
            entities = {"urls": list(r.urls), "handles": [], "titles": []}
            conn.execute(
                "INSERT INTO fusion VALUES (?, ?, ?, ?, ?, '[]', '[]', ?, 'fake', ?)",
                (
                    r.item_id,
                    r.title,
                    r.summary,
                    json.dumps(bullets),
                    json.dumps(entities),
                    r.language,
                    NOW,
                ),
            )

    with connect_stage(db, "classify") as conn:
        conn.executemany("INSERT INTO categories VALUES (?, ?, ?)", CATEGORIES)
        for r in REELS:
            conn.execute(
                "INSERT INTO classification VALUES (?, ?, 0.9, NULL, '', 'fake', ?)",
                (r.item_id, r.category, NOW),
            )
    return db


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/fake")
    print(f"wrote {build(target)} with {len(REELS)} cards")
