"""Reports in the admin console. Any signed-in user may list Reports, create a
draft, edit a draft (its body, its attached file, or its chart images, and
the Site preview of its edits), and download a Report's file or view its
images or its saved Site preview. Editing a published Report, its file, or its
images, and publishing, unpublishing, or deleting any Report, is Director
only."""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app import chart_images, public_site, reports, uploads
from app.flash import SITE_NOTE, confirm
from app.auth import current_user, require_csrf, require_director
from app.content import STATUS_LABELS, ContentError
from app.rendering import images_without_description
from app.routes.public import preview_site_file
from app.templating import templates

router = APIRouter(prefix="/admin/reports", dependencies=[Depends(current_user)])
_MAX_FILE_MB = uploads.MAX_BYTES // uploads.MIB
_MAX_IMAGE_MB = chart_images.MAX_BYTES // chart_images.MIB


def _site_preview(request: Request, form: Mapping[str, str], report: sqlite3.Row | None) -> str:
    """The Site preview of `form`'s edits to `report` (None for a new
    Report), as HTML, served from the preview's copy of the site."""
    at = (request.app.url_path_for("report_preview_site", report_id=report["id"], path="")
          if report is not None else request.app.url_path_for("new_report_preview_site", path=""))
    return public_site.report_preview(form, report).render_preview(str(at))


def _list_page(request: Request, user: sqlite3.Row, *, error: str | None = None,
               form: dict | None = None, status_code: int = 200):
    form = form or {"title": "", "slug": "", "body": ""}
    return templates.TemplateResponse(
        request, "admin/reports.html",
        {"title": "Reports", "home_path": "/admin", "user": user,
         "reports": reports.list_all(), "status_labels": STATUS_LABELS,
         "error": error, "form": form, "max_file_mb": _MAX_FILE_MB,
         "site_preview": _site_preview(request, form, None),
         "preview_path": request.app.url_path_for("preview_new_report")},
        status_code=status_code,
    )


@router.get("")
def list_reports(request: Request, user=Depends(current_user)):
    return _list_page(request, user)


@router.post("", dependencies=[Depends(require_csrf)])
def create_report(request: Request, user=Depends(current_user), title: str = Form(""),
                  slug: str = Form(""), body: str = Form(""),
                  file: UploadFile | None = File(None)):
    try:
        pdf = uploads.read_pdf(file)
        reports.create(title, slug, body, user["id"], pdf=pdf)
    except ContentError as exc:
        return _list_page(request, user, error=str(exc), status_code=400,
                          form={"title": title, "slug": slug, "body": body})
    confirm(request, "Report created as a Draft, with its attached file." if pdf
            else "Report created as a Draft.")
    return RedirectResponse("/admin/reports", status_code=303)


# A new Report's Site preview. Before the /{report_id} routes, which would
# otherwise take "preview" for an id.

@router.post("/preview", dependencies=[Depends(require_csrf)])
def preview_new_report(request: Request, title: str = Form(""), body: str = Form("")):
    """The create form's Site preview, for its frame and "Preview on site".
    Saves nothing; a file chosen in the form is not read."""
    return HTMLResponse(_site_preview(request, {"title": title, "body": body}, None))


@router.get("/preview/{path:path}")
def new_report_preview_site(path: str):
    return preview_site_file(path, {})


def _edit_page(request: Request, user: sqlite3.Row, report: sqlite3.Row, *,
               error: str | None = None, form: dict | None = None,
               status_code: int = 200):
    form = form or report
    return templates.TemplateResponse(
        request, "admin/report_edit.html",
        {"title": "Edit Report", "home_path": "/admin", "user": user,
         "report": report, "can_edit": reports.can_edit(report, user),
         "status_labels": STATUS_LABELS, "error": error, "form": form,
         "max_file_mb": _MAX_FILE_MB,
         "images": list(reports.images(report["id"])),
         "site_preview": _site_preview(request, form, report),
         "preview_path": request.app.url_path_for("preview_report", report_id=report["id"]),
         "undescribed_images": images_without_description(form["body"]),
         "max_image_mb": _MAX_IMAGE_MB,
         "max_images": chart_images.MAX_PER_ITEM},
        status_code=status_code,
    )


def _get_or_404(report_id: int) -> sqlite3.Row:
    report = reports.get(report_id)
    if report is None:
        raise HTTPException(status_code=404)
    return report


def _editable_or_403(report_id: int, user: sqlite3.Row) -> sqlite3.Row:
    """The Report, if `user` may change it. Checked before anything sent is
    looked at, so a locked Report is 403 whatever was sent. The write checks
    again, in its UPDATE, in case the Report is published in between; that
    raises ReportLocked, which the routes also turn into a 403."""
    report = _get_or_404(report_id)
    if not reports.can_edit(report, user):
        raise HTTPException(status_code=403, detail=reports.LOCKED)
    return report


