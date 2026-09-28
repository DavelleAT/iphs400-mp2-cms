"""Reports: durable, cite-able Markdown documents (the Factbook, the CDS).

Any Analyst or Director may create a Report (always as a draft) and edit a
draft one, whoever started it (shift continuity, ADR-003). Once a Report is
published only a Director may change it: `update` enforces that in the same
statement that writes, and the routes make publish, unpublish, and delete
Director only. Editing never changes the author or created_at.

Public-facing code reads Reports only through `list_published`, so a draft
cannot leak through it.
"""
from __future__ import annotations

import sqlite3

from app.content import ContentError, ContentTable
from app.users import is_director

_TABLE = ContentTable("reports", "Report")

create = _TABLE.create
get = _TABLE.get
list_all = _TABLE.list_all
set_status = _TABLE.set_status
delete = _TABLE.delete


class ReportLocked(ContentError):
    """A published Report, and the user is not a Director."""


def can_edit(report: sqlite3.Row, user: sqlite3.Row) -> bool:
    """The lockdown rule. `update` applies the same rule in its UPDATE."""
    return report["status"] == "draft" or is_director(user)


def update(report_id: int, title: str, slug: str, body: str, *,
           user: sqlite3.Row) -> bool:
    """Edit title, slug, and body on behalf of `user`. False if there is no
    such Report; ReportLocked if it is published and `user` is not a Director."""
    if _TABLE.update(report_id, title, slug, body, drafts_only=not is_director(user)):
        return True
    if get(report_id) is not None:
        raise ReportLocked("Only the Director can edit a published Report.")
    return False


def list_published() -> list[sqlite3.Row]:
    """The public-facing query: published Reports only, by title."""
    return _TABLE.list_published("c.title, c.id")
