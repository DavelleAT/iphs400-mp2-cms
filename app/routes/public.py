"""The public site, served at the same paths `cms publish` exports it to. No
login: everything here is published content only (app.public_site)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

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


@router.get("/reports/files/{slug}.pdf")
def report_file(slug: str):
    found = public_site.report_file(slug)
    if found is None:
        raise HTTPException(status_code=404)
    path, name = found
    return FileResponse(path, media_type="application/pdf", filename=name,
                        headers={"X-Content-Type-Options": "nosniff"})
