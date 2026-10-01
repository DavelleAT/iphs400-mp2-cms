"""User management: Director only. Analysts get 403 on every route here."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from app import users
from app.auth import require_csrf, require_director
from app.flash import confirm
from app.templating import templates

router = APIRouter(prefix="/admin/users", dependencies=[Depends(require_director)])


def _users_page(request: Request, user: sqlite3.Row, *, error: str | None = None,
                form: dict | None = None, status_code: int = 200):
    return templates.TemplateResponse(
        request, "admin/users.html",
        {"title": "Users", "user": user,
         "users": users.list_users(), "role_labels": users.ROLE_LABELS,
         "min_password_length": users.MIN_PASSWORD_LENGTH,
         "error": error, "form": form or {}},
        status_code=status_code,
    )


@router.get("")
def list_users(request: Request, user=Depends(require_director)):
    return _users_page(request, user)


@router.post("", dependencies=[Depends(require_csrf)])
def create_user(request: Request, user=Depends(require_director),
                email: str = Form(""), name: str = Form(""),
                password: str = Form(""), role: str = Form("")):
    try:
        users.create_user(email, password, role, name=name)
    except users.UserError as exc:
        # Re-fill everything but the password.
        return _users_page(request, user, error=str(exc), status_code=400,
                           form={"email": email, "name": name, "role": role})
    confirm(request, "User created.")
    return RedirectResponse("/admin/users", status_code=303)


# A Director may not demote or deactivate themselves: the acting Director always
# stays an active Director, so the office can never lose its last one.
SELF_LOCKOUT = "You can't change the role of, or deactivate, your own account."


@router.post("/{user_id}/role", dependencies=[Depends(require_csrf)])
def change_role(request: Request, user_id: int, user=Depends(require_director),
                role: str = Form("")):
    if user_id == user["id"]:
        return _users_page(request, user, error=SELF_LOCKOUT, status_code=400)
    try:
        found = users.set_role(user_id, role)
    except users.UserError as exc:
        return _users_page(request, user, error=str(exc), status_code=400)
    if not found:
        raise HTTPException(status_code=404)
    confirm(request, "Role changed.")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/{user_id}/deactivate", dependencies=[Depends(require_csrf)])
def deactivate(request: Request, user_id: int, user=Depends(require_director)):
    if user_id == user["id"]:
        return _users_page(request, user, error=SELF_LOCKOUT, status_code=400)
    if not users.deactivate(user_id):
        raise HTTPException(status_code=404)
    confirm(request, "User deactivated.")
    return RedirectResponse("/admin/users", status_code=303)
