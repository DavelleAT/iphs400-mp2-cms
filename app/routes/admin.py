"""The admin console. Every route on this router requires an active session:
add new admin routes here (or to a router built the same way) and they are
protected without further work."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.auth import current_user
from app.templating import templates

router = APIRouter(prefix="/admin", dependencies=[Depends(current_user)])


@router.get("")
def admin_home(request: Request, user=Depends(current_user)):
    return templates.TemplateResponse(
        request, "admin/home.html",
        {"title": "Admin", "home_path": "/admin", "user": user},
    )
