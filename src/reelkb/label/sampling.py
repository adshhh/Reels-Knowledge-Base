"""Stratified sampling for the holdout labelling set (PLAN.md §7: 150 reels, ~10 per category).

Discovery happens once per ``data_dir`` and is then frozen to ``data/holdout_sample.json``,
so restarting the labelling page (or the machine) never reshuffles which reels are being
labelled — resuming just means finding the first sampled item with no saved answer yet.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from reelkb.contract.cards import Card

DEFAULT_TARGET = 150
DEFAULT_FLOOR = 10
# Fixed, not tuned: the sample only needs to be *reproducible*, not chosen for any property.
DEFAULT_SEED = 20260919

UNCATEGORISED = "__uncategorised__"


class UnstratifiableError(RuntimeError):
    """A holdout was requested before the cards have categories to stratify by."""


def stratified_sample(
    cards: list[Card],
    *,
    target: int = DEFAULT_TARGET,
    floor: int = DEFAULT_FLOOR,
    seed: int = DEFAULT_SEED,
) -> list[str]:
    """Return sampled item_ids: every category floored at ``floor`` items (or all it has,
    if fewer), remaining slots spread proportionally across categories, seeded throughout.

    On a corpus smaller than ``target`` (e.g. the 27-item fake corpus), every category's
    floor exceeds or matches its size, so the "floor" degenerates to "take everything" and
    the returned list is just the whole corpus, shuffled.
    """
    rng = random.Random(seed)
    by_category: dict[str, list[str]] = {}
    for c in cards:
        by_category.setdefault(c.category_id or UNCATEGORISED, []).append(c.item_id)
    for ids in by_category.values():
        rng.shuffle(ids)  # which items get picked within a category is seeded too

    total_available = sum(len(v) for v in by_category.values())
    n = min(target, total_available)

    floors = {cat: min(floor, len(ids)) for cat, ids in by_category.items()}
    picked = {cat: ids[: floors[cat]] for cat, ids in by_category.items()}
    allocated = sum(floors.values())

    if allocated > n:
        # More categories than room for their floors. Rare at plan scale (12-20 categories,
        # target 150); kept correct anyway via fair round-robin trimming.
        picked = _trim_round_robin(picked, n, rng)
    else:
        remaining_pool = {cat: ids[floors[cat] :] for cat, ids in by_category.items()}
        picked = _top_up(picked, remaining_pool, n - allocated, rng)

    result = [item_id for ids in picked.values() for item_id in ids]
    rng.shuffle(result)
    return result


def _top_up(
    picked: dict[str, list[str]],
    remaining_pool: dict[str, list[str]],
    slots: int,
    rng: random.Random,
) -> dict[str, list[str]]:
    """Distribute ``slots`` more items across categories, proportional to their leftover
    pool size, using largest-remainder rounding so the total lands exactly on ``slots``."""
    if slots <= 0:
        return picked
    total_remaining = sum(len(v) for v in remaining_pool.values())
    if total_remaining == 0:
        return picked
    shares: dict[str, int] = {}
    fractions: dict[str, float] = {}
    for cat, ids in remaining_pool.items():
        exact = slots * len(ids) / total_remaining
        shares[cat] = int(exact)
        fractions[cat] = exact - shares[cat]
    leftover = slots - sum(shares.values())
    order = sorted(remaining_pool.keys(), key=lambda c: (-fractions[c], rng.random()))
    for cat in order[:leftover]:
        shares[cat] += 1
    out = dict(picked)
    for cat, ids in remaining_pool.items():
        take = min(shares.get(cat, 0), len(ids))
        out[cat] = out[cat] + ids[:take]
    return out


def _trim_round_robin(
    picked: dict[str, list[str]], n: int, rng: random.Random
) -> dict[str, list[str]]:
    cats = list(picked.keys())
    rng.shuffle(cats)
    pools = {cat: list(ids) for cat, ids in picked.items()}
    out: dict[str, list[str]] = {cat: [] for cat in cats}
    count = 0
    while count < n:
        progressed = False
        for cat in cats:
            if count >= n:
                break
            if pools[cat]:
                out[cat].append(pools[cat].pop(0))
                count += 1
                progressed = True
        if not progressed:
            break
    return out


def load_or_create_sample(
    data_dir: Path,
    cards: list[Card],
    *,
    target: int = DEFAULT_TARGET,
    floor: int = DEFAULT_FLOOR,
    seed: int = DEFAULT_SEED,
) -> list[str]:
    """Load the frozen sample from ``data_dir/holdout_sample.json``, creating it on first use.

    Refuses to freeze a sample that cannot be stratified. §7 requires the holdout to be
    "stratified by category... with every category floored at ~10 items so per-category
    recall is measurable", but categories come from the ``classification`` table via a LEFT
    JOIN -- so before the classify stage runs, every card carries ``category_id = None``,
    every card lands in one bucket, and "stratified" silently becomes "proportional random".

    That is not a hypothetical ordering: PLAN.md's Wave 2 order is taxonomy draft (M6) ->
    label 150 reels -> classify (M7), so an empty ``classification`` table is the *expected*
    state when the owner first opens this page. The M7 checker measured the result on a
    1,300-card corpus: 9 of 14 categories fell below the floor of 10 and one got zero items,
    with no warning. And because the sample is frozen on that first page load, a single
    premature visit fixes the bad sample permanently.
    """
    path = data_dir / "holdout_sample.json"
    if path.exists():
        payload = json.loads(path.read_text())
        return [str(x) for x in payload["item_ids"]]

    categorised = sum(1 for c in cards if c.category_id)
    if cards and categorised == 0:
        raise UnstratifiableError(
            f"none of the {len(cards)} cards has a category yet, so a holdout sampled now "
            f"would not be stratified -- and it would be frozen to {path} as-is.\n"
            f"Run the classify stage first (python -m reelkb.classify), then reopen this page.\n"
            f"If {path} already exists from a premature visit, delete it before re-sampling."
        )

    item_ids = stratified_sample(cards, target=target, floor=floor, seed=seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"seed": seed, "item_ids": item_ids}, indent=2))
    return item_ids
