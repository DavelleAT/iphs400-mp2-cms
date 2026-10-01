"""The public site, served at the same paths `cms publish` exports it to. No
login: everything here is published content only (app.public_site)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

from app import chart_images, public_site
from app.public_site import Page

router = APIRouter()


def _html(page: Page | None) -> HTMLResponse:
    if page is None:
        raise HTTPException(status_code=404)
    return HTMLResponse(page.render())


@router.get("/")
@router.get("/index.html")
def home():
    return _html(public_site.home())


@router.get("/404.html")
def not_found():
    return _html(public_site.not_found())


@router.get("/style.css")
def stylesheet():
    return asset("style.css")


@router.get("/fonts/{name}")
def font(name: str):
    return asset(f"fonts/{name}")


# By extension, so a font or licence is never sniffed as anything else.
_ASSET_TYPES = {".css": "text/css; charset=utf-8", ".woff2": "font/woff2",
                ".txt": "text/plain; charset=utf-8"}


def asset(path: str) -> FileResponse:
    """The stylesheet, or a font or its licence, at `path` in the site
    (public_site.assets)."""
    stored = public_site.assets().get(path)
    if stored is None:
        raise HTTPException(status_code=404)
    return FileResponse(stored, media_type=_ASSET_TYPES[stored.suffix],
                        headers={"X-Content-Type-Options": "nosniff"})


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
    return pdf_response(*found)


def pdf_response(path: Path, name: str | None = None) -> FileResponse:
    """A Report's stored file, served as a PDF and never sniffed as anything
    else; downloaded as `name` if one is given."""
    return FileResponse(path, media_type="application/pdf", filename=name,
                        headers={"X-Content-Type-Options": "nosniff"})
