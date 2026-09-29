"""Data Bites in the admin console. Any signed-in user may do everything here,
chart images included, except delete, which is Director only."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import chart_images, data_bites
from app.flash import SITE_NOTE, confirm
from app.auth import current_user, require_csrf, require_director
from app.content import STATUS_LABELS, ContentError
from app.rendering import ImageSrc, images_without_description, render_markdown
from app.templating import templates

router = APIRouter(prefix="/admin/data-bites", dependencies=[Depends(current_user)])
_MAX_IMAGE_MB = chart_images.MAX_BYTES // chart_images.MIB


def _list_page(request: Request, user: sqlite3.Row, *, error: str | None = None,
               form: dict | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/data_bites.html",
        {"title": "Data Bites", "home_path": "/admin", "user": user,
         "bites": data_bites.list_all(), "status_labels": STATUS_LABELS,
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
    except ContentError as exc:
        return _list_page(request, user, error=str(exc), status_code=400,
                          form={"title": title, "slug": slug, "body": body})
    confirm(request, "Data Bite created as a Draft.")
    return RedirectResponse("/admin/data-bites", status_code=303)


def _image_src(bite_id: int) -> ImageSrc:
    """The Data Bite's `image:<name>` references, resolved to its images here."""
    names = data_bites.images(bite_id)
    return lambda name: f"/admin/data-bites/{bite_id}/images/{name}" if name in names else None


def _edit_page(request: Request, user: sqlite3.Row, bite: sqlite3.Row, *,
               error: str | None = None, form: dict | None = None,
               status_code: int = 200):
    form = form or bite
    return templates.TemplateResponse(
        request, "admin/data_bite_edit.html",
        {"title": "Edit Data Bite", "home_path": "/admin", "user": user,
         "bite": bite, "status_labels": STATUS_LABELS,
         "error": error, "form": form,
         "images": list(data_bites.images(bite["id"])),
         "image_src": _image_src(bite["id"]),
         "preview_path": f"/admin/data-bites/{bite['id']}/preview",
         "undescribed_images": images_without_description(form["body"]),
         "max_image_mb": _MAX_IMAGE_MB,
         "max_images": chart_images.MAX_PER_ITEM},
        status_code=status_code,
    )


def _get_or_404(bite_id: int) -> sqlite3.Row:
    bite = data_bites.get(bite_id)
    if bite is None:
        raise HTTPException(status_code=404)
    return bite


@router.get("/{bite_id}")
def edit_bite_form(request: Request, bite_id: int, user=Depends(current_user)):
    return _edit_page(request, user, _get_or_404(bite_id))


@router.post("/{bite_id}", dependencies=[Depends(require_csrf)])
def edit_bite(request: Request, bite_id: int, user=Depends(current_user),
              title: str = Form(""), slug: str = Form(""), body: str = Form("")):
    bite = _get_or_404(bite_id)
    try:
        data_bites.update(bite_id, title, slug, body)
    except ContentError as exc:
        return _edit_page(request, user, bite, error=str(exc), status_code=400,
                          form={"title": title, "slug": slug, "body": body})
    confirm(request, "Data Bite saved.")
    return RedirectResponse(f"/admin/data-bites/{bite_id}", status_code=303)


@router.post("/{bite_id}/preview", dependencies=[Depends(require_csrf)])
def preview(bite_id: int, body: str = Form("")):
    """As /admin/preview, with the Data Bite's chart images shown. Saves nothing."""
    _get_or_404(bite_id)
    return HTMLResponse(render_markdown(body, _image_src(bite_id)))


@router.get("/{bite_id}/images/{name}")
def serve_image(bite_id: int, name: str):
    path = data_bites.images(bite_id).get(name)
    if path is None:
        raise HTTPException(status_code=404)
    return chart_images.response(path)


@router.post("/{bite_id}/images", dependencies=[Depends(require_csrf)])
def upload_image(request: Request, bite_id: int, user=Depends(current_user),
                 file: UploadFile | None = File(None)):
    bite = _get_or_404(bite_id)
    try:
        if not data_bites.add_image(bite_id, chart_images.read(file)):
            raise HTTPException(status_code=404)
    except ContentError as exc:
        return _edit_page(request, user, bite, error=str(exc), status_code=400)
    confirm(request, "Chart image uploaded.")
    return RedirectResponse(f"/admin/data-bites/{bite_id}", status_code=303)


@router.post("/{bite_id}/images/{name}/delete", dependencies=[Depends(require_csrf)])
def delete_image(request: Request, bite_id: int, name: str):
    if not data_bites.remove_image(bite_id, name):
        raise HTTPException(status_code=404)
    confirm(request, "Chart image deleted.")
    return RedirectResponse(f"/admin/data-bites/{bite_id}", status_code=303)


def _set_status(request: Request, bite_id: int, status: str, message: str):
    if not data_bites.set_status(bite_id, status):
        raise HTTPException(status_code=404)
    confirm(request, message + SITE_NOTE)
    return RedirectResponse("/admin/data-bites", status_code=303)


@router.post("/{bite_id}/publish", dependencies=[Depends(require_csrf)])
def publish(request: Request, bite_id: int):
    return _set_status(request, bite_id, "published", "Data Bite published.")


@router.post("/{bite_id}/unpublish", dependencies=[Depends(require_csrf)])
def unpublish(request: Request, bite_id: int):
    return _set_status(request, bite_id, "draft", "Data Bite moved back to Draft.")


@router.post("/{bite_id}/delete",
             dependencies=[Depends(require_director), Depends(require_csrf)])
def delete(request: Request, bite_id: int):
    if not data_bites.delete(bite_id):
        raise HTTPException(status_code=404)
    confirm(request, "Data Bite deleted.")
    return RedirectResponse("/admin/data-bites", status_code=303)
