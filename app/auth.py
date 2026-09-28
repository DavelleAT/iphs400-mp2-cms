"""Sessions and CSRF.

The session is a signed cookie (Starlette's SessionMiddleware, which signs with
itsdangerous). It holds only the user's id and a CSRF token. The user is
re-loaded from the database on every protected request, so deactivating an
account ends its sessions at once.
"""
from __future__ import annotations

import secrets
import sqlite3

from fastapi import Depends, HTTPException, Request

from app import users


class LoginRequired(Exception):
    """Raised by current_user; main.py turns it into a redirect to /login."""


def current_user(request: Request) -> sqlite3.Row:
    """Dependency: the logged-in, still-active user, or LoginRequired."""
    user_id = request.session.get("user_id")
    user = users.get_active_user(user_id) if user_id is not None else None
    if user is None:
        request.session.clear()
        raise LoginRequired
    return user


def require_director(user: sqlite3.Row = Depends(current_user)) -> sqlite3.Row:
    """Dependency: current_user, but 403 unless they are a Director."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Directors only.")
    return user


def log_in(request: Request, user: sqlite3.Row) -> None:
    # A fresh session (and CSRF token) on login, so a pre-login cookie planted
    # by someone else never becomes an authenticated one.
    request.session.clear()
    request.session["user_id"] = user["id"]
    csrf_token(request)


def log_out(request: Request) -> None:
    request.session.clear()


def csrf_token(request: Request) -> str:
    """The session's CSRF token, created on first use. Templates call this."""
    token = request.session.get("csrf_token")
    if token is None:
        token = request.session["csrf_token"] = secrets.token_urlsafe(32)
    return token


async def require_csrf(request: Request) -> None:
    """Dependency for every state-changing POST: the form's csrf_token must
    match the session's."""
    form = await request.form()
    submitted = form.get("csrf_token")
    expected = request.session.get("csrf_token")
    if not (isinstance(submitted, str) and expected
            and secrets.compare_digest(submitted, expected)):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token.")
