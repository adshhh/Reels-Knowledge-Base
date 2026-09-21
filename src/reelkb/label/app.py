"""The labelling app: ``create_app(data_dir, searchers=None)`` builds the FastAPI application.

Two jobs (PLAN.md §7):

1. **Holdout labelling** — walk a frozen, stratified 150-item sample one card at a time and
   record the owner's category judgement to ``eval/holdout_v1.jsonl``. The classifier's own
   category for the item is never sent to the template (see ``_categories``/``holdout_item``:
   the button list comes from the taxonomy table, not from the item's ``classification`` row,
   and nothing in the response ever reveals which one the model picked).
2. **Query judging** — the owner types a query, the page pools and shuffles the top results
   from every configured ``Searcher``, and the owner grades each 2/1/0, saved to
   ``eval/queries_v1.jsonl``.

The database is opened ``connect_readonly`` only (this page never writes to ``kb.db``); its
own state (the frozen sample, the salt, the hid lookup) lives under ``data_dir``, and the two
fixture files live in the sibling ``eval/`` directory, matching the project's top-level layout
(``data/`` local-only, ``eval/`` committed with hashed ids per docs/CONTRACT.md).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from reelkb.contract.cards import Card, load_cards
from reelkb.contract.curation import Curation, load_curation
from reelkb.contract.db import connect_readonly
from reelkb.contract.search_api import Searcher
from reelkb.eval.ids import SaltLostError, hash_id, load_lookup, load_salt, update_lookup
from reelkb.label import holdout_store, queries_store
from reelkb.label.pooling import pool_candidates
from reelkb.label.sampling import UnstratifiableError, load_or_create_sample
from reelkb.testing.fake_search import SubstringSearcher

_HERE = Path(__file__).parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"


def create_app(
    data_dir: Path | str,
    searchers: dict[str, Searcher] | None = None,
    *,
    eval_dir: Path | str | None = None,
) -> FastAPI:
    data_dir = Path(data_dir)
    eval_dir = Path(eval_dir) if eval_dir is not None else data_dir.parent / "eval"

    app = FastAPI(title="Reel KB — labelling")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    templates = Jinja2Templates(directory=TEMPLATES_DIR)

    def _connect() -> sqlite3.Connection:
        return connect_readonly(data_dir / "kb.db")

    def _cards_and_curation() -> tuple[list[Card], Curation]:
        conn = _connect()
        try:
            curation = load_curation(data_dir)
            # include_hidden=True: a sampled item hidden later must stay labellable, since
            # the sample was already frozen and the fixture is about category truth, not
            # about what the feed currently shows.
            return load_cards(conn, curation, include_hidden=True), curation
        finally:
            conn.close()

    def _categories() -> list[dict[str, str]]:
        """The taxonomy's buttons, in a fixed order that never depends on any item's own
        classification, so no item's page can leak which category the model picked."""
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT category_id, name FROM categories ORDER BY category_id"
            ).fetchall()
            return [{"category_id": r["category_id"], "name": r["name"]} for r in rows]
        finally:
            conn.close()

    def _searchers(cards: list[Card]) -> dict[str, Searcher]:
        if searchers is not None:
            return searchers
        # Until the real engines exist, the fake/dev default is a plain substring search
        # (§ M7 build brief), so the query-judging page is usable before M8 lands.
        return {"substring": SubstringSearcher(cards)}

    # ---------------------------------------------------------------- holdout labelling

    @app.exception_handler(UnstratifiableError)
    @app.exception_handler(SaltLostError)
    async def _blocked(_request: Request, exc: Exception) -> PlainTextResponse:
        """Show the remediation text instead of a blank 500.

        Both of these fire on the page the owner opens FIRST, and both carry instructions he
        needs (run classify before sampling; restore the salt from a backup). A 500 hides
        exactly the sentence that tells him what to do. (Code review, finding 5.)
        """
        return PlainTextResponse(f"Cannot start labelling yet.\n\n{exc}\n", status_code=409)

    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse("/holdout")

    @app.get("/holdout")
    def holdout_root() -> RedirectResponse:
        cards, _ = _cards_and_curation()
        sample = load_or_create_sample(data_dir, cards)
        if not sample:
            raise HTTPException(404, "the corpus has no fused items to sample from")
        salt = load_salt(data_dir)
        answers = holdout_store.load_answers(eval_dir)
        next_n = len(sample)  # once everything is answered, land on the last card to review
        for i, item_id in enumerate(sample, start=1):
            if hash_id(item_id, salt) not in answers:
                next_n = i
                break
        return RedirectResponse(f"/holdout/{next_n}")

    @app.get("/holdout/{n}", response_class=HTMLResponse)
    def holdout_item(request: Request, n: int) -> HTMLResponse:
        cards, _ = _cards_and_curation()
        sample = load_or_create_sample(data_dir, cards)
        if n < 1 or n > len(sample):
            raise HTTPException(404, "no such position in the holdout sample")
        by_id = {c.item_id: c for c in cards}
        item_id = sample[n - 1]
        card = by_id.get(item_id)
        if card is None:
            raise HTTPException(404, f"sampled item {item_id!r} is no longer a card")

        salt = load_salt(data_dir)
        hid = hash_id(item_id, salt)
        answers = holdout_store.load_answers(eval_dir)
        answered_count = sum(1 for i in sample if hash_id(i, salt) in answers)

        return templates.TemplateResponse(
            request,
            "holdout.html",
            {
                "n": n,
                "total": len(sample),
                "answered": answered_count,
                "card": card,
                "categories": _categories(),
                "your_answer": answers.get(hid),
                "has_prev": n > 1,
                "has_next": n < len(sample),
            },
        )

    @app.post("/holdout/{n}")
    def holdout_save(n: int, category_id: Annotated[str, Form()]) -> RedirectResponse:
        cards, _ = _cards_and_curation()
        sample = load_or_create_sample(data_dir, cards)
        if n < 1 or n > len(sample):
            raise HTTPException(404, "no such position in the holdout sample")
        valid_ids = {c["category_id"] for c in _categories()}
        if category_id not in valid_ids:
            raise HTTPException(400, f"{category_id!r} is not a known category")
        item_id = sample[n - 1]
        hid = update_lookup(data_dir, item_id)
        holdout_store.save_answer(eval_dir, hid, category_id)
        next_n = n + 1 if n < len(sample) else n
        return RedirectResponse(f"/holdout/{next_n}", status_code=303)

    # ------------------------------------------------------------------- query judging

    @app.get("/queries", response_class=HTMLResponse)
    def queries_index(request: Request) -> HTMLResponse:
        records = list(queries_store.load_queries(eval_dir).values())
        return templates.TemplateResponse(request, "queries.html", {"records": records})

    @app.post("/queries")
    def queries_create(query: Annotated[str, Form()]) -> RedirectResponse:
        query = query.strip()
        if not query:
            raise HTTPException(400, "query text cannot be empty")
        records = queries_store.load_queries(eval_dir)
        qid = queries_store.next_qid(records)
        queries_store.save_query(eval_dir, queries_store.QueryRecord(qid=qid, query=query))
        return RedirectResponse(f"/queries/{qid}", status_code=303)

    @app.get("/queries/{qid}", response_class=HTMLResponse)
    def queries_judge(request: Request, qid: str) -> HTMLResponse:
        records = queries_store.load_queries(eval_dir)
        record = records.get(qid)
        if record is None:
            raise HTTPException(404, f"no such query {qid!r}")

        cards, curation = _cards_and_curation()
        by_id = {c.item_id: c for c in cards}
        pooled_ids = pool_candidates(record.query, _searchers(cards), curation)

        # Keep any already-judged item visible even if it fell out of a re-run pool (e.g. the
        # query text was tweaked), so editing an old judgement never silently drops it.
        lookup = load_lookup(data_dir)
        judged_ids = [lookup[hid] for hid in record.judgements if hid in lookup]
        ordered_ids = list(dict.fromkeys([*pooled_ids, *judged_ids]))

        candidates = []
        for item_id in ordered_ids:
            card = by_id.get(item_id)
            if card is None:
                continue
            hid = update_lookup(data_dir, item_id)
            candidates.append({"card": card, "hid": hid, "judgement": record.judgements.get(hid)})

        return templates.TemplateResponse(
            request,
            "queries_judge.html",
            {"record": record, "candidates": candidates},
        )

    @app.post("/queries/{qid}")
    async def queries_save(request: Request, qid: str) -> RedirectResponse:
        records = queries_store.load_queries(eval_dir)
        record = records.get(qid)
        if record is None:
            raise HTTPException(404, f"no such query {qid!r}")

        form = await request.form()
        # Merge onto what is already saved, rather than replacing it. A submit only carries
        # the candidates that were on screen, so replacing wholesale means any grade not
        # re-sent is deleted -- a partial submit, a changed candidate pool, or a hid the
        # local lookup can no longer resolve would silently erase judging work the owner
        # cannot see is gone. (M7 checker, finding 6.) Re-grading a hid still overwrites it,
        # which is the only case where losing the old value is what the owner asked for.
        judgements: dict[str, int] = dict(record.judgements)
        for key, value in form.multi_items():
            if isinstance(key, str) and key.startswith("judgement_"):
                hid = key[len("judgement_") :]
                judgements[hid] = int(str(value))
        record.judgements = judgements
        record.canary = form.get("canary") == "on"
        queries_store.save_query(eval_dir, record)
        return RedirectResponse("/queries", status_code=303)

    return app
