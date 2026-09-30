"""The public site, served at the same paths `cms publish` exports it to. No
login: everything here is published content only (app.public_site).

Also `preview_site_file`, which the admin routes use to serve a Site
preview's own copy of the site, behind their login."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response

from app import chart_images, public_site
from app.public_site import Page

router = APIRouter()
# A path in the site, as the *_path functions of app.public_site make them:
# never starting with "/" or a backslash, so a redirect to "/" + it stays on this site.
_SITE_PATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", re.ASCII)


def _html(page: Page | None) -> HTMLResponse:
    if page is None:
        raise HTTPException(status_code=404)
    return HTMLResponse(page.render())


@router.get("/")
@router.get("/index.html")
def home():
    return _html(public_site.home())


@router.get("/style.css")
def stylesheet():
    return Response(public_site.CSS, media_type="text/css")


@router.get("/data-bites/")
@router.get("/data-bites/index.html")
def data_bite_list():
    return _html(public_site.data_bite_list())


@router.get("/data-bites/{slug}.html")
def data_bite(slug: str):
    return _html(public_site.data_bite(slug))


@router.get("/images/data-bites/{slug}/{name}")
def data_bite_image(slug: str, name: str):
    path = public_site.data_bite_image(slug, name)
    if path is None:
        raise HTTPException(status_code=404)
    return chart_images.response(path)


@router.get("/reports/")
@router.get("/reports/index.html")
def report_list():
    return _html(public_site.report_list())


@router.get("/reports/{slug}.html")
def report(slug: str):
    return _html(public_site.report(slug))


@router.get("/images/reports/{slug}/{name}")
def report_image(slug: str, name: str):
    path = public_site.report_image(slug, name)
    if path is None:
        raise HTTPException(status_code=404)
    return chart_images.response(path)


@router.get("/reports/files/{slug}.pdf")
def report_file(slug: str):
    found = public_site.report_file(slug)
    if found is None:
        raise HTTPException(status_code=404)
    path, name = found
    return FileResponse(path, media_type="application/pdf", filename=name,
                        headers={"X-Content-Type-Options": "nosniff"})


def preview_site_file(path: str, files: dict[str, Path]):
    """What a Site preview's link to `path` in the site gets
    (app.public_site.Page.render_preview): the stylesheet, or one of `files`,
    the previewed item's own, which the public site would not serve for a
    draft. Any other page sends the browser to the published one."""
    if path == "style.css":
        return stylesheet()
    stored = files.get(path)
    if stored is None:
        if not _SITE_PATH.fullmatch(path):
            raise HTTPException(status_code=404)
        return RedirectResponse("/" + path, status_code=303)
    if stored.suffix == ".pdf":  # a Report's file (reports.file_path)
        return FileResponse(stored, media_type="application/pdf",
                            headers={"X-Content-Type-Options": "nosniff"})
    return chart_images.response(stored)
