"""AC-3.1 / AC-FIDELITY: "No stored record contains a URL, @handle, or proper-noun title
absent from that reel's OCR output within edit distance 2."

This is the one test file the milestone is graded on: "The milestone fails if a planted fake
survives." Every case below is either a planted fake (must be caught) or genuine OCR noise
(must survive), matching the plan's own examples where the plan gives one (e.g.
`coursera.org` vs `coursero.org`, distance 1).
"""

from __future__ import annotations

import functools
import random
import string

import pytest

from reelkb.fusion.fidelity import edit_distance, gate, is_verified, normalise_url
from reelkb.fusion.types import FusionDraft

# --------------------------------------------------------------------------- edit_distance


@functools.cache
def _reference_distance(a: str, b: str) -> int:
    """A second, independently-written Levenshtein implementation (plain recursion + cache)
    used only to cross-check `edit_distance`, so a bug shared between "the code" and "the
    test's model of the code" can't hide."""
    if not a:
        return len(b)
    if not b:
        return len(a)
    if a[0] == b[0]:
        return _reference_distance(a[1:], b[1:])
    return 1 + min(
        _reference_distance(a[1:], b),
        _reference_distance(a, b[1:]),
        _reference_distance(a[1:], b[1:]),
    )


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("", "", 0),
        ("abc", "abc", 0),
        ("abc", "", 3),
        ("", "abc", 3),
        ("coursera.org", "coursero.org", 1),
        ("kitten", "sitting", 3),
        ("flaw", "lawn", 2),
    ],
)
def test_edit_distance_known_values(a: str, b: str, expected: int) -> None:
    assert edit_distance(a, b) == expected


def test_edit_distance_matches_independent_reference_over_random_strings() -> None:
    """Property-style check: generate random short string pairs (fixed seed, reproducible)
    and assert the fast DP implementation agrees with a slow, independently-written one."""
    rng = random.Random(20260919)
    alphabet = string.ascii_lowercase + "01./-@"
    for _ in range(200):
        a = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 10)))
        b = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 10)))
        assert edit_distance(a, b) == _reference_distance(a, b), (a, b)


# --------------------------------------------------------------------------- normalise_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://www.coursera.org/", "coursera.org"),
        ("http://coursera.org", "coursera.org"),
        ("coursera.org/", "coursera.org"),
        ("COURSERA.ORG", "coursera.org"),
        ("www.coursera.org", "coursera.org"),
    ],
)
def test_normalise_url_strips_scheme_www_trailing_slash_and_case(raw: str, expected: str) -> None:
    assert normalise_url(raw) == expected


# --------------------------------------------------------------------------- genuine OCR noise


GENUINE_NOISE_CASES = [
    # (label, candidate, kind, ocr_texts) -- all must be VERIFIED (survive the gate).
    (
        "plan's own example: coursera.org vs coursero.org (ED1)",
        "coursera.org",
        "url",
        ["coursero.org"],
    ),
    ("l misread as 1, twice (ED2)", "llm-course", "title", ["11m-course"]),
    ("O misread as 0, twice (ED2)", "coursera.org", "url", ["c0ursera.0rg"]),
    ("single character swap in a handle (ED1)", "@learnwithdata", "handle", ["@leornwithdata"]),
    ("exact match, different case", "Coursera.org", "url", ["coursera.org"]),
    ("scheme/www present on one side only", "coursera.org", "url", ["https://www.coursera.org"]),
    (
        "OCR joined a spaced title into one run",
        "Attention Is All You Need",
        "title",
        ["AttentionIsAllYouNeed"],
    ),
    (
        "OCR split a URL across two on-screen rows",
        "github.com/mlabonne/llm-course",
        "url",
        ["github.com/mlabonne/", "llm-course"],
    ),
    ("trailing slash noise", "kaggle.com/learn", "url", ["kaggle.com/learn/"]),
    ("digit-letter confusion in a course code", "CS229", "title", ["C5229"]),
]


