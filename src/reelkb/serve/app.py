"""The FastAPI app: landing page, category feeds, detail view, search, and curation actions.

Every route opens the database with ``connect_readonly`` (AC-8.2) and calls ``load_cards`` /
``load_curation`` fresh, on every request, from files it never caches -- so a hide or an edit
made a second ago is visible on the very next page load (AC-1.3). The one exception is the
``Searcher``: when the caller doesn't inject a real one (``searcher=None``), search falls back
to ``SubstringSearcher`` built fresh from the current cards, for the same reason.

Curation actions (hide, unhide, edit, change category) never touch the database. They call
straight into ``reelkb.contract.curation`` and then redirect back to a GET page
(POST-redirect-GET), so a phone browser's "reload" never resubmits a form.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from reelkb.contract import curation as curation_ops
from reelkb.contract.cards import Card, load_cards
from reelkb.contract.curation import EDITABLE_FIELDS, Curation
from reelkb.contract.db import connect_readonly
from reelkb.contract.search_api import Searcher, SearchFilters, SearchHit
from reelkb.testing.fake_search import SubstringSearcher

_HERE = Path(__file__).parent
TEMPLATES_DIR = _HERE / "templates"
STATIC_DIR = _HERE / "static"


def create_app(data_dir: Path | str, searcher: Searcher | None = None) -> FastAPI:
    """Build the app. ``searcher`` is a seam for tests and for the real search engine (M8);

    left as ``None`` it falls back to the fake ``SubstringSearcher`` so the app works
    standalone (e.g. ``--fake``) before the real engine exists.
    """
    data_dir = Path(data_dir)
    db_path = data_dir / "kb.db"

    app = FastAPI(title="Reel Knowledge Base")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    def _conn() -> sqlite3.Connection:
        return connect_readonly(db_path)

    def _curation() -> Curation:
        return curation_ops.load_curation(data_dir)

    def _categories(conn: sqlite3.Connection) -> list[dict[str, str]]:
        rows = conn.execute("SELECT category_id, name FROM categories ORDER BY name")
        return [{"category_id": r["category_id"], "name": r["name"]} for r in rows]

    def _searcher_for(cards: list[Card]) -> Searcher:
        return searcher if searcher is not None else SubstringSearcher(cards)

    # ----------------------------------------------------------------- landing (AC-1.1)

    @app.get("/")
    def landing(request: Request) -> object:
        conn = _conn()
        try:
            cur = _curation()
            cards = load_cards(conn, cur)
            cats = _categories(conn)
        finally:
            conn.close()
        counts = dict.fromkeys((c["category_id"] for c in cats), 0)
        for card in cards:
            if card.category_id in counts:
                counts[card.category_id] += 1
        rows = [{**c, "count": counts[c["category_id"]]} for c in cats]
        return templates.TemplateResponse(request, "landing.html", {"categories": rows})

    # ------------------------------------------------------------- category feed (D2)

    @app.get("/category/{category_id}")
    def category_feed(request: Request, category_id: str) -> object:
        conn = _conn()
        try:
            cur = _curation()
            name_row = conn.execute(
                "SELECT name FROM categories WHERE category_id = ?", (category_id,)
            ).fetchone()
            if name_row is None:
                raise HTTPException(404, f"no such category: {category_id}")
            cards = [c for c in load_cards(conn, cur) if c.category_id == category_id]
        finally:
            conn.close()
        cards.sort(key=lambda c: c.sent_at, reverse=True)
        return templates.TemplateResponse(
            request,
            "category.html",
            {"category_id": category_id, "category_name": name_row["name"], "cards": cards},
        )

    # ------------------------------------------------------------------ detail (AC-1.2)

    @app.get("/item/{item_id}")
    def detail(request: Request, item_id: str) -> object:
        conn = _conn()
        try:
            cur = _curation()
            cats = _categories(conn)
            all_cards = {c.item_id: c for c in load_cards(conn, cur, include_hidden=True)}
        finally:
            conn.close()
        card = all_cards.get(item_id)
        if card is None:
            raise HTTPException(404, f"no such item: {item_id}")
        return templates.TemplateResponse(
            request,
            "detail.html",
            {
                "card": card,
                "categories": cats,
                "is_hidden": item_id in cur.hidden,
            },
        )

    # -------------------------------------------------------------- hidden items (D15)

    @app.get("/hidden")
    def hidden_items(request: Request) -> object:
        conn = _conn()
        try:
            cur = _curation()
            all_cards = load_cards(conn, cur, include_hidden=True)
        finally:
            conn.close()
        cards = [c for c in all_cards if c.item_id in cur.hidden]
        cards.sort(key=lambda c: c.sent_at, reverse=True)
        return templates.TemplateResponse(request, "hidden.html", {"cards": cards})

    # -------------------------------------------------------------- curation actions

    def _redirect(url: str) -> RedirectResponse:
        return RedirectResponse(url, status_code=303)  # POST-redirect-GET

    @app.post("/item/{item_id}/hide")
    def hide_item(item_id: str) -> RedirectResponse:
        curation_ops.hide(data_dir, item_id)
        return _redirect(f"/item/{item_id}")

    @app.post("/item/{item_id}/unhide")
    def unhide_item(item_id: str) -> RedirectResponse:
        curation_ops.unhide(data_dir, item_id)
        return _redirect("/hidden")

    @app.post("/item/{item_id}/edit")
    def edit_item(
        item_id: str, title: Annotated[str, Form()], summary: Annotated[str, Form()]
    ) -> RedirectResponse:
        assert "title" in EDITABLE_FIELDS and "summary" in EDITABLE_FIELDS
        curation_ops.edit(data_dir, item_id, "title", title)
        curation_ops.edit(data_dir, item_id, "summary", summary)
        return _redirect(f"/item/{item_id}")

    @app.post("/item/{item_id}/category")
    def change_category(item_id: str, category_id: Annotated[str, Form()]) -> RedirectResponse:
        curation_ops.correct_category(data_dir, item_id, category_id)
        return _redirect(f"/item/{item_id}")

    # ------------------------------------------------------------------- search (§5)

    @app.get("/search")
    def search(
        request: Request,
        q: str = "",
        category_id: str = "",
        source_account: str = "",
        date_from: str = "",
        date_to: str = "",
        language: str = "",
        unreadable_only: bool = False,
    ) -> object:
        conn = _conn()
        try:
            cur = _curation()
            cards = load_cards(conn, cur)
            cats = _categories(conn)
        finally:
            conn.close()

        accounts = sorted({c.source_account for c in cards if c.source_account})
        languages = sorted({c.language for c in cards if c.language})

        filters = SearchFilters(
            category_id=category_id or None,
            source_account=source_account or None,
            date_from=date_from or None,
            date_to=date_to or None,
            language=language or None,
            unreadable_only=unreadable_only,
        )

        hits: list[SearchHit] = []
        if q.strip():
            engine = _searcher_for(cards)
            hits = engine.search(q, cur, filters, k=50)

        by_id = {c.item_id: c for c in cards}
        results = [(by_id[h.item_id], h) for h in hits if h.item_id in by_id]

        return templates.TemplateResponse(
            request,
            "search.html",
            {
                "q": q,
                "results": results,
                "categories": cats,
                "accounts": accounts,
                "languages": languages,
                "filters": {
                    "category_id": category_id,
                    "source_account": source_account,
                    "date_from": date_from,
                    "date_to": date_to,
                    "language": language,
                    "unreadable_only": unreadable_only,
                },
            },
        )

    return app
