"""What the console's item lists share (spec #25, T22): the Data Bites,
Reports, and All content pages show one `table-items` table, each row an
item's title and Summary, its State, author, last update, and the actions the
signed-in user may take on it; and they filter by State with `?status=`."""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import NamedTuple

from fastapi import HTTPException, Query, Request

from app import data_bites, reports
from app.content import STATUS_LABELS
from app.templating import templates
from app.users import is_director


@dataclass(frozen=True)
class ContentType:
    key: str          # e.g. "data-bite", as used in ids and query strings
    noun: str         # e.g. "Data Bite"
    plural: str       # e.g. "Data Bites"
    module: ModuleType
    id_param: str     # its routes' id parameter, e.g. "bite_id"
    list_route: str   # its admin routes' names, for url_path_for / path_for
    edit_route: str
    delete_route: str  # the confirm-delete page
    director_publishes: bool  # only a Director may publish or unpublish one
    can_edit: Callable[[sqlite3.Row, sqlite3.Row], bool]  # (item, user): else read-only


DATA_BITE = ContentType("data-bite", "Data Bite", "Data Bites", data_bites, "bite_id",
                        "list_bites", "edit_bite_form", "confirm_delete_bite",
                        director_publishes=False, can_edit=lambda item, user: True)
REPORT = ContentType("report", "Report", "Reports", reports, "report_id",
                     "list_reports", "edit_report_form", "confirm_delete_report",
                     director_publishes=True, can_edit=reports.can_edit)
CONTENT_TYPES = (DATA_BITE, REPORT)

# The State filters, in order: the query value ("" for all) and its label.
STATUS_FILTERS = (("", "All"), ("published", "Published"), ("draft", "Drafts"))


def _one_of(value: str, allowed, name: str) -> str:
    if value not in ("", *allowed):
        raise HTTPException(status_code=400, detail=f"Unknown {name} filter.")
    return value


def status_filter(status: str = "") -> str:
    """`?status=` as a route dependency: "" (all), or a State. 400 for any
    other value."""
    return _one_of(status, STATUS_LABELS, "status")


def type_filter(content_type: str = Query("", alias="type")) -> str:
    """All content's `?type=`: "" (all), or a type's key. 400 for any other
    value."""
    return _one_of(content_type, [ctype.key for ctype in CONTENT_TYPES], "type")


@dataclass(frozen=True)
class ItemRow:
    """One row of a list: the item, its type, what the user may do with it,
    and where each action goes, from the routes."""
    ctype: ContentType
    item: sqlite3.Row
    may_edit: bool             # else its page is read-only for the user ("View")
    edit_path: str
    status_path: str | None    # publish a draft, or unpublish; None if not the user's to do.
                               # It returns to the list filtered as it was.
    delete_path: str | None    # Director only


def item_row(request: Request, ctype: ContentType, item: sqlite3.Row, user: sqlite3.Row,
             *, back_status: str = "") -> ItemRow:
    """`item`'s row for `user`. `back_status` is the list's State filter, which
    Publish and Unpublish return to."""
    def path(route: str) -> str:
        # The publish and unpublish routes share their names across the types;
        # the id parameter picks the type's.
        return str(request.app.url_path_for(route, **{ctype.id_param: item["id"]}))

    director = is_director(user)
    may_publish = director or not ctype.director_publishes
    action = "unpublish" if item["status"] == "published" else "publish"
    back = f"?status={back_status}" if back_status else ""
    return ItemRow(ctype, item, may_edit=ctype.can_edit(item, user),
                   edit_path=path(ctype.edit_route),
                   status_path=path(action) + back if may_publish else None,
                   delete_path=path(ctype.delete_route) if director else None)


class StateFilter(NamedTuple):
    href: str
    label: str
    count: int     # how many items it shows
    current: bool  # the one shown


def filters(path: str, counts: dict[str, int], chosen: str) -> list[StateFilter]:
    """The State filters for the list at `path`."""
    return [StateFilter(f"{path}?status={value}" if value else path, label,
                        counts[value] if value else sum(counts.values()), value == chosen)
            for value, label in STATUS_FILTERS]


def list_page(request: Request, user: sqlite3.Row, ctype: ContentType, status: str,
              template: str):
    """A type's own list, `template`, narrowed to `status` ("" for all)."""
    return templates.TemplateResponse(
        request, template,
        {"title": ctype.plural, "user": user, "ctype": ctype,
         "rows": [item_row(request, ctype, item, user, back_status=status)
                  for item in ctype.module.list_all(status or None)],
         "filters": filters(request.url.path, ctype.module.count_by_status(), status),
         "status": status, "status_labels": STATUS_LABELS},
    )
