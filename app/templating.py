"""The Jinja environment the admin console and the public site render with."""
from __future__ import annotations

from typing import NamedTuple

from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from app import settings
from app.auth import csrf_token
from app.content import SUMMARY_MAX
from app.flash import confirmation
from app.rendering import render_markdown
from app.users import ROLE_LABELS, is_director


@pass_context
def path_for(context, name: str, **path_params) -> str:
    """The path of the admin route called `name` (its function's name), e.g.
    path_for("edit_report_form", report_id=3) -> "/admin/reports/3", so a
    template never hard-codes a route's path. Admin pages only: the public
    site links relatively (app.public_site)."""
    return str(context["request"].app.url_path_for(name, **path_params))


class NavItem(NamedTuple):
    label: str
    route: str           # the admin route's name, for path_for
    director_only: bool


# The console's numbered nav (spec #25), in order.
CONSOLE_NAV = (NavItem("Dashboard", "admin_home", False), NavItem("Data Bites", "list_bites", False),
               NavItem("Reports", "list_reports", False), NavItem("Homepage", "edit_homepage", True),
               NavItem("Users", "list_users", True))


@pass_context
def console_nav(context, user) -> list[dict]:
    """`user`'s nav items, numbered as in CONSOLE_NAV, each with its path and
    whether it is the section the page is in: the item whose path is the
    longest prefix of the page's. A page in a section `user` may not see
    (an Analyst's "Not allowed" at /admin/users) marks none."""
    request = context["request"]
    page = request.url.path
    items = [(nav, {"number": f"{n:02d}", "label": nav.label,
                    "path": str(request.app.url_path_for(nav.route))})
             for n, nav in enumerate(CONSOLE_NAV, start=1)]
    within = [item for _, item in items
              if page == item["path"] or page.startswith(item["path"] + "/")]
    here = max(within, key=lambda item: len(item["path"]), default=None)
    return [{**item, "current": item is here} for nav, item in items
            if is_director(user) or not nav.director_only]


templates = Jinja2Templates(directory=str(settings.TEMPLATES))
templates.env.globals["path_for"] = path_for
templates.env.globals["csrf_token"] = csrf_token
templates.env.globals["console_nav"] = console_nav
templates.env.globals["confirmation"] = confirmation
templates.env.globals["summary_max"] = SUMMARY_MAX
templates.env.filters["role_label"] = ROLE_LABELS.get
templates.env.filters["markdown"] = render_markdown
