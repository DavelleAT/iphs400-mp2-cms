"""Data Bites: short, dated Markdown items.

Any Analyst or Director may create, edit, publish, and unpublish any Data Bite
(shift continuity, ADR-003); only a Director may delete one, which the routes
enforce. Editing never changes the author or created_at.

Public-facing code reads Data Bites only through `list_published`, so a draft
cannot leak through it.
"""
from __future__ import annotations

import sqlite3

from app.content import ContentTable

_TABLE = ContentTable("data_bites", "Data Bite")

create = _TABLE.create
get = _TABLE.get
list_all = _TABLE.list_all
set_status = _TABLE.set_status
delete = _TABLE.delete


def update(bite_id: int, title: str, slug: str, body: str) -> bool:
    """Edit title, slug, and body. False if there is no such Data Bite."""
    return _TABLE.update(bite_id, title, slug, body)


def list_published() -> list[sqlite3.Row]:
    """The public-facing query: published Data Bites only, newest first."""
    return _TABLE.list_published("c.created_at DESC, c.id DESC")
