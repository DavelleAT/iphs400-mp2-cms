"""The admin console. Every route on this router requires an active session:
add new admin routes here (or to a router built the same way) and they are
protected without further work."""
from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import homepage, settings
from app.auth import current_user, signed_in_user
from app.content import STATUS_LABELS
from app.routes.listing import (CONTENT_TYPES, REPORT, ContentType, ItemRow, newest_first,
                                status_filter, type_filter)
from app.users import is_director
from app.templating import templates

router = APIRouter(prefix="/admin", dependencies=[Depends(current_user)])


async def refused_page(request: Request, exc: StarletteHTTPException):
    """A 403 (e.g. an Analyst on a Director-only page) as a page with a way
    back, not FastAPI's JSON. Any other HTTP error is handled as FastAPI would."""
    if exc.status_code != 403:
        return await http_exception_handler(request, exc)
    return templates.TemplateResponse(
        request, "admin/forbidden.html",
        {"title": "Not allowed", "user": signed_in_user(request), "reason": exc.detail},
        status_code=403,
    )


# How many items the Dashboard's "Recently changed" shows.
RECENT_COUNT = 8


def waiting_for(request: Request, user: sqlite3.Row) -> list[ItemRow]:
    """The Dashboard's "Waiting for you", derived from what is stored (spec
    #25): for the Director, every draft Report, oldest update first, as only
    they can publish one; for an Analyst, their own drafts of both kinds,
    newest first, where they left off."""
    if is_director(user):
        return newest_first(request, user, (REPORT,), "draft")[::-1]
    return [row for row in newest_first(request, user, status="draft")
            if row.item["author_id"] == user["id"]]


@router.get("")
def admin_home(request: Request, user=Depends(current_user)):
    """The Dashboard: what needs the user's attention (spec #25, T24)."""
    counts: dict[ContentType, dict[str, int]] = {
        ctype: ctype.module.count_by_status() for ctype in CONTENT_TYPES}
    director = is_director(user)
    return templates.TemplateResponse(
        request, "admin/home.html",
        {"title": "Dashboard", "user": user, "director": director,
         # The office's day: the Console runs on the office's own machine.
         # (Stored times, and so the items' dates, are UTC, as on every page.)
         "today": date.today().isoformat(),
         "counts": counts,
         "waiting": waiting_for(request, user),
         "recent": newest_first(request, user)[:RECENT_COUNT],
         # When the Homepage settings were last saved; None if they are
         # still the sample a new site starts with, so never saved.
         "homepage_saved": (homepage.last_saved()
                            if director and homepage.get() != homepage.SAMPLE else None),
         "status_labels": STATUS_LABELS},
    )


@router.get("/content")
def content_list(request: Request, user=Depends(current_user),
                 content_type: str = Depends(type_filter),
                 status: str = Depends(status_filter)):
    """Data Bites and Reports together, most recently updated first,
    optionally narrowed to one type and/or one status."""
    rows = newest_first(request, user, [ctype for ctype in CONTENT_TYPES
                                        if content_type in ("", ctype.key)], status or None)
    return templates.TemplateResponse(
        request, "admin/content.html",
        {"title": "All content", "user": user,
         "rows": rows, "content_types": CONTENT_TYPES,
         "status_labels": STATUS_LABELS,
         "chosen": {"type": content_type, "status": status}},
    )


@router.get("/editor.js")
def editor_script():
    """The Editor's script (app.editor), for the edit and create pages only."""
    return FileResponse(settings.STATIC / "editor.js", media_type="text/javascript")