@router.get("/{report_id}")
def edit_report_form(request: Request, report_id: int, user=Depends(current_user)):
    return _edit_page(request, user, _get_or_404(report_id))


@router.post("/{report_id}", dependencies=[Depends(require_csrf)])
def edit_report(request: Request, report_id: int, user=Depends(current_user),
                title: str = Form(""), slug: str = Form(""), body: str = Form(""),
                file: UploadFile | None = File(None)):
    report = _editable_or_403(report_id, user)
    try:
        pdf = uploads.read_pdf(file)
        if not reports.update(report_id, title, slug, body, user=user, pdf=pdf):
            raise HTTPException(status_code=404)
    except reports.ReportLocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    except ContentError as exc:
        return _edit_page(request, user, report, error=str(exc), status_code=400,
                          form={"title": title, "slug": slug, "body": body})
    confirm(request, "Report saved, with its new attached file." if pdf
            else "Report saved.")
    return RedirectResponse(f"/admin/reports/{report_id}", status_code=303)


@router.get("/{report_id}/file")
def download_file(report_id: int):
    report = _get_or_404(report_id)
    path = reports.file_path(report_id)
    if report["file_name"] is None or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="application/pdf",
                        filename=report["file_name"],
                        headers={"X-Content-Type-Options": "nosniff"})


@router.post("/{report_id}/file/delete", dependencies=[Depends(require_csrf)])
def remove_file(request: Request, report_id: int, user=Depends(current_user)):
    try:
        if not reports.remove_file(report_id, user=user):
            raise HTTPException(status_code=404)
    except reports.ReportLocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    confirm(request, "Attached file removed.")
    return RedirectResponse(f"/admin/reports/{report_id}", status_code=303)


@router.post("/{report_id}/preview", dependencies=[Depends(require_csrf)])
def preview_report(request: Request, report_id: int, user=Depends(current_user),
                   title: str = Form(""), body: str = Form("")):
    """The edit form's Site preview, of its unsaved title and body, for its
    frame and "Preview on site". Only for a user who may make those edits
    (the lockdown). Saves nothing; a file chosen in the form is not read."""
    report = _editable_or_403(report_id, user)
    return HTMLResponse(_site_preview(request, {"title": title, "body": body}, report))


@router.get("/{report_id}/preview/{path:path}")
def report_preview_site(report_id: int, path: str):
    """The Site preview's copy of the site: its stylesheet and the Report's
    chart images and file, draft or not, which any signed-in user may already
    download here (app.routes.public.preview_site_file)."""
    return preview_site_file(path, public_site.report_files(_get_or_404(report_id)))


@router.get("/{report_id}/images/{name}")
def serve_image(report_id: int, name: str):
    path = reports.images(report_id).get(name)
    if path is None:
        raise HTTPException(status_code=404)
    return chart_images.response(path)


@router.post("/{report_id}/images", dependencies=[Depends(require_csrf)])
def upload_image(request: Request, report_id: int, user=Depends(current_user),
                 file: UploadFile | None = File(None)):
    report = _editable_or_403(report_id, user)
    try:
        if not reports.add_image(report_id, chart_images.read(file), user=user):
            raise HTTPException(status_code=404)
    except reports.ReportLocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    except ContentError as exc:
        return _edit_page(request, user, report, error=str(exc), status_code=400)
    confirm(request, "Chart image uploaded.")
    return RedirectResponse(f"/admin/reports/{report_id}", status_code=303)


@router.post("/{report_id}/images/{name}/delete", dependencies=[Depends(require_csrf)])
def delete_image(request: Request, report_id: int, name: str,
                 user=Depends(current_user)):
    _editable_or_403(report_id, user)
    try:
        if not reports.remove_image(report_id, name, user=user):
            raise HTTPException(status_code=404)
    except reports.ReportLocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    confirm(request, "Chart image deleted.")
    return RedirectResponse(f"/admin/reports/{report_id}", status_code=303)


def _set_status(request: Request, report_id: int, status: str, message: str):
    if not reports.set_status(report_id, status):
        raise HTTPException(status_code=404)
    confirm(request, message + SITE_NOTE)
    return RedirectResponse("/admin/reports", status_code=303)


@router.post("/{report_id}/publish",
             dependencies=[Depends(require_director), Depends(require_csrf)])
def publish(request: Request, report_id: int):
    return _set_status(request, report_id, "published", "Report published.")


@router.post("/{report_id}/unpublish",
             dependencies=[Depends(require_director), Depends(require_csrf)])
def unpublish(request: Request, report_id: int):
    return _set_status(request, report_id, "draft", "Report moved back to Draft.")


@router.post("/{report_id}/delete",
             dependencies=[Depends(require_director), Depends(require_csrf)])
def delete(request: Request, report_id: int):
    if not reports.delete(report_id):
        raise HTTPException(status_code=404)
    confirm(request, "Report deleted.")
    return RedirectResponse("/admin/reports", status_code=303)
