"""The two holes the M5 checker found in the fidelity gate, and the rules that close them.

Both were open while all 85 fusion tests were green, because every planted fake in
``test_fidelity_gate.py`` is at least 12 characters long -- above the length band where the
old matching collapsed. These tests deliberately live in that band.

Hole 1: short invented entities passed. Measured by the checker against a realistic OCR
payload: 100% of random 2- and 3-letter invented titles kept, 66% of 4-letter ones. "Dune",
"Coco", "Up", "Her" are what this archive is full of.

Hole 2: proper nouns in the card's prose were never checked at all, so a name thrown out of
the entity list could still be the card's headline.
"""

from __future__ import annotations

import random
import string

import pytest

from reelkb.fusion.fidelity import PROPER_NOUN_RE, gate, is_verified
from reelkb.fusion.types import FusionDraft

# A realistic screenful of overlay text: several short lines, numbers, a domain, a handle.
OCR = [
    "FREE MACHINE LEARNING COURSES",
    "1. Andrew Ng on Coursera",
    "2. fast.ai practical deep learning",
    "LINK IN BIO",
    "SAVE THIS FOR LATER",
    "follow @datasciencedaily",
]


# --- hole 1: short entities -------------------------------------------------------------


@pytest.mark.parametrize("fake", ["Dune", "Coco", "Flow", "Her", "Up", "Arca", "Nope"])
def test_a_short_invented_film_title_does_not_pass(fake: str) -> None:
    assert not is_verified(fake, OCR, "title")


@pytest.mark.parametrize("fake", ["@ai", "@ml", "@nyt", "@bbc"])
def test_a_short_invented_handle_does_not_pass(fake: str) -> None:
    assert not is_verified(fake, OCR, "handle")


def test_a_short_handle_whose_name_is_actually_on_screen_does_pass() -> None:
    """'@ng' is verified against "Andrew Ng" -- those exact letters are on screen, standing
    alone. Rejecting it would be the gate refusing evidence it has. (I wrote this test the
    other way round first and the gate was right.)"""
    assert is_verified("@ng", OCR, "handle")


@pytest.mark.parametrize("length", [2, 3, 4, 5, 6, 8, 12])
def test_random_invented_strings_almost_never_pass_at_any_length(length: int) -> None:
    """The property the old fixtures could not express.

    Not a flat zero, and the exceptions are the gate working rather than failing: a random
    two-letter string is sometimes a word that IS on screen ('on', from "Andrew Ng on
    Coursera"), and a random four-letter one is sometimes a single edit from one ('bipo' vs
    the "BIO" of "LINK IN BIO") -- which is the edit-distance budget the plan asks for.
    Before the fix this measured 100% at lengths 2-3 and 66% at length 4.
    """
    rng = random.Random(f"fidelity-{length}")
    kept = [
        cand
        for _ in range(200)
        if is_verified(
            (cand := "".join(rng.choice(string.ascii_lowercase) for _ in range(length))),
            OCR,
            "title",
        )
    ]
    assert len(kept) <= 2, f"{len(kept)}/200 invented {length}-char titles passed: {kept[:5]}"
    if length >= 6:
        assert kept == [], f"nothing this long should ever coincide: {kept[:5]}"


def test_a_short_word_hiding_inside_a_longer_one_does_not_count() -> None:
    """'up' is inside 'group', but the reel does not say "Up" -- the letters must stand alone."""
    assert not is_verified("Up", ["JOIN THE GROUP TODAY"], "title")
    assert is_verified("Up", ["UP NEXT: PART TWO"], "title")


def test_a_real_short_title_that_is_genuinely_on_screen_still_passes() -> None:
    assert is_verified("Flow", ["this is your sign to watch", "'Flow' with your cat"], "title")


def test_a_substring_of_a_longer_token_passes_at_a_word_boundary() -> None:
    """The model saying 'fast.ai' when OCR captured 'course.fast.ai' is not an invention.

    No token or n-gram comparison can match this -- it is a sub-span of one token -- so
    without the boundary rule the gate wrongly dropped a real domain. Caught when this
    change first broke two existing tests.
    """
    assert is_verified("fast.ai", ["2. course.fast.ai free"], "url")


def test_a_title_is_not_assembled_out_of_two_unrelated_lines() -> None:
    """Only URLs are matched across concatenated OCR rows; OCR splits links, not film names."""
    rows = ["DAY 3 OF LEARNING", "PYTHON BASICS", "THE LOOP"]
    assert not is_verified("PYTHONBASICSTHE", rows, "title")


def test_a_url_split_across_two_ocr_rows_is_still_recognised() -> None:
    assert is_verified("coursera.org/learn", ["go to coursera.", "org/learn today"], "url")


@pytest.mark.parametrize(
    "lookalike",
    ["cоurse.fast.ai", "course.fаst.ai"],  # Cyrillic 'о' / 'а' -- different domains entirely
)
def test_a_homoglyph_domain_is_not_accepted_for_the_real_one(lookalike: str) -> None:
    """These render identically to a human and resolve somewhere else. Fuzzy matching cannot
    tell them apart, so non-ASCII urls must appear on screen exactly as written."""
    assert not is_verified(lookalike, ["visit course.fast.ai for the course"], "url")


def test_a_genuinely_non_latin_handle_still_passes_when_it_is_on_screen() -> None:
    assert is_verified("@कोर्स", ["follow @कोर्स for more"], "handle")


# --- hole 2: names in the card's prose ---------------------------------------------------


