"""Reports in the admin console. Any signed-in user may list Reports, create a
draft, edit a draft (its body or its attached file), and download a Report's
file. Editing a published Report or its file, and publishing, unpublishing, or
deleting any Report, is Director only."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from app import reports, uploads
from app.auth import current_user, require_csrf, require_director
from app.content import STATUS_LABELS, ContentError
from app.templating import templates

router = APIRouter(prefix="/admin/reports", dependencies=[Depends(current_user)])
_MAX_FILE_MB = uploads.MAX_BYTES // uploads.MIB


def _list_page(request: Request, user: sqlite3.Row, *, error: str | None = None,
               form: dict | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/reports.html",
        {"title": "Reports", "home_path": "/admin", "user": user,
         "reports": reports.list_all(), "status_labels": STATUS_LABELS,
         "error": error, "form": form or {}, "max_file_mb": _MAX_FILE_MB},
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
        reports.create(title, slug, body, user["id"], pdf=uploads.read_pdf(file))
    except ContentError as exc:
        return _list_page(request, user, error=str(exc), status_code=400,
                          form={"title": title, "slug": slug, "body": body})
    return RedirectResponse("/admin/reports", status_code=303)


def _edit_page(request: Request, user: sqlite3.Row, report: sqlite3.Row, *,
               error: str | None = None, form: dict | None = None,
               status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/report_edit.html",
        {"title": "Edit Report", "home_path": "/admin", "user": user,
         "report": report, "can_edit": reports.can_edit(report, user),
         "status_labels": STATUS_LABELS, "error": error, "form": form or report,
         "max_file_mb": _MAX_FILE_MB},
        status_code=status_code,
    )


def _get_or_404(report_id: int) -> sqlite3.Row:
    report = reports.get(report_id)
    if report is None:
        raise HTTPException(status_code=404)
    return report


@router.get("/{report_id}")
def edit_form(request: Request, report_id: int, user=Depends(current_user)):
    return _edit_page(request, user, _get_or_404(report_id))


@router.post("/{report_id}", dependencies=[Depends(require_csrf)])
def edit_report(request: Request, report_id: int, user=Depends(current_user),
                title: str = Form(""), slug: str = Form(""), body: str = Form(""),
                file: UploadFile | None = File(None)):
    report = _get_or_404(report_id)
    # Permission before validation: a locked Report is 403 whatever was sent.
    if not reports.can_edit(report, user):
        raise HTTPException(status_code=403, detail="Only the Director can edit a published Report.")
    try:
        if not reports.update(report_id, title, slug, body, user=user,
                              pdf=uploads.read_pdf(file)):
            raise HTTPException(status_code=404)
    except reports.ReportLocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    except ContentError as exc:
        return _edit_page(request, user, report, error=str(exc), status_code=400,
                          form={"title": title, "slug": slug, "body": body})
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
def remove_file(report_id: int, user=Depends(current_user)):
    try:
        if not reports.remove_file(report_id, user=user):
            raise HTTPException(status_code=404)
    except reports.ReportLocked as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
    return RedirectResponse(f"/admin/reports/{report_id}", status_code=303)


def _set_status(report_id: int, status: str):
    if not reports.set_status(report_id, status):
        raise HTTPException(status_code=404)
    return RedirectResponse("/admin/reports", status_code=303)


@router.post("/{report_id}/publish",
             dependencies=[Depends(require_director), Depends(require_csrf)])
def publish(report_id: int):
    return _set_status(report_id, "published")


@router.post("/{report_id}/unpublish",
             dependencies=[Depends(require_director), Depends(require_csrf)])
def unpublish(report_id: int):
    return _set_status(report_id, "draft")


@router.post("/{report_id}/delete",
             dependencies=[Depends(require_director), Depends(require_csrf)])
def delete(report_id: int):
    if not reports.delete(report_id):
        raise HTTPException(status_code=404)
    return RedirectResponse("/admin/reports", status_code=303)
