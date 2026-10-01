"""The Jinja environment the admin console and the public site render with."""
from __future__ import annotations

from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from app import settings
from app.auth import csrf_token
from app.content import SUMMARY_MAX
from app.flash import confirmation
from app.rendering import render_markdown
from app.users import ROLE_LABELS



@pass_context
def path_for(context, name: str, **path_params) -> str:
    """The path of the admin route called `name` (its function's name), e.g.
    path_for("edit_report_form", report_id=3) -> "/admin/reports/3", so a
    template never hard-codes a route's path. Admin pages only: the public
    site links relatively (app.public_site)."""
    return str(context["request"].app.url_path_for(name, **path_params))


templates = Jinja2Templates(directory=str(settings.TEMPLATES))
templates.env.globals["path_for"] = path_for
templates.env.globals["csrf_token"] = csrf_token
templates.env.globals["confirmation"] = confirmation
templates.env.globals["summary_max"] = SUMMARY_MAX
templates.env.filters["role_label"] = ROLE_LABELS.get
templates.env.filters["markdown"] = render_markdown
