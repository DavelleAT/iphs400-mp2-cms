"""The FastAPI application.

The admin console lives under /admin (login required) and the public preview
at /. Routes live in their own modules under app/routes/ and are included here.
Keep this file small.
"""
from __future__ import annotations

import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from app import db, settings
from app.auth import LoginRequired, current_user
from app.data_bites import list_published as published_data_bites
from app.routes import admin, auth, data_bites, users
from app.templating import templates

SESSION_MAX_AGE = 8 * 60 * 60  # one working day
ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # At server start, not import, so importing app.main never touches a database.
    db.init_db()
    if settings.SECRET_KEY_IS_PLACEHOLDER:
        print("WARNING: CMS_SECRET_KEY is unset or the .env.example placeholder; "
              "session cookies can be forged. Set a long random value in .env.",
              file=sys.stderr)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="IPHS 400 MP2 CMS", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware, secret_key=settings.SECRET_KEY,
        session_cookie="cms_session", max_age=SESSION_MAX_AGE, same_site="lax",
    )

    @app.exception_handler(LoginRequired)
    def redirect_to_login(request: Request, exc: LoginRequired):
        return RedirectResponse("/login", status_code=303)

    @app.get("/")
    def public_home(request: Request):
        # Titles only: the public Data Bite pages (and links to them) arrive
        # with the public-site ticket, T07.
        items = [{"title": b["title"]} for b in published_data_bites()]
        return templates.TemplateResponse(
            request, "public/home.html",
            {"title": settings.SITE_TITLE, "items": items},
        )

    app.include_router(auth.router)
    app.include_router(admin.router)
    app.include_router(users.router)
    app.include_router(data_bites.router)

    # Must stay last: any /admin request no router above claimed, by path or by
    # method. Anonymous visitors are sent to login (so they can't probe which
    # admin paths exist); signed-in users get 405/404.
    @app.api_route("/admin", methods=ALL_METHODS,
                   dependencies=[Depends(current_user)], include_in_schema=False)
    def admin_method_not_allowed():
        raise HTTPException(status_code=405)

    @app.api_route("/admin/{rest:path}", methods=ALL_METHODS,
                   dependencies=[Depends(current_user)], include_in_schema=False)
    def admin_not_found(rest: str):
        if rest == "":
            return RedirectResponse("/admin", status_code=307)
        raise HTTPException(status_code=404)

    return app


app = create_app()
