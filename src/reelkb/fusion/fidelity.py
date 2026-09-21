"""The fidelity gate (AC-3.1 / AC-FIDELITY) — "the single most important correctness
boundary in the project."

D7: OCR reads, the model interprets, never the reverse. The model is free to *summarise* and
*organise* what the three channels say, but every URL, @handle, and proper-noun title it
outputs must be traceable back to source text within edit distance 2, or it is thrown away.
This is what turns "trust the model" into a test that fails loudly (`test_fidelity_gate.py`)
the moment a model invents a plausible-looking URL that was never on screen.

Edit distance forgives OCR misreading `l` as `1`, or `coursera.org` as `coursero.org` (both
distance 1), and the budget scales with length (``allowed_distance``) so that a short entity
cannot slip through on coincidence.

**What this gate does not do**, stated plainly because an earlier version of this docstring
claimed otherwise and the M5 checker disproved it: edit distance 2 does *not* guarantee a
different destination is rejected. `course.fast.io` is 2 edits from `course.fast.ai` and is a
different site; `coursefast.ai` is 1 edit (a deleted dot) and is a different domain. Those pass.
The guarantee is narrower and worth stating exactly: **a url, handle or title that resembles
nothing on screen is rejected.** One that closely resembles something on screen is accepted,
including when the resemblance is misleading. Homoglyph lookalikes are the one case singled out
for stricter treatment (see ``is_verified``), because they are indistinguishable by eye.

Proper-noun titles in the card's **prose** are flagged rather than removed -- see
``_flag_unverified_names`` and ``decisions/004``. AC-3.1 is **not met** as written; that is a
recorded miss awaiting the owner's post-judging decision, not a redefinition of the target.

Default allowed source is OCR text only (``ocr_only``), exactly as AC-3.1 is written: "absent
from that reel's OCR output". ``ocr_and_caption`` is implemented but never the default -- it
weakens the guarantee, so it is a deliberate opt-in that belongs to the owner, not a default
anyone can drift into. Whether the *transcript* should also count is deferred to the same
post-judging decision.

No dependency is used for edit distance; it is implemented here (`edit_distance`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

from reelkb.fusion.types import (
    DroppedEntity,
    EntityKind,
    FlaggedName,
    FusionDraft,
    GatedFusion,
    TextLocation,
)

MAX_EDIT_DISTANCE = 2

# A URL needs at least one dotted label pair and a plausible (2-24 letter) TLD, so we don't
# false-positive on "e.g." or "3.14". Path/query is optional and stops at whitespace or a
# closing bracket/quote, which is enough for OCR/caption/summary text (never HTML).
URL_RE = re.compile(
    r"""(?ix)
    \b
    (?:https?://)?
    (?:www\.)?
    (?:[a-z0-9][a-z0-9-]{0,61}\.)+   # one or more "label."
    [a-z]{2,24}                      # TLD
    (?:/[^\s"'<>\)\]]*)?             # optional path
    """,
    re.VERBOSE,
)

HANDLE_RE = re.compile(r"@[^\W\d_][\w.\-]{1,30}", re.UNICODE)

# Suffixes that make something a filename or a library, not a web address. Several are also
# real country TLDs (.py is Paraguay, .sh is Saint Helena, .md is Moldova), so the suffix
# alone cannot decide -- but "main.py" in a bullet is a file every time, and the gate STRIPS
# what it reads as an unverifiable URL. Found by code review after the M5 fixes: "Run main.py
# first" became "Run first", and "Uses Vue.js and main.py" lost its ending. That is the card
# destruction decisions/004 refused to accept for names, arriving by another route.
# A scheme, a "www.", or a path still wins -- "python.org/downloads" is a URL whatever it ends in.
NON_URL_SUFFIXES = frozenset(
    """
    py js jsx ts tsx mjs cjs md txt json yml yaml sh bash zsh rb go rs css scss sass html htm
    java kt swift cpp cc cxx c h hpp php sql csv tsv png jpg jpeg gif svg webp mp4 mov avi mp3
    wav flac pdf doc docx xls xlsx ppt pptx ipynb toml ini cfg conf lock log exe dll app zip
    tar gz bz2 xz rar env gitignore dockerfile makefile lua dart scala clj ex exs vue svelte
    """.split()
)


def _looks_like_a_file_not_a_url(match: str) -> bool:
    lowered = match.strip().lower()
    if lowered.startswith(("http://", "https://", "www.")) or "/" in lowered:
        return False
    return lowered.rsplit(".", 1)[-1] in NON_URL_SUFFIXES


# A run of capitalised words, optionally joined by lowercase connectors, optionally followed by
# a (YYYY) parenthetical: "Dune", "Denis Villeneuve", "Machine Learning Specialization",
# "The Lord of the Rings", "Nosferatu (2024)". This is a heuristic, not a parser -- see
# _is_checkable_proper_noun for what stops it mangling ordinary prose.
PROPER_NOUN_RE = re.compile(
    r"""
    \b[A-Z][A-Za-z0-9'’]*
    (?:
        [ ](?:of|the|de|la|du|von|van)[ ][A-Z][A-Za-z0-9'’]*
      | [ ][A-Z][A-Za-z0-9'’]*
    )*
    (?:[ ]\(\d{4}\))?
    """,
    re.VERBOSE,
)

# Capitalised words that carry no evidence of being a name: sentence openers and the generic
# vocabulary of reel captions. A single capitalised word from this list is never treated as a
# proper-noun candidate, so ordinary prose ("Explains gradient descent", "Free deep learning
# course") survives the gate intact.
COMMON_CAPITALISED_WORDS = frozenset(
    """
    a an and are as at be been but by can could did do does for from get gets go goes had has
    have he her here hers him his how i if in into is it its just like make makes may me more
    most my no not now of off on once one only or other our out over own she should so some
    such than that the their them then there these they this those to too up us use uses very
    was watch we were what when where which while who why will with would you your
    all also always any because before best big both check comes complete day days easy every
    explains free full good great guide help here's how's learn learning lets let's look looks
    new news next nice quick real save saw see simple start starts step steps stop take takes
    that's these things think tips today top try turn use using want watch ways week weeks
    what's why's work works year years yes ok okay plus pro top-tier must need needs full-time
    provides shares explains covers expresses identify begin describes shows features
    includes highlights demonstrates discusses mentions offers presents recommends suggests
    encourages notes compares reviews details outlines lists teaches walks emphasises
    emphasizes warns advises reminds asks answers claims argues adds ends opens closes
    visually clearly simply finally first second third depicts reflects urges states
    """.split()
)


def edit_distance(a: str, b: str) -> int:
    """Levenshtein distance between ``a`` and ``b``. Plain iterative DP, no dependency."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(
                prev[j] + 1,  # deletion
                curr[j - 1] + 1,  # insertion
                prev[j - 1] + cost,  # substitution
            )
        prev = curr
    return prev[-1]


def normalise_url(value: str) -> str:
    """Strip scheme, ``www.``, and a trailing slash; lowercase. Same domain, different
    written form, should compare as equal (distance 0), not accrue a spurious edit cost."""
    v = value.strip().lower()
    v = re.sub(r"^[a-z]+://", "", v)
    v = re.sub(r"^www\.", "", v)
    v = v.rstrip("/")
    return v


def _normalise(value: str, kind: EntityKind) -> str:
    if kind == "url":
        return normalise_url(value)
    if kind == "handle":
        return value.strip().lower().lstrip("@")
    return re.sub(r"\s+", " ", value.strip().lower())  # title: collapse whitespace


_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-/:@]*")


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


MIN_LEN_FOR_WINDOW_MATCH = 8
MAX_NGRAM_TOKENS = 8
NON_ASCII_RE = re.compile(r"[^\x00-\x7f]")


def allowed_distance(cand_norm: str, max_distance: int = MAX_EDIT_DISTANCE) -> int:
    """How many edits a candidate of this length may be away from source text.

    A flat "edit distance 2" is meaningless for short strings: at 2 edits, every 4-letter
    string is within reach of a large share of all 4-letter strings, so the test stops
    discriminating. The M5 checker measured exactly that against a realistic OCR payload --
    100% of random invented 2- and 3-letter titles passed, and 66% of 4-letter ones. Short
    film titles ("Dune", "Coco", "Up", "Her") are precisely this archive's content, so the
    hole sat directly under the most common case.

    Scaling the budget with length (0 edits below 4 characters, 1 up to 7, 2 above) keeps
    distance 2 where the plan wants it -- the `coursera.org` -> `coursero.org` OCR slip is 12
    characters long -- while requiring a short entity to actually be there.
    """
    return min(max_distance, len(cand_norm) // 4)


def _token_ngrams(tokens: Sequence[str], kind: EntityKind) -> set[str]:
    """Every run of up to ``MAX_NGRAM_TOKENS`` adjacent tokens, joined with and without spaces.

    Joining without spaces is what lets a candidate match text OCR ran together; capping the
    run at a few tokens is what stops a candidate being assembled out of an entire screenful
    of unrelated words.
    """
    out: set[str] = set()
    for start in range(len(tokens)):
        for length in range(1, min(MAX_NGRAM_TOKENS, len(tokens) - start) + 1):
            run = tokens[start : start + length]
            spaced = " ".join(run)
            out.add(_normalise(spaced, kind))
            if length > 1:
                out.add(_normalise("".join(run), kind))
    return out


def _windows(text: str, target_len: int, max_distance: int) -> Iterable[str]:
    """Substring windows of about ``target_len`` characters.

    Only used for candidates of at least ``MIN_LEN_FOR_WINDOW_MATCH`` characters -- see
    ``is_verified``. An arbitrary character window is the loosest possible comparison, and for
    a short candidate it degenerates: the M5 checker found the title "Dune" matching the
    single-character window 'S'. Long candidates need it (OCR splits a long URL across lines),
    and at that length a window match is genuinely informative.
    """
    n = len(text)
    if n == 0 or target_len <= 0:
        return
    lo = max(1, target_len - max_distance)
    hi = target_len + max_distance
    if n <= hi:
        yield text
        return
    for length in range(lo, hi + 1):
        for i in range(n - length + 1):
            yield text[i : i + length]


def _close_enough(cand: str, other: str, max_distance: int) -> bool:
    # Cheap O(1) reject before the O(len*len) DP: distance can't be smaller than the length
    # gap, so wildly different lengths are never worth comparing.
    if abs(len(other) - len(cand)) > max_distance:
        return False
    return edit_distance(cand, other) <= max_distance


def _appears_verbatim(candidate: str, source_texts: Sequence[str]) -> bool:
    folded = candidate.strip().lower()
    return any(folded in (s or "").lower() for s in source_texts)


MIN_LEN_FOR_SUBSTRING_MATCH = 4


def _appears_at_word_boundary(candidate: str, source_texts: Sequence[str]) -> bool:
    """True if ``candidate`` occurs verbatim in source text, bounded by non-letter characters.

    Zero edits: the characters really are on screen. This is what lets the model refer to
    ``fast.ai`` when OCR captured ``course.fast.ai`` -- a sub-span of a longer token, so no
    token or n-gram comparison would ever match it, yet plainly not an invention.

    The boundary requirement is what stops this from re-opening the short-candidate hole: the
    title "Up" is not verified by the text "group", because the 'up' inside it is surrounded
    by letters. Sub-span matching also needs a floor on length, or every two-letter string
    finds itself somewhere.
    """
    if len(candidate) < MIN_LEN_FOR_SUBSTRING_MATCH:
        return False
    pattern = re.compile(rf"(?<![^\W\d_]){re.escape(candidate)}(?![^\W\d_])", re.IGNORECASE)
    return any(pattern.search(s) for s in source_texts)


def is_verified(
    candidate: str,
    source_texts: Sequence[str],
    kind: EntityKind,
    *,
    max_distance: int = MAX_EDIT_DISTANCE,
) -> bool:
    """True if ``candidate`` (a url/handle/title from the model) is close enough to something
    in ``source_texts`` to be believed.

    "Close enough" is deliberately anchored to word boundaries rather than to arbitrary
    character positions. A candidate is compared against every token and every short run of
    adjacent tokens (joined with and without spaces, since OCR both splits and joins overlay
    lines). Only candidates of at least ``MIN_LEN_FOR_WINDOW_MATCH`` characters are also
    compared against free-floating substring windows, and only URLs -- which OCR really does
    break across lines -- are matched against all source rows concatenated together.

    The edit budget scales with length (``allowed_distance``), so a short entity has to
    genuinely be on screen rather than merely resemble some fragment of the text.
    """
    cand_norm = _normalise(candidate, kind)
    if not cand_norm:
        return False

    non_empty = [s for s in source_texts if s and s.strip()]
    if not non_empty:
        return False

    # A url or handle carrying non-ASCII characters is either genuinely non-Latin text or a
    # homoglyph lookalike of a real destination ('cоurse.fast.ai' with a Cyrillic 'o' is a
    # different domain entirely). Fuzzy matching cannot tell those apart, and getting it wrong
    # means storing a link that goes somewhere the owner did not expect -- so require the
    # exact characters to appear on screen. (M5 checker, findings 5 and 6.)
    if kind in ("url", "handle") and NON_ASCII_RE.search(candidate):
        return _appears_verbatim(candidate, non_empty)

    # A url's top-level domain must appear on screen, exactly. Edit distance is the right
    # tolerance for OCR noise inside a name, but `.io` is not a noisy reading of `.ai` -- it is
    # a different site, and a wrong link is the most harmful thing this gate can pass. The M5
    # checker demonstrated `course.fast.io` sailing through on 2 edits from `course.fast.ai`.
    if kind == "url":
        host = cand_norm.split("/")[0]
        tld = host.rsplit(".", 1)[-1] if "." in host else ""
        # One edit of slack, because OCR misreads the suffix too ("c0ursera.0rg" is a real
        # fixture). That still separates the cases: '0rg'/'org' is one edit, 'io'/'ai' is two.
        # Skipped entirely when the source shows no domain-shaped token at all, so a URL whose
        # dot OCR simply lost ("coursera org") is judged by the ordinary matching below.
        source_tlds = {
            m.group(1).lower()
            for s in non_empty
            for m in re.finditer(r"\.([a-z0-9]{2,24})\b", s, re.IGNORECASE)
        }
        if tld and source_tlds and not any(edit_distance(tld, t) <= 1 for t in source_tlds):
            return False

    budget = allowed_distance(cand_norm, max_distance)
    cand_forms = {cand_norm, re.sub(r"\s+", "", cand_norm)}

    # Zero edits first: the exact characters, bounded by non-letters, somewhere on screen.
    if any(_appears_at_word_boundary(cand, non_empty) for cand in cand_forms):
        return True

    for src in non_empty:
        for form in _token_ngrams(_tokens(src), kind):
            if any(_close_enough(cand, form, budget) for cand in cand_forms):
                return True

    if len(cand_norm) >= MIN_LEN_FOR_WINDOW_MATCH:
        for src in non_empty:
            for text in (src, re.sub(r"\s+", "", src)):
                for cand in cand_forms:
                    for win in _windows(text, len(cand), budget):
                        if _close_enough(cand, _normalise(win, kind), budget):
                            return True
        if kind == "url" and len(non_empty) > 1:
            # Only URLs are reassembled across separate OCR rows. Allowing it for titles let
            # the checker build the invented title 'PYTHONBASICSTHE' out of two unrelated
            # lines of an on-screen list.
            combined = "".join(re.sub(r"\s+", "", s) for s in non_empty)
            for cand in cand_forms:
                for win in _windows(combined, len(cand), budget):
                    if _close_enough(cand, _normalise(win, kind), budget):
                        return True
    return False


def _source_texts(ocr_texts: Sequence[str], caption: str | None, allowed_sources: str) -> list[str]:
    texts = list(ocr_texts)
    if allowed_sources == "ocr_and_caption" and caption:
        texts.append(caption)
    return texts


def _gate_entity_list(
    values: Iterable[str],
    kind: EntityKind,
    source_texts: Sequence[str],
) -> tuple[list[str], list[DroppedEntity]]:
    kept: list[str] = []
    dropped: list[DroppedEntity] = []
    for value in values:
        if not value or not value.strip():
            continue
        if is_verified(value, source_texts, kind):
            kept.append(value)
        else:
            dropped.append(
                DroppedEntity(
                    kind=kind,
                    value=value,
                    reason=(
                        f"no source text within edit distance {MAX_EDIT_DISTANCE} "
                        f"(fidelity gate, AC-3.1)"
                    ),
                    location="entities",
                )
            )
    return kept, dropped


def _scan_and_strip_unverified(
    text: str, location: TextLocation, source_texts: Sequence[str]
) -> tuple[str, list[DroppedEntity]]:
    """Regex-scan free text (title/summary/one bullet) for URLs and @handles; strip any that
    the gate can't verify, and record why. Proper-noun titles are not regex-scanned here —
    there is no reliable regex for a proper noun, which is exactly why the model reports them
    as a labelled ``entities.titles`` list instead of us hunting for them in prose."""
    dropped: list[DroppedEntity] = []
    spans: list[tuple[int, int, str, EntityKind]] = []
    for m in URL_RE.finditer(text):
        if _looks_like_a_file_not_a_url(m.group()):
            continue
        spans.append((m.start(), m.end(), m.group(), "url"))
    for m in HANDLE_RE.finditer(text):
        spans.append((m.start(), m.end(), m.group(), "handle"))
    spans.sort(key=lambda s: s[0])

    out = []
    cursor = 0
    for start, end, value, kind in spans:
        if start < cursor:
            continue  # overlapping match (shouldn't happen: URL_RE and HANDLE_RE don't overlap)
        if is_verified(value, source_texts, kind):
            out.append(text[cursor:end])
        else:
            out.append(text[cursor:start])  # drop the matched span itself
            dropped.append(
                DroppedEntity(
                    kind=kind,
                    value=value,
                    reason=(
                        f"no source text within edit distance {MAX_EDIT_DISTANCE} "
                        f"(fidelity gate, AC-3.1)"
                    ),
                    location=location,
                )
            )
        cursor = end
    out.append(text[cursor:])
    cleaned = re.sub(r"[ \t]{2,}", " ", "".join(out)).strip()
    return cleaned, dropped


FLAG_REASON = "name not confirmed by on-screen text (fidelity gate, AC-3.1 -- kept, not removed)"

_SENTENCE_BREAK_RE = re.compile(r"[.!?:]\s+|\n")


TITLE_CASE_MIN_WORDS = 3
TITLE_CASE_RATIO = 0.6


def _is_title_cased(text: str) -> bool:
    """True when most words are capitalised, so capitalisation tells us nothing about names."""
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z0-9'’-]*", text)]
    if len(words) < TITLE_CASE_MIN_WORDS:
        return False
    capitalised = sum(1 for w in words if w[0].isupper())
    return capitalised / len(words) >= TITLE_CASE_RATIO


def _sentence_start_offsets(text: str) -> set[int]:
    """Character offsets where a new sentence begins, so a capitalised word there can be
    recognised as 'just the first word' rather than a name."""
    offsets = {0}
    for m in _SENTENCE_BREAK_RE.finditer(text):
        offsets.add(m.end())
    return offsets


def _flag_unverified_names(
    text: str,
    location: TextLocation,
    source_texts: Sequence[str],
    rejected_values: set[str],
) -> list[FlaggedName]:
    """Find name-shaped phrases in prose that on-screen text cannot confirm. Never edits.

    Two things make this usable rather than noise, both measured against the 50 real M0
    items before being chosen:

    * A single capitalised word at the start of a sentence is skipped unless the model itself
      declared it as an entity. Model prose is full of sentence-opening verbs -- "Provides",
      "Shares", "Begin", "Expresses" -- and a naive scan flagged all of them, 294 hits across
      49 of the 50 items.
    * A single capitalised word from ``COMMON_CAPITALISED_WORDS`` is never a candidate.

    A name the model *declared* and the gate *rejected* is always flagged wherever it appears,
    sentence position notwithstanding: the gate has already judged that one unverifiable, so
    leaving it unmarked in the headline is the exact inconsistency the M5 checker found.
    """
    if not text.strip():
        return []
    # In Title Case, capitalisation says nothing: "Free ML Learning Resources", "Parent-Teen
    # Social Media Conflict" and "Step-by-Step LeetCode Problem Solving Guide" are ordinary
    # phrasing, not names. Measured on the 50 real M0 items, treating them as names put a flag
    # on 46 of 50 cards -- a badge on 92% of the library tells the owner nothing. Where the
    # signal is absent, only names the model itself declared (and the gate rejected) count.
    title_cased = _is_title_cased(text)
    starts = _sentence_start_offsets(text)
    flagged: list[FlaggedName] = []
    seen: set[str] = set()

    # First, the reliable half: anything the gate already rejected from the entity list, found
    # by looking for those exact words rather than by pattern. The pattern alone is not enough
    # -- in "Directed By Robert Eggers For Max" the whole capitalised run matches as a single
    # phrase, so a rejected "Robert Eggers" sitting inside it was never noticed.
    for rejected in sorted(rejected_values):
        if not rejected or rejected in seen:
            continue
        found = re.search(rf"(?<![^\W\d_]){re.escape(rejected)}(?![^\W\d_])", text, re.IGNORECASE)
        if found:
            seen.add(rejected)
            flagged.append(FlaggedName(value=found.group(), location=location, reason=FLAG_REASON))
    for m in PROPER_NOUN_RE.finditer(text):
        value = m.group().strip()
        if not value or value.lower() in seen:
            continue
        was_rejected = value.lower() in rejected_values
        if title_cased and not was_rejected:
            continue
        # "Provides URLs", "Shows Docker" -- a bullet opening with a summariser's verb. The
        # verb is capitalised only because it starts the sentence, so drop it and judge what
        # follows; the single-word rules below then apply to the remainder as they should.
        words = value.split()
        if (
            not was_rejected
            and m.start() in starts
            and len(words) > 1
            and words[0].lower() in COMMON_CAPITALISED_WORDS
        ):
            value = " ".join(words[1:])
            if not value or value.lower() in seen:
                continue
        single_word = len(value.split()) == 1
        if single_word and value.lower() in COMMON_CAPITALISED_WORDS and not was_rejected:
            continue
        # A title is a noun phrase, not a sentence, so its first word carries no "this is
        # merely how sentences start" excuse -- and a bare film name ("Nosferatu") is the
        # commonest shape a fabricated headline takes. Summaries and bullets are sentences,
        # where the opening word is usually a verb.
        sentence_initial = m.start() in starts
        if single_word and sentence_initial and not was_rejected:
            # In a title of three words or fewer, the first word IS the subject
            # ("Nosferatu", "Dune: Part Two"). In a longer, sentence-like title
            # ("Visually stunning cat movie praised by creator") it is just a word.
            if location != "title" or len(text.split()) > 3:
                continue
        if is_verified(value, source_texts, "title"):
            continue
        seen.add(value.lower())
        flagged.append(FlaggedName(value=value, location=location, reason=FLAG_REASON))
    return flagged


def gate(
    draft: FusionDraft,
    *,
    ocr_texts: Sequence[str],
    caption: str | None,
    allowed_sources: str = "ocr_only",
) -> GatedFusion:
    """Run the fidelity gate over one model draft. Pure function, no I/O.

    ``allowed_sources``: ``"ocr_only"`` (default, matches AC-3.1 as written) or
    ``"ocr_and_caption"`` (implemented, not default — see the trade-off in the milestone
    report and in ``reelkb.fusion.stage``'s module docstring).
    """
    if allowed_sources not in ("ocr_only", "ocr_and_caption"):
        raise ValueError(f"unknown allowed_sources {allowed_sources!r}")

    source_texts = _source_texts(ocr_texts, caption, allowed_sources)
    all_dropped: list[DroppedEntity] = []

    urls, d = _gate_entity_list(draft.entities.get("urls", []), "url", source_texts)
    all_dropped += d
    handles, d = _gate_entity_list(draft.entities.get("handles", []), "handle", source_texts)
    all_dropped += d
    titles, d = _gate_entity_list(draft.entities.get("titles", []), "title", source_texts)
    all_dropped += d

    title, d = _scan_and_strip_unverified(draft.title, "title", source_texts)
    all_dropped += d
    summary, d = _scan_and_strip_unverified(draft.summary, "summary", source_texts)
    all_dropped += d

    bullets = []
    for bullet in draft.bullets:
        cleaned, d = _scan_and_strip_unverified(bullet, "bullets", source_texts)
        all_dropped += d
        if cleaned:
            bullets.append(cleaned)

    # Names are flagged, never stripped -- see FlaggedName. Run over the text the URL/handle
    # pass already cleaned, so a name is not reported inside a span that has just been removed.
    rejected = {d.value.strip().lower() for d in all_dropped}
    flagged: list[FlaggedName] = []
    flagged += _flag_unverified_names(title, "title", source_texts, rejected)
    flagged += _flag_unverified_names(summary, "summary", source_texts, rejected)
    for bullet in bullets:
        flagged += _flag_unverified_names(bullet, "bullets", source_texts, rejected)

    return GatedFusion(
        title=title,
        summary=summary,
        bullets=bullets,
        entities={"urls": urls, "handles": handles, "titles": titles},
        dropped_entities=all_dropped,
        language=draft.language,
        unverified_names=flagged,
    )
