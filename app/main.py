"""The FastAPI application.

T00 (already done): the admin console answers at /admin and the public site
answers at /. That is the whole skeleton — it exists so you can prove the stack
runs before you build anything on it.

Add your routes in their own modules (app/routes/posts.py and so on) and include
them here. Keep this file small.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates

from app import settings

templates = Jinja2Templates(directory=str(settings.TEMPLATES))


def create_app() -> FastAPI:
    app = FastAPI(title="IPHS 400 MP2 CMS")

    @app.get("/admin")
    def admin_home(request: Request):
        return templates.TemplateResponse(
            request, "admin/hello.html", {"title": "Admin"}
        )

    @app.get("/")
    def public_home(request: Request):
        return templates.TemplateResponse(
            request, "public/home.html",
            {"title": settings.SITE_TITLE, "items": []},
        )

    # Your ticket work plugs in here, e.g.
    #   from app.routes import posts
    #   app.include_router(posts.router)
    return app


app = create_app()