@pytest.mark.parametrize(
    ("label", "candidate", "kind", "ocr_texts"),
    GENUINE_NOISE_CASES,
    ids=[c[0] for c in GENUINE_NOISE_CASES],
)
def test_genuine_ocr_noise_survives(label, candidate, kind, ocr_texts) -> None:
    assert is_verified(candidate, ocr_texts, kind) is True, label


# --------------------------------------------------------------------------- planted fakes


PLANTED_FAKE_CASES = [
    # (label, candidate, kind, ocr_texts) -- all must be REJECTED (caught by the gate).
    ("different domain entirely", "coursera.org", "url", ["check out udemy.com instead"]),
    (
        "same domain, path beyond ED2",
        "github.com/mlabonne/llm-course",
        "url",
        ["github.com/other-author/some-different-repo"],
    ),
    (
        "invented handle, none present",
        "@realcreator",
        "handle",
        ["no handles anywhere in this text"],
    ),
    (
        "invented handle, different from the real one",
        "@invented_handle",
        "handle",
        ["@learnwithdata"],
    ),
    (
        "invented proper-noun title",
        "The Great Fake Movie",
        "title",
        ["A totally different film about cats"],
    ),
    (
        "invented title close in topic but not text",
        "Attention Is All You Even",
        "title",
        ["a video about transformers and self-attention mechanisms in deep learning models"],
    ),
    (
        "plausible-looking but wrong TLD/path",
        "coursera.org/fake-course-xyz",
        "url",
        ["coursera.org/real-course"],
    ),
]


@pytest.mark.parametrize(
    ("label", "candidate", "kind", "ocr_texts"),
    PLANTED_FAKE_CASES,
    ids=[c[0] for c in PLANTED_FAKE_CASES],
)
def test_planted_fakes_are_caught(label, candidate, kind, ocr_texts) -> None:
    assert is_verified(candidate, ocr_texts, kind) is False, label


def test_fake_url_inside_summary_text_is_stripped_and_recorded() -> None:
    draft = FusionDraft(
        title="Free deep learning course",
        summary="Great course, also check bit.ly/totally-fake-link for bonus material",
        bullets=["covers python basics"],
        entities={"urls": [], "handles": [], "titles": []},
        language="en",
    )
    gated = gate(draft, ocr_texts=["Practical Deep Learning", "course.fast.ai"], caption=None)
    assert "bit.ly/totally-fake-link" not in gated.summary
    assert "Great course, also check" in gated.summary
    reasons = [d for d in gated.dropped_entities if d.value == "bit.ly/totally-fake-link"]
    assert len(reasons) == 1
    assert reasons[0].location == "summary"
    assert reasons[0].kind == "url"


def test_fake_handle_inside_bullet_is_stripped_and_recorded() -> None:
    draft = FusionDraft(
        title="A recipe video",
        summary="A quick recipe.",
        bullets=["follow @totally_invented_chef for more", "add onions first"],
        entities={"urls": [], "handles": [], "titles": []},
        language="en",
    )
    gated = gate(draft, ocr_texts=["Paneer Bhurji", "10 min"], caption=None)
    assert not any("@totally_invented_chef" in b for b in gated.bullets)
    kinds_dropped = {(d.kind, d.value) for d in gated.dropped_entities}
    assert ("handle", "@totally_invented_chef") in kinds_dropped


def test_genuine_url_inside_summary_text_survives() -> None:
    draft = FusionDraft(
        title="Free course",
        summary="Available at coursera.org right now",
        bullets=[],
        entities={"urls": [], "handles": [], "titles": []},
        language="en",
    )
    gated = gate(draft, ocr_texts=["coursera.org", "audit it for free"], caption=None)
    assert "coursera.org" in gated.summary
    assert gated.dropped_entities == []


