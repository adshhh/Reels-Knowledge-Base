"""M0 step 8 -- unblind the owner's judgements and aggregate them. Reads `judgements.json`
(blind, from judge.html), `judge_key.json` (X/Y -> pipeline), and `judgement_coding.json` --
the lead's reading of each note as an X/Y/tie preference plus category, ambiguous reads
flagged, since the checkboxes alone can't say which output was *better* (33/50 marked both
"yes"). All local, gitignored. Prints aggregates only -- safe to paste into
`docs/M0_FINDINGS.md` as-is.
"""

import json
from collections import Counter, defaultdict
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
M0 = ROOT / "data" / "m0"

PIPELINES = ("pipeline1", "pipeline2")
LABEL = {
    "pipeline1": "P1 (Vision OCR + Whisper + gpt-oss-120b)",
    "pipeline2": "P2 (Gemini Flash-Lite, whole video)",
}

# The owner's buckets, grouped into families big enough to say anything about. n=1 buckets
# on their own tell you nothing; a family of related ones at least has a chance.
FAMILY = {
    "Movie recommendations": "Screen recs (movie / TV)",
    "TV/web series recommendations": "Screen recs (movie / TV)",
    "ML resources": "Learning & career",
    "AI resources": "Learning & career",
    "Programming resources": "Learning & career",
    "Project resources": "Learning & career",
    "Career related": "Learning & career",
    "Miscellaneous": "Miscellaneous",
    "Music recommendations": "Other (music, YouTube, food)",
    "YouTube video recommendations": "Other (music, YouTube, food)",
    "Food": "Other (music, YouTube, food)",
}


def load_jsonl(path: Path) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {r["shortcode"]: r for r in rows}


def sign_test_p(wins_a: int, wins_b: int) -> float:
    """Two-sided exact binomial sign test: if the two pipelines were really equally good,
    how likely is a split at least this lopsided? Ties are excluded, as the test requires."""
    n = wins_a + wins_b
    if n == 0:
        return 1.0
    k = min(wins_a, wins_b)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)


def tally(items: list[dict]) -> tuple[Counter, str]:
    c: Counter = Counter(i["winner"] for i in items)
    p1, p2, tie = c["pipeline1"], c["pipeline2"], c["tie"]
    line = f"P1 {p1:>2} · P2 {p2:>2} · tie {tie:>2}   (n={len(items)})"
    return c, line


def main() -> None:
    judgements = json.loads((M0 / "judgements.json").read_text())
    key = json.loads((M0 / "judge_key.json").read_text())
    coding = json.loads((M0 / "judgement_coding.json").read_text())
    results = load_jsonl(M0 / "results.jsonl")

    assert set(judgements) == set(key) == set(coding), "judgements, key and coding disagree"

    items = []
    for sc, j in judgements.items():
        k, c, r = key[sc], coding[sc], results.get(sc, {})
        winner = "tie" if c["pref"] == "tie" else k[c["pref"]]
        items.append(
            {
                "winner": winner,
                "subject": {k["X"]: j["subject_X"], k["Y"]: j["subject_Y"]},
                "wrong_link": {k["X"]: j["wrong_link_X"], k["Y"]: j["wrong_link_Y"]},
                "bucket": c["bucket"],
                "family": FAMILY[c["bucket"]],
                "ambiguous": bool(c["flag"]) and "AMBIGUOUS" in c["flag"],
                "note_vs_checkbox": bool(c["flag"]) and "CHECKBOX" in c["flag"],
                "media": r.get("apify_media_type") or r.get("kind") or "?",
                "speech": bool(r.get("vad_speech")),
                "lyric_like": bool(r.get("lyric_like")),
                "unreadable": (r.get("unreadable_frame_count") or 0) > 0,
                "caption_uninformative": bool(r.get("caption_uninformative")),
            }
        )

    print("=" * 78)
    print("M0 -- UNBLINDED JUDGEMENTS (50 hard reels, owner-judged blind)")
    print("=" * 78)

    # ---- 1. Overall preference
    c, line = tally(items)
    print("\n1. WHICH OUTPUT THE OWNER PREFERRED (read from his notes)")
    print("   " + line)
    p = sign_test_p(c["pipeline1"], c["pipeline2"])
    print(f"   sign test, ties excluded: p = {p:.3f}")
    clean = [i for i in items if not i["ambiguous"]]
    c2, line2 = tally(clean)
    p2 = sign_test_p(c2["pipeline1"], c2["pipeline2"])
    print(f"   excluding {len(items) - len(clean)} ambiguous notes: {line2}   p = {p2:.3f}")

    # ---- 2. Subject naming (the checkbox)
    print("\n2. DID IT NAME THE SUBJECT? (owner's checkbox)")
    for pl in PIPELINES:
        s = Counter(i["subject"][pl] for i in items)
        print(f"   {LABEL[pl]:<42} yes {s['yes']:>2} · partly {s['partly']:>2} · no {s['no']:>2}")
    only = Counter()
    for i in items:
        a, b = i["subject"]["pipeline1"], i["subject"]["pipeline2"]
        if a == "yes" and b != "yes":
            only["pipeline1"] += 1
        if b == "yes" and a != "yes":
            only["pipeline2"] += 1
    print(
        f"   fully named by only one pipeline: P1 alone {only['pipeline1']}, "
        f"P2 alone {only['pipeline2']}"
    )

    # ---- 3. Wrong links
    print("\n3. WRONG OR INVENTED LINK FLAGGED (owner's checkbox)")
    for pl in PIPELINES:
        n = sum(i["wrong_link"][pl] for i in items)
        print(f"   {LABEL[pl]:<42} {n} of 50")

    # ---- 4. By category family -- the routing question
    print("\n4. BY CATEGORY -- does the better pipeline depend on the kind of reel?")
    fam: defaultdict[str, list] = defaultdict(list)
    for i in items:
        fam[i["family"]].append(i)
    for name in sorted(fam, key=lambda f: -len(fam[f])):
        c, line = tally(fam[name])
        p = sign_test_p(c["pipeline1"], c["pipeline2"])
        print(f"   {name:<30} {line}   p = {p:.2f}")
    print("   owner's own buckets:")
    buck: defaultdict[str, list] = defaultdict(list)
    for i in items:
        buck[i["bucket"]].append(i)
    for name in sorted(buck, key=lambda b: -len(buck[b])):
        _, line = tally(buck[name])
        print(f"     {name:<32} {line}")

    # ---- 5. By property of the reel
    print("\n5. BY PROPERTY OF THE REEL")
    splits = [
        ("media type", lambda i: i["media"]),
        ("speech detected", lambda i: "speech" if i["speech"] else "no speech"),
        ("sung / lyric-like audio", lambda i: "lyric-like" if i["lyric_like"] else "not"),
        ("some unreadable text", lambda i: "unreadable" if i["unreadable"] else "readable"),
        ("caption uninformative", lambda i: "uninformative" if i["caption_uninformative"] else "informative"),
    ]
    for title, fn in splits:
        print(f"   {title}:")
        grp: defaultdict[str, list] = defaultdict(list)
        for i in items:
            grp[fn(i)].append(i)
        for g in sorted(grp):
            _, line = tally(grp[g])
            print(f"     {g:<20} {line}")

    # ---- 6. Coding caveats
    print("\n6. CODING CAVEATS")
    print(f"   notes read as ambiguous:          {sum(i['ambiguous'] for i in items)}")
    print(f"   note overrode its own checkbox:   {sum(i['note_vs_checkbox'] for i in items)}")


if __name__ == "__main__":
    main()
