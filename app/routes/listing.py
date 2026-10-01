"""What the console's item lists share (spec #25, T22): the Data Bites,
Reports, and All content pages show one `table-items` table, each row an
item's title and Summary, its state, author, last update, and the actions the
signed-in user may take on it; and they filter by state with `?status=`."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from types import ModuleType

from fastapi import HTTPException

from app import data_bites, reports
from app.content import STATUS_LABELS
from app.users import is_director


@dataclass(frozen=True)
class ContentType:
    key: str        # e.g. "data-bite", as used in ids and query strings
    noun: str       # e.g. "Data Bite"
    plural: str     # e.g. "Data Bites"
    module: ModuleType
    list_path: str  # the type's own admin page, e.g. "/admin/data-bites"
    director_publishes: bool  # only a Director may publish, unpublish, or edit a published one


DATA_BITE = ContentType("data-bite", "Data Bite", "Data Bites", data_bites, "/admin/data-bites",
                        director_publishes=False)
REPORT = ContentType("report", "Report", "Reports", reports, "/admin/reports",
                     director_publishes=True)
CONTENT_TYPES = (DATA_BITE, REPORT)

# The state filters, in order: the query value ("" for all) and its label.
STATUS_FILTERS = (("", "All"), ("published", "Published"), ("draft", "Drafts"))


def status_filter(status: str = "") -> str:
    """`?status=` as a route dependency: "" (all), or a state. 400 for any
    other value."""
    if status not in ("", *STATUS_LABELS):
        raise HTTPException(status_code=400, detail="Unknown status filter.")
    return status


@dataclass(frozen=True)
class ItemRow:
    """One row of a list: the item, its type, and what the user may do."""
    ctype: ContentType
    item: sqlite3.Row
    may_edit: bool     # else its page is read-only for the user ("View")
    may_publish: bool  # publish a draft, or unpublish a published item
    may_delete: bool


def item_row(ctype: ContentType, item: sqlite3.Row, user: sqlite3.Row) -> ItemRow:
    director = is_director(user)
    return ItemRow(ctype, item,
                   may_edit=not ctype.director_publishes or reports.can_edit(item, user),
                   may_publish=director or not ctype.director_publishes,
                   may_delete=director)


def filters(path: str, counts: dict[str, int], chosen: str) -> list[dict]:
    """The state filters for the list at `path`: each one's link, label,
    how many items it shows, and whether it is the one shown."""
    return [{"href": f"{path}?status={value}" if value else path, "label": label,
             "count": counts[value] if value else sum(counts.values()),
             "current": value == chosen}
            for value, label in STATUS_FILTERS]