def test_gate_drops_from_entities_and_keeps_verified_ones() -> None:
    draft = FusionDraft(
        title="Free deep learning course from fast.ai",
        summary="A free, practical deep learning course.",
        bullets=["covers python", "covers deep learning"],
        entities={
            "urls": ["course.fast.ai", "totally-fake-domain.biz"],
            "handles": ["@invented99"],
            "titles": ["Practical Deep Learning", "A Completely Different Movie"],
        },
        language="en",
    )
    gated = gate(draft, ocr_texts=["Practical Deep Learning", "course.fast.ai"], caption=None)
    assert gated.entities["urls"] == ["course.fast.ai"]
    assert gated.entities["handles"] == []
    assert gated.entities["titles"] == ["Practical Deep Learning"]
    dropped_values = {d.value for d in gated.dropped_entities}
    assert dropped_values == {
        "totally-fake-domain.biz",
        "@invented99",
        "A Completely Different Movie",
    }


# --------------------------------------------------------------------------- allowed_sources


def test_ocr_only_default_drops_a_caption_only_title() -> None:
    """The strict default (AC-3.1 as written): a title spoken/written only in the caption and
    never on screen is dropped. This is the trade-off the milestone report documents."""
    draft = FusionDraft(
        title="Flow (2024)",
        summary="A wordless animated film about a cat.",
        bullets=[],
        entities={"urls": [], "handles": [], "titles": ["Flow"]},
        language="en",
    )
    gated = gate(
        draft,
        ocr_texts=[],  # the film's title never appears on screen in this reel
        caption="Not only was this movie visually stunning, I loved it & so did Kuma",
        allowed_sources="ocr_only",
    )
    assert gated.entities["titles"] == []
    assert any(d.value == "Flow" for d in gated.dropped_entities)


def test_ocr_and_caption_keeps_a_caption_only_title() -> None:
    draft = FusionDraft(
        title="Flow (2024)",
        summary="A wordless animated film about a cat.",
        bullets=[],
        entities={"urls": [], "handles": [], "titles": ["Flow"]},
        language="en",
    )
    gated = gate(
        draft,
        ocr_texts=[],
        caption="Not only was this movie visually stunning, I loved it & so did Flow the cat",
        allowed_sources="ocr_and_caption",
    )
    assert gated.entities["titles"] == ["Flow"]


def test_unknown_allowed_sources_raises() -> None:
    draft = FusionDraft(title="t", summary="s", bullets=[], entities={}, language=None)
    with pytest.raises(ValueError):
        gate(draft, ocr_texts=[], caption=None, allowed_sources="nonsense")


# --------------------------------------------------------------------------- generated / property


def _random_domain(rng: random.Random) -> str:
    label = "".join(rng.choice(string.ascii_lowercase) for _ in range(rng.randint(4, 10)))
    tld = rng.choice(["com", "org", "io", "ai", "net"])
    return f"{label}.{tld}"


def _mutate_beyond_distance_2(domain: str, rng: random.Random) -> str:
    """Replace at least 3 non-overlapping characters with characters not in the original
    string at all, and change the TLD too, so the true edit distance cannot coincidentally
    land at or under 2 no matter how the alignment is chosen."""
    label, _, tld = domain.rpartition(".")
    chars = list(label)
    unused = [c for c in string.ascii_lowercase if c not in domain]
    rng.shuffle(unused)
    positions = rng.sample(range(len(chars)), k=min(3, len(chars)))
    for pos, repl in zip(positions, unused, strict=False):
        chars[pos] = repl
    other_tld = rng.choice([t for t in ["com", "org", "io", "ai", "net", "biz"] if t != tld])
    return "".join(chars) + "." + other_tld


@pytest.mark.parametrize("seed", range(25))
def test_property_random_domains_survive_when_genuine_and_fail_when_invented(seed: int) -> None:
    rng = random.Random(seed)
    domain = _random_domain(rng)
    ocr_texts = [f"visit {domain} today", "some other on-screen text"]

    # Genuine: the model reproduces the domain exactly (or Groq-style scheme/www noise).
    assert is_verified(domain, ocr_texts, "url") is True
    assert is_verified(f"https://www.{domain}/", ocr_texts, "url") is True

    # Invented: a domain far enough away that it cannot be OCR noise of the real one.
    fake = _mutate_beyond_distance_2(domain, rng)
    assert edit_distance(normalise_url(fake), normalise_url(domain)) > 2, (domain, fake)
    assert is_verified(fake, ocr_texts, "url") is False
