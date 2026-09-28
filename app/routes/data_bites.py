"""Data Bites in the admin console. Any signed-in user may do everything here
except delete, which is Director only."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import data_bites
from app.auth import current_user, require_csrf, require_director
from app.templating import templates

router = APIRouter(prefix="/admin/data-bites", dependencies=[Depends(current_user)])


def _list_page(request: Request, user: sqlite3.Row, *, error: str | None = None,
               form: dict | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/data_bites.html",
        {"title": "Data Bites", "home_path": "/admin", "user": user,
         "bites": data_bites.list_all(), "status_labels": data_bites.STATUS_LABELS,
         "error": error, "form": form or {}},
        status_code=status_code,
    )


@router.get("")
def list_bites(request: Request, user=Depends(current_user)):
    return _list_page(request, user)


@router.post("", dependencies=[Depends(require_csrf)])
def create_bite(request: Request, user=Depends(current_user), title: str = Form(""),
                slug: str = Form(""), body: str = Form("")):
    try:
        data_bites.create(title, slug, body, user["id"])
    except data_bites.DataBiteError as exc:
        return _list_page(request, user, error=str(exc), status_code=400,
                          form={"title": title, "slug": slug, "body": body})
    return RedirectResponse("/admin/data-bites", status_code=303)


def _edit_page(request: Request, user: sqlite3.Row, bite: sqlite3.Row, *,
               error: str | None = None, form: dict | None = None,
               status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/data_bite_edit.html",
        {"title": "Edit Data Bite", "home_path": "/admin", "user": user,
         "bite": bite, "status_labels": data_bites.STATUS_LABELS,
         "error": error, "form": form or bite},
        status_code=status_code,
    )


def _get_or_404(bite_id: int) -> sqlite3.Row:
    bite = data_bites.get(bite_id)
    if bite is None:
        raise HTTPException(status_code=404)
    return bite


@router.get("/{bite_id}")
def edit_form(request: Request, bite_id: int, user=Depends(current_user)):
    return _edit_page(request, user, _get_or_404(bite_id))


@router.post("/{bite_id}", dependencies=[Depends(require_csrf)])
def edit_bite(request: Request, bite_id: int, user=Depends(current_user),
              title: str = Form(""), slug: str = Form(""), body: str = Form("")):
    bite = _get_or_404(bite_id)
    try:
        data_bites.update(bite_id, title, slug, body)
    except data_bites.DataBiteError as exc:
        return _edit_page(request, user, bite, error=str(exc), status_code=400,
                          form={"title": title, "slug": slug, "body": body})
    return RedirectResponse(f"/admin/data-bites/{bite_id}", status_code=303)


def _set_status(bite_id: int, status: str):
    if not data_bites.set_status(bite_id, status):
        raise HTTPException(status_code=404)
    return RedirectResponse("/admin/data-bites", status_code=303)


@router.post("/{bite_id}/publish", dependencies=[Depends(require_csrf)])
def publish(bite_id: int):
    return _set_status(bite_id, "published")


@router.post("/{bite_id}/unpublish", dependencies=[Depends(require_csrf)])
def unpublish(bite_id: int):
    return _set_status(bite_id, "draft")


@router.post("/{bite_id}/delete",
             dependencies=[Depends(require_director), Depends(require_csrf)])
def delete(bite_id: int):
    if not data_bites.delete(bite_id):
        raise HTTPException(status_code=404)
    return RedirectResponse("/admin/data-bites", status_code=303)