def _draft(title: str, summary: str = "", bullets: list[str] | None = None, **ents: list[str]):
    return FusionDraft(
        title=title,
        summary=summary,
        bullets=bullets or [],
        entities={"urls": ents.get("urls", []), "handles": [], "titles": ents.get("titles", [])},
        language="en",
    )


def test_an_invented_film_name_in_the_title_is_flagged() -> None:
    """The headline case: before this, the gate never looked at the title at all."""
    gated = gate(
        _draft("Nosferatu (2024)", "A review of Nosferatu."),
        ocr_texts=["a wordless animated film about a cat"],
        caption=None,
    )
    flagged = {f.value for f in gated.unverified_names}
    assert "Nosferatu (2024)" in flagged or "Nosferatu" in flagged


def test_a_name_thrown_out_of_the_entity_list_is_flagged_where_it_survives_in_prose() -> None:
    """The inconsistency the checker demonstrated: dropped from entities, kept as the title."""
    gated = gate(
        _draft("Dune: Part Two", "A review of Dune.", titles=["Dune"]),
        ocr_texts=["THIS IS YOUR SIGN TO WATCH", "with your cat"],
        caption=None,
    )
    assert "Dune" in {d.value for d in gated.dropped_entities}
    assert "Dune" in {f.value for f in gated.unverified_names}


def test_flagging_never_rewrites_the_prose() -> None:
    """The owner's decision: destroying a correct card is worse than surfacing a doubt.

    The M0 item whose card reads "Source Code movie recommendation" has no on-screen text at
    all -- every name in it is unverifiable, and the model got it exactly right.
    """
    draft = _draft("Source Code movie recommendation", "The reel recommends Source Code.")
    gated = gate(draft, ocr_texts=[], caption=None)
    assert gated.title == "Source Code movie recommendation"
    assert gated.summary == "The reel recommends Source Code."
    assert gated.unverified_names != []


def test_ordinary_prose_is_not_flagged_as_a_name() -> None:
    """Sentence-opening verbs and generic words are what a naive scan drowns in: measured at
    294 hits across 49 of the 50 real M0 items before these two rules were added."""
    gated = gate(
        _draft(
            "Free deep learning course",
            "Explains gradient descent. Shares practical tips. Covers the basics.",
            bullets=["Provides a reading list", "Begin with the first lesson"],
        ),
        ocr_texts=["FREE DEEP LEARNING COURSE"],
        caption=None,
    )
    assert [f.value for f in gated.unverified_names] == []


def test_a_verified_name_is_not_flagged() -> None:
    gated = gate(
        _draft("Andrew Ng on Coursera", "Andrew Ng teaches on Coursera."),
        ocr_texts=OCR,
        caption=None,
    )
    assert [f.value for f in gated.unverified_names] == []


def test_the_flag_records_where_each_name_was_found() -> None:
    gated = gate(
        _draft("Nosferatu", "A review.", bullets=["The film was directed by Robert Eggers"]),
        ocr_texts=["nothing relevant here"],
        caption=None,
    )
    locations = {f.location for f in gated.unverified_names}
    assert "title" in locations
    assert "bullets" in locations


def test_known_limit_title_cased_prose_relies_on_the_declared_entity_net() -> None:
    """A recorded miss, not a passing grade.

    Where most words are capitalised there is no signal left to find names by, so the scan
    stands down and only names the model *declared* are caught. "Directed By Robert Eggers"
    reads as Title Case, so Robert Eggers goes unflagged unless the model listed him. The
    alternative -- scanning anyway -- put a flag on 46 of 50 real M0 cards and would make the
    badge meaningless. Closing this properly needs either name recognition or a dictionary,
    both out of scope for v1; revisit with the post-judging AC-3.1 decision.
    """
    unflagged = gate(
        _draft("Reel", "Directed By Robert Eggers For Max"),
        ocr_texts=["nothing relevant"],
        caption=None,
    )
    assert [f.value for f in unflagged.unverified_names if f.location == "summary"] == []

    # ...but declaring it puts it back in reach, wherever it sits in the prose.
    flagged = gate(
        _draft("Reel", "Directed By Robert Eggers For Max", titles=["Robert Eggers"]),
        ocr_texts=["nothing relevant"],
        caption=None,
    )
    assert "Robert Eggers" in {f.value for f in flagged.unverified_names}


def test_the_proper_noun_pattern_finds_multi_word_names() -> None:
    found = {m.group() for m in PROPER_NOUN_RE.finditer("Directed by Denis Villeneuve for Max.")}
    assert "Denis Villeneuve" in found


def test_a_different_top_level_domain_is_a_different_site() -> None:
    """`.io` is not a noisy reading of `.ai`. A wrong link is the worst thing this gate can
    pass -- it sends the owner somewhere the reel never pointed. (M5 checker, finding 5.)"""
    ocr = ["visit course.fast.ai for the free course"]
    assert not is_verified("course.fast.io", ocr, "url")
    assert is_verified("course.fast.ai", ocr, "url")


def test_the_tld_check_still_tolerates_ocr_misreading_the_suffix() -> None:
    """OCR mangles the suffix as readily as the rest: '.0rg' for '.org' is one edit, and real.

    This is why the check allows one edit rather than demanding an exact match -- a rule that
    rejected genuine OCR noise would push the gate into destroying real links.
    """
    assert is_verified("coursera.org", ["c0ursera.0rg"], "url")


def test_the_tld_check_stands_down_when_the_source_shows_no_domain_at_all() -> None:
    """If OCR lost the dot ("coursera org"), there is no suffix to compare against, so the
    ordinary matching decides rather than a rule firing on absent evidence."""
    assert is_verified("coursera.org", ["coursera org audit it free"], "url")
