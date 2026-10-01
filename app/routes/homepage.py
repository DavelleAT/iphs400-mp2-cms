"""Homepage settings in the admin console (app.homepage): Director only.
An Analyst gets 403 on every route here."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app import homepage
from app.auth import require_csrf, require_director
from app.flash import SITE_NOTE, confirm
from app.templating import templates

router = APIRouter(prefix="/admin/homepage", dependencies=[Depends(require_director)])


def _page(request: Request, user: sqlite3.Row, form: dict[str, str], *,
          error: homepage.SettingsError | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/homepage.html",
        {"title": "Homepage", "user": user, "form": form,
         "limits": homepage.LIMITS, "figures_max": homepage.FIGURES_MAX,
         "error": None if error is None else str(error),
         "error_field": None if error is None else error.field},
        status_code=status_code)


@router.get("")
def edit_homepage(request: Request, user=Depends(require_director)):
    return _page(request, user, homepage.form_of(homepage.get()))


@router.post("", dependencies=[Depends(require_csrf)])
async def save_homepage(request: Request, user=Depends(require_director)):
    # Every field by name, which the form numbers; require_csrf has read it.
    form = {name: value for name, value in (await request.form()).items()
            if isinstance(value, str)}
    try:
        homepage.save(homepage.from_form(form))
    except homepage.SettingsError as exc:
        return _page(request, user, {**homepage.form_of(homepage.get()), **form},
                     error=exc, status_code=400)
    confirm(request, "Homepage saved." + SITE_NOTE)
    return RedirectResponse("/admin/homepage", status_code=303)
