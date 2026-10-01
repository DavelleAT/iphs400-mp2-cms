"""A Site preview's own copy of the site, which the Data Bite and Report
admin routes serve under their login at /admin/<type>/<id>/preview/ (and
/admin/<type>/preview/ for a new item). A Site preview's links are relative
and resolve there (app.public_site.Page.render_preview)."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import RedirectResponse, Response

from app import chart_images, public_site
from app.routes.public import asset, pdf_response

# A path in the site, as the *_path functions of app.public_site make them:
# never starting with "/" or a backslash, so a redirect to "/" + it stays on
# this site.
_SITE_PATH = re.compile(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", re.ASCII)


def site_file(path: str, images: dict[str, Path], pdfs: dict[str, Path] | None = None) -> Response:
    """What a Site preview's link to `path` in the site gets: the stylesheet
    or a font (public_site.assets), or one of the previewed item's own chart
    `images` or `pdfs` (a Report's file), by path in the site, which the
    public site would not serve for a draft. Any other page sends the browser
    to the published one."""
    if path in public_site.assets():
        return asset(path)
    if path in images:
        return chart_images.response(images[path])
    if pdfs and path in pdfs:
        return pdf_response(pdfs[path])
    if not _SITE_PATH.fullmatch(path):
        raise HTTPException(status_code=404)
    return RedirectResponse("/" + path, status_code=303)
