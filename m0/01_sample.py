"""M0 step 1: sample 50 hard items from the DM export.

Reads data/raw/message_1.json, decodes mojibake captions, extracts Instagram
shortcodes from share links, and writes a seeded, reproducible 50-item sample
to data/m0/sample.jsonl for the extraction bake-off.

Sample composition (per M0 task spec):
  - 1  the Flow canary (caption contains both "visually stunning" and "Kuma")
  - 15 empty or <40-char captions
  - 10 /p/ posts
  - 10 hashtag-heavy captions (mostly hashtags)
  - 5  Hindi hints (Devanagari chars or common Hinglish words)
  - 9  random
  = 50
"""

import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "message_1.json"
OUT = ROOT / "data" / "m0" / "sample.jsonl"

SEED = 20260919  # today's date, for reproducibility

SHORTCODE_RE = re.compile(r"/(reel|p)/([A-Za-z0-9_-]+)")
DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")
HINGLISH_WORDS = {
    "hai",
    "nahi",
    "kya",
    "kyun",
    "acha",
    "bhai",
    "yaar",
    "kaise",
    "matlab",
    "bahut",
    "sahi",
    "dekho",
    "tumhe",
    "mera",
    "meri",
    "tera",
    "teri",
    "chahiye",
    "karo",
    "kiya",
    "hoga",
    "nahin",
    "bhi",
    "wala",
    "wali",
    "aisa",
    "waise",
    "abhi",
    "kuch",
    "sabse",
    "bilkul",
}


def fix_mojibake(s: str) -> str:
    if s is None:
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s


def extract_shortcode(link: str):
    if not link:
        return None, None
    m = SHORTCODE_RE.search(link)
    if not m:
        return None, None
    kind, code = m.group(1), m.group(2)
    return kind, code


def is_hashtag_heavy(caption: str) -> bool:
    if not caption:
        return False
    tokens = caption.split()
    if not tokens:
        return False
    hashtags = [t for t in tokens if t.startswith("#")]
    non_hashtag_chars = len(re.sub(r"#\S+", "", caption).strip())
    # "mostly hashtags": majority of tokens are hashtags, and little
    # non-hashtag text remains
    return len(hashtags) >= 3 and (len(hashtags) / len(tokens) >= 0.5 or non_hashtag_chars < 15)


def has_hindi_hint(caption: str) -> bool:
    if not caption:
        return False
    if DEVANAGARI_RE.search(caption):
        return True
    words = set(re.findall(r"[a-zA-Z]+", caption.lower()))
    return len(words & HINGLISH_WORDS) >= 1


def main():
    data = json.loads(RAW.read_text())
    messages = data["messages"]

    items = {}  # shortcode -> record (first occurrence wins for uniqueness)
    non_instagram = []
    for msg in messages:
        share = msg.get("share")
        if not share or "link" not in share:
            continue
        link = share.get("link", "")
        kind, code = extract_shortcode(link)
        if not code:
            non_instagram.append(link)
            continue
        if code in items:
            continue
        caption = fix_mojibake(share.get("share_text", "") or "")
        owner = fix_mojibake(share.get("original_content_owner", "") or "")
        items[code] = {
            "shortcode": code,
            "kind": kind,  # "reel" or "p"
            "link": link,
            "caption": caption,
            "original_content_owner": owner,
            "timestamp_ms": msg.get("timestamp_ms"),
        }

    all_items = list(items.values())
    print(f"unique instagram shortcodes: {len(all_items)}")
    print(f"reel: {sum(1 for i in all_items if i['kind'] == 'reel')}")
    print(f"p:    {sum(1 for i in all_items if i['kind'] == 'p')}")
    print(f"non-instagram / unresolved share links: {len(non_instagram)}")

    # --- Flow canary ---
    flow_candidates = [
        i for i in all_items if "visually stunning" in i["caption"] and "Kuma" in i["caption"]
    ]
    if len(flow_candidates) != 1:
        raise SystemExit(f"expected exactly 1 Flow canary, found {len(flow_candidates)}")
    flow = flow_candidates[0]
    print(f"Flow canary: shortcode={flow['shortcode']} kind={flow['kind']}")

    remaining = [i for i in all_items if i["shortcode"] != flow["shortcode"]]

    rng = random.Random(SEED)

    def take(pool, n, predicate, tag):
        matches = [i for i in pool if predicate(i)]
        rng.shuffle(matches)
        chosen = matches[:n]
        for c in chosen:
            c["sample_reason"] = tag
        chosen_codes = {c["shortcode"] for c in chosen}
        new_pool = [i for i in pool if i["shortcode"] not in chosen_codes]
        return chosen, new_pool, len(matches)

    pool = remaining

    empty_short, pool, n_empty = take(
        pool, 15, lambda i: len(i["caption"].strip()) < 40, "empty_or_short_caption"
    )
    p_posts, pool, n_p = take(pool, 10, lambda i: i["kind"] == "p", "p_post")
    hashtag_heavy, pool, n_hash = take(
        pool, 10, lambda i: is_hashtag_heavy(i["caption"]), "hashtag_heavy"
    )
    hindi_hint, pool, n_hindi = take(pool, 5, lambda i: has_hindi_hint(i["caption"]), "hindi_hint")

    print(f"pool sizes available -> empty/short:{n_empty} p:{n_p} hashtag:{n_hash} hindi:{n_hindi}")

    got_so_far = len(empty_short) + len(p_posts) + len(hashtag_heavy) + len(hindi_hint)
    n_random = 50 - 1 - got_so_far
    rng.shuffle(pool)
    random_items = pool[:n_random]
    for r in random_items:
        r["sample_reason"] = "random"

    flow["sample_reason"] = "flow_canary"

    sample = [flow] + empty_short + p_posts + hashtag_heavy + hindi_hint + random_items
    print(
        f"total sampled: {len(sample)} "
        f"(flow=1 empty={len(empty_short)} p={len(p_posts)} "
        f"hashtag={len(hashtag_heavy)} hindi={len(hindi_hint)} "
        f"random={len(random_items)})"
    )

    if len(sample) != 50:
        print("WARNING: sample size is not exactly 50 due to pool shortages")

    # de-dup check
    codes = [s["shortcode"] for s in sample]
    assert len(codes) == len(set(codes)), "duplicate shortcodes in sample"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as f:
        for item in sample:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
