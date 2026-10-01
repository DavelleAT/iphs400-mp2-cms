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

from app import chart_images, editor, public_site, reports, uploads
from app.flash import SITE_NOTE, confirm
from app.auth import current_user, require_csrf, require_director
from app.content import STATUS_LABELS, ContentError
from app.rendering import images_without_description
from app.routes import editing, listing
from app.routes.site_preview import site_file
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


def _images(request: Request, report_id: int) -> editor.ImageLinks:
    return editing.image_links(request, "serve_image", report_id=report_id)


@router.get("")
def list_reports(request: Request, user=Depends(current_user),
                 status: str = Depends(listing.status_filter)):
    return templates.TemplateResponse(
        request, "admin/reports.html",
        {"title": "Reports", "user": user,
         "rows": [listing.item_row(listing.REPORT, report, user)
                  for report in reports.list_all(status or None)],
         "filters": listing.filters(request.url.path, reports.count_by_status(), status),
         "status": status, "status_labels": STATUS_LABELS},
    )


def _new_page(request: Request, user: sqlite3.Row, *, error: ContentError | None = None,
              form: dict | None = None, status_code: int = 200):
    """The create form, on its own page; again, with what was typed, after a
    refused create (a chosen file is not kept)."""
    form = form or {"title": "", "slug": "", "summary": "", "body": ""}
    body = editor.full_body(form["body"], "")
    return templates.TemplateResponse(
        request, "admin/report_new.html",
        {"title": "New Report", "user": user,
         **editing.error_for(error), "form": form, "max_file_mb": _MAX_FILE_MB,
         "editor_html": editor.editor_html(form["body"], "", None),
         **editing.site_links_for(body),
         "site_preview": _site_preview(request, {**form, "body": body}, None),
         "preview_path": request.app.url_path_for("preview_new_report")},
        status_code=status_code,
    )


@router.post("", dependencies=[Depends(require_csrf)])
def create_report(request: Request, user=Depends(current_user), title: str = Form(""),
                  slug: str = Form(""), summary: str = Form(""),
                  posted: editor.Posted = Depends(editing.posted),
                  file: UploadFile | None = File(None)):
    try:
        pdf = uploads.read_pdf(file)
        report_id = reports.create(title, slug, editor.saved_body(posted, None, None),
                                   user["id"], summary=summary, pdf=pdf)
    except ContentError as exc:
        return _new_page(request, user, error=exc, status_code=400,
                         form=editor.form_after(posted, title, slug, "", None, None,
                                                summary=summary))
    confirm(request, "Report created as a Draft, with its attached file." if pdf
            else "Report created as a Draft.")
    return RedirectResponse(request.app.url_path_for("edit_report_form", report_id=report_id),
                            status_code=303)


# The create page and a new Report's Site preview. Before the /{report_id}
# routes, which would otherwise take "new" or "preview" for an id.

@router.get("/new")
def new_report_form(request: Request, user=Depends(current_user)):
    return _new_page(request, user)


@router.post("/preview", dependencies=[Depends(require_csrf)])
def preview_new_report(request: Request, title: str = Form(""), summary: str = Form(""),
                       posted: editor.Posted = Depends(editing.posted)):
    """The create form's Site preview, for its frame and "Preview on site".
    Saves nothing; a file chosen in the form is not read."""
    shown = editing.previewed(posted, None, None)
    return HTMLResponse(_site_preview(
        request, {"title": title, "summary": summary, "body": shown}, None))


@router.get("/preview/{path:path}")
def new_report_preview_site(path: str):
    """The create form's Site preview's copy of the site: only its stylesheet,
    as a new Report has no chart images or file (app.routes.site_preview)."""
    return site_file(path, images={})


def _edit_page(request: Request, user: sqlite3.Row, report: sqlite3.Row, *,
               error: ContentError | None = None, form: dict | None = None,
               status_code: int = 200):
    form = form or editor.form_for(report)
    # The body with its locked blocks, which only the server sees.
    body = editor.full_body(form["body"], report["body"])
    links, names = _images(request, report["id"]), list(reports.images(report["id"]))
    return templates.TemplateResponse(
        request, "admin/report_edit.html",
        {"title": "Edit Report", "user": user,
         "report": report, "can_edit": reports.can_edit(report, user),
         "status_labels": STATUS_LABELS, **editing.error_for(error), "form": form,
         "max_file_mb": _MAX_FILE_MB,
         "editor_html": editor.editor_html(form["body"], report["body"], links.src),
         "images": names,
         "body_images": editing.body_images(links, names),
         **editing.site_links_for(body),
         "site_preview": _site_preview(request, {**form, "body": body}, report),
         "preview_path": request.app.url_path_for("preview_report", report_id=report["id"]),
         "undescribed_images": images_without_description(body),
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
                title: str = Form(""), slug: str = Form(""), summary: str = Form(""),
                posted: editor.Posted = Depends(editing.posted),
                item_base: str = Form(""), file: UploadFile | None = File(None)):
    report = _editable_or_403(report_id, user)
    image_name = _images(request, report_id).name
    try:
        pdf = uploads.read_pdf(file)
        if not reports.update(report_id, title, slug,
                              editor.saved_edit(posted, report, item_base, image_name),
                              user=user, summary=summary, pdf=pdf,
                              base=item_base or None):
            raise HTTPException(status_code=404)
    except reports.ReportLocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    except ContentError as exc:
        # Shown over the Report as stored now, which a stale form missed.
        current = _get_or_404(report_id)
        return _edit_page(request, user, current, error=exc,
                          status_code=editing.refused_status(exc),
                          form=editor.form_after(posted, title, slug, item_base,
                                                 current["body"], image_name,
                                                 summary=summary))
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
                   title: str = Form(""), summary: str = Form(""),
                   posted: editor.Posted = Depends(editing.posted)):
    """The edit form's Site preview, of its unsaved title and body, for its
    frame and "Preview on site". Only for a user who may make those edits
    (the lockdown). Saves nothing; a file chosen in the form is not read."""
    report = _editable_or_403(report_id, user)
    shown = editing.previewed(posted, report["body"],
                      _images(request, report_id).name)
    return HTMLResponse(_site_preview(
        request, {"title": title, "summary": summary, "body": shown}, report))


@router.get("/{report_id}/preview/{path:path}")
def report_preview_site(request: Request, report_id: int, path: str):
    """The Site preview's copy of the site: its stylesheet and the Report's
    chart images and file, draft or not, which any signed-in user may already
    download here (app.routes.site_preview). Its own page, which a draft's
    Site preview links from the nav, is its Site preview as saved."""
    report = _get_or_404(report_id)
    if path == public_site.report_path(report["slug"]):
        return HTMLResponse(_site_preview(request, report, report))
    return site_file(path, images=public_site.report_image_files(report),
                     pdfs=public_site.report_pdf_file(report))


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
        return _edit_page(request, user, report, error=exc, status_code=400)
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


@router.get("/{report_id}/delete", dependencies=[Depends(require_director)])
def confirm_delete_report(request: Request, report_id: int, user=Depends(current_user)):
    return editing.confirm_delete(request, user, _get_or_404(report_id), "report",
                                  back=request.app.url_path_for("list_reports"))


@router.post("/{report_id}/delete",
             dependencies=[Depends(require_director), Depends(require_csrf)])
def delete(request: Request, report_id: int):
    if not reports.delete(report_id):
        raise HTTPException(status_code=404)
    confirm(request, "Report deleted.")
    return RedirectResponse("/admin/reports", status_code=303)
