"""Login and logout, and the admin console's stylesheet, which the login page
needs before there is a session."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, RedirectResponse

from app import auth, settings, users
from app.templating import templates

router = APIRouter()

LOGIN_FAILED = "Invalid email or password."


def _login_page(request: Request, error: str | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request, "login.html",
        {"title": "Log in", "error": error},
        status_code=status_code,
    )


@router.get("/login")
def login_form(request: Request):
    return _login_page(request)


@router.post("/login", dependencies=[Depends(auth.require_csrf)])
def login(request: Request, email: str = Form(""), password: str = Form("")):
    user = users.authenticate(email, password)
    if user is None:
        # Same message whether the account is unknown, inactive, or the
        # password is wrong.
        return _login_page(request, LOGIN_FAILED, status_code=401)
    auth.log_in(request, user)
    return RedirectResponse("/admin", status_code=303)


@router.post("/logout", dependencies=[Depends(auth.require_csrf)])
def logout(request: Request):
    auth.log_out(request)
    return RedirectResponse("/login", status_code=303)


@router.get("/admin.css")
def admin_stylesheet():
    """The console's own stylesheet (ADR-007); the public site's is style.css."""
    return FileResponse(settings.STATIC / "admin.css", media_type="text/css; charset=utf-8")
