"""The admin console. Every route on this router requires an active session:
add new admin routes here (or to a router built the same way) and they are
protected without further work."""
from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import data_bites, reports, settings
from app.auth import current_user, signed_in_user
from app.content import STATUS_LABELS
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


@dataclass(frozen=True)
class ContentType:
    key: str        # e.g. "data-bite", as used in ids and query strings
    noun: str       # e.g. "Data Bite"
    plural: str     # e.g. "Data Bites"
    module: ModuleType
    list_path: str  # the type's own admin page, e.g. "/admin/data-bites"


CONTENT_TYPES = (
    ContentType("data-bite", "Data Bite", "Data Bites", data_bites, "/admin/data-bites"),
    ContentType("report", "Report", "Reports", reports, "/admin/reports"),
)
# The content list's filters; "" (the form's "All") means no filter.
TypeFilter = Literal["", *(ctype.key for ctype in CONTENT_TYPES)]
StatusFilter = Literal["", *STATUS_LABELS]


@router.get("")
def admin_home(request: Request, user=Depends(current_user)):
    counts = {ctype.key: ctype.module.count_by_status() for ctype in CONTENT_TYPES}
    return templates.TemplateResponse(
        request, "admin/home.html",
        {"title": "Dashboard", "user": user,
         "content_types": CONTENT_TYPES, "counts": counts,
         "status_labels": STATUS_LABELS},
    )


@router.get("/content")
def content_list(request: Request, user=Depends(current_user),
                 content_type: TypeFilter = Query("", alias="type"),
                 status: StatusFilter = ""):
    """Data Bites and Reports together, most recently updated first,
    optionally narrowed to one type and/or one status."""
    items = [(ctype, item) for ctype in CONTENT_TYPES if content_type in ("", ctype.key)
             for item in ctype.module.list_all(status or None)]
    items.sort(key=lambda pair: pair[1]["updated_at"], reverse=True)
    return templates.TemplateResponse(
        request, "admin/content.html",
        {"title": "All content", "user": user,
         "items": items, "content_types": CONTENT_TYPES,
         "status_labels": STATUS_LABELS,
         "chosen": {"type": content_type, "status": status}},
    )


@router.get("/editor.js")
def editor_script():
    """The Editor's script (app.editor), for the edit and create pages only."""
    return FileResponse(settings.STATIC / "editor.js", media_type="text/javascript")
