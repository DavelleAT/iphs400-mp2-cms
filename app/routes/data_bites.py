"""Data Bites in the admin console. Any signed-in user may do everything here,
chart images and Site previews included, except delete, which is Director
only."""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse

from app import chart_images, data_bites, editor, public_site, site_links
from app.flash import SITE_NOTE, confirm
from app.auth import current_user, require_csrf, require_director
from app.content import STATUS_LABELS, ContentError
from app.rendering import images_without_description
from app.routes import editing
from app.routes.site_preview import site_file
from app.templating import templates

router = APIRouter(prefix="/admin/data-bites", dependencies=[Depends(current_user)])
_MAX_IMAGE_MB = chart_images.MAX_BYTES // chart_images.MIB


def _site_preview(request: Request, form: Mapping[str, str], bite: sqlite3.Row | None) -> str:
    """The Site preview of `form`'s edits to `bite` (None for a new Data
    Bite), as HTML, served from the preview's copy of the site."""
    at = (request.app.url_path_for("bite_preview_site", bite_id=bite["id"], path="")
          if bite is not None else request.app.url_path_for("new_bite_preview_site", path=""))
    return public_site.data_bite_preview(form, bite).render_preview(str(at))


def _images(request: Request, bite_id: int) -> editor.ImageLinks:
    return editing.image_links(request, "serve_image", bite_id=bite_id)


def _list_page(request: Request, user: sqlite3.Row, *, error: str | None = None,
               form: dict | None = None, status_code: int = 200):
    form = form or {"title": "", "slug": "", "body": ""}
    return templates.TemplateResponse(
        request, "admin/data_bites.html",
        {"title": "Data Bites", "home_path": "/admin", "user": user,
         "bites": data_bites.list_all(), "status_labels": STATUS_LABELS,
         "error": error, "form": form,
         "editor_html": editor.editor_html(form["body"], "", None),
         **editing.site_links_for(editor.full_body(form["body"], "")),
         "site_preview": _site_preview(
             request, {**form, "body": editor.full_body(form["body"], "")}, None),
         "preview_path": request.app.url_path_for("preview_new_bite")},
        status_code=status_code,
    )


@router.get("")
def list_bites(request: Request, user=Depends(current_user)):
    return _list_page(request, user)


@router.post("", dependencies=[Depends(require_csrf)])
def create_bite(request: Request, user=Depends(current_user), title: str = Form(""),
                slug: str = Form(""), posted: editor.Posted = Depends(editing.posted)):
    try:
        data_bites.create(title, slug, editor.saved_body(posted, None, None), user["id"])
    except ContentError as exc:
        return _list_page(request, user, error=str(exc), status_code=400,
                          form=editor.form_after(posted, title, slug, "", None, None))
    confirm(request, "Data Bite created as a Draft.")
    return RedirectResponse("/admin/data-bites", status_code=303)


# A new Data Bite's Site preview. Before the /{bite_id} routes, which would
# otherwise take "preview" for an id.

@router.post("/preview", dependencies=[Depends(require_csrf)])
def preview_new_bite(request: Request, title: str = Form(""),
                     posted: editor.Posted = Depends(editing.posted)):
    """The create form's Site preview, for its frame and "Preview on site".
    Saves nothing."""
    shown = editing.previewed(posted, None, None)
    return HTMLResponse(_site_preview(request, {"title": title, "body": shown}, None))


@router.get("/preview/{path:path}")
def new_bite_preview_site(path: str):
    """The create form's Site preview's copy of the site: only its stylesheet,
    as a new Data Bite has no chart images (app.routes.site_preview)."""
    return site_file(path, images={})


def _edit_page(request: Request, user: sqlite3.Row, bite: sqlite3.Row, *,
               error: str | None = None, form: dict | None = None,
               status_code: int = 200):
    form = form or editor.form_for(bite)
    # The body with its locked blocks, which only the server sees.
    body = editor.full_body(form["body"], bite["body"])
    return templates.TemplateResponse(
        request, "admin/data_bite_edit.html",
        {"title": "Edit Data Bite", "home_path": "/admin", "user": user,
         "bite": bite, "status_labels": STATUS_LABELS,
         "error": error, "form": form,
         "editor_html": editor.editor_html(form["body"], bite["body"],
                                           _images(request, bite["id"]).src),
         "images": list(data_bites.images(bite["id"])),
         **editing.site_links_for(body),
         "site_preview": _site_preview(request, {**form, "body": body}, bite),
         "preview_path": request.app.url_path_for("preview_bite", bite_id=bite["id"]),
         "undescribed_images": images_without_description(body),
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
              title: str = Form(""), slug: str = Form(""),
              posted: editor.Posted = Depends(editing.posted), item_base: str = Form("")):
    bite = _get_or_404(bite_id)
    image_name = _images(request, bite_id).name
    try:
        data_bites.update(bite_id, title, slug,
                          editor.saved_edit(posted, bite, item_base, image_name),
                          base=item_base or None)
    except ContentError as exc:
        # Shown over the item as stored now, which a stale form missed.
        current = _get_or_404(bite_id)
        return _edit_page(request, user, current, error=str(exc),
                          status_code=editing.refused_status(exc),
                          form=editor.form_after(posted, title, slug, item_base,
                                                 current["body"], image_name))
    confirm(request, "Data Bite saved.")
    return RedirectResponse(f"/admin/data-bites/{bite_id}", status_code=303)


@router.post("/{bite_id}/preview", dependencies=[Depends(require_csrf)])
def preview_bite(request: Request, bite_id: int, title: str = Form(""),
                 posted: editor.Posted = Depends(editing.posted)):
    """The edit form's Site preview, of its unsaved title and body, for its
    frame and "Preview on site". Saves nothing."""
    bite = _get_or_404(bite_id)
    shown = editing.previewed(posted, bite["body"],
                      _images(request, bite_id).name)
    return HTMLResponse(_site_preview(request, {"title": title, "body": shown}, bite))


@router.get("/{bite_id}/preview/{path:path}")
def bite_preview_site(bite_id: int, path: str):
    """The Site preview's copy of the site: its stylesheet and the Data
    Bite's chart images, draft or not (app.routes.site_preview)."""
    return site_file(path, images=public_site.data_bite_files(_get_or_404(bite_id)))


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


@router.get("/{bite_id}/delete", dependencies=[Depends(require_director)])
def confirm_delete_bite(request: Request, bite_id: int, user=Depends(current_user)):
    """Before a delete: which items link to this one, whose links will be
    their text once it is gone. The delete isn't blocked."""
    item = _get_or_404(bite_id)
    return templates.TemplateResponse(
        request, "admin/confirm_delete.html",
        {"title": "Delete Data Bite", "home_path": "/admin", "user": user, "noun": "Data Bite",
         "item": item, "action": f"/admin/data-bites/{bite_id}/delete",
         "back": request.app.url_path_for("list_bites"),
         "linked_from": site_links.linked_from(site_links.reference("data-bite", item["ref"]))})


@router.post("/{bite_id}/delete",
             dependencies=[Depends(require_director), Depends(require_csrf)])
def delete(request: Request, bite_id: int):
    if not data_bites.delete(bite_id):
        raise HTTPException(status_code=404)
    confirm(request, "Data Bite deleted.")
    return RedirectResponse("/admin/data-bites", status_code=303)
