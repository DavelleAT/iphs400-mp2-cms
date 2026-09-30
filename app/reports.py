"""Reports: durable, cite-able Markdown documents (the Factbook, the CDS).

Any Analyst or Director may create a Report (always as a draft) and edit a
draft one, whoever started it (shift continuity, ADR-003). Once a Report is
published only a Director may change it: `update` enforces that in the same
statement that writes, and the routes make publish, unpublish, and delete
Director only. Editing never changes the author or created_at.

A Report may carry one attached PDF (checked by app.uploads). Attaching,
replacing, or removing it follows the same lockdown as the body. The file is
stored under settings.UPLOADS, outside site/, named by the Report's id; the
`file_name` column says whether there is one.

A Report may also carry chart images (app.chart_images, ADR-004), stored apart
from its PDF, so that changing one never touches the other. Adding or
removing an image follows the same lockdown again. Deleting a Report deletes
its file and its images.

Public-facing code reads Reports only through `list_published` and
`get_published`, so a draft cannot leak through it.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app import chart_images, db, settings
from app.content import AlsoWrite, ContentError, ContentTable
from app.uploads import Pdf, write_atomically
from app.users import is_director

_TABLE = ContentTable("reports", "Report")
_IMAGES = "reports"  # the chart_images kind
LOCKED = "Only the Director can change a published Report."

get = _TABLE.get
list_all = _TABLE.list_all
count_by_status = _TABLE.count_by_status
set_status = _TABLE.set_status
get_published = _TABLE.get_published


class ReportLocked(ContentError):
    """A published Report, and the user is not a Director."""


def can_edit(report: sqlite3.Row, user: sqlite3.Row) -> bool:
    """The lockdown rule. `update`, `remove_file`, `add_image`, and
    `remove_image` apply the same rule in their UPDATEs."""
    return report["status"] == "draft" or is_director(user)


def file_path(report_id: int) -> Path:
    """Where a Report's attached file is stored. Built from the id alone."""
    return settings.UPLOADS / "reports" / f"{int(report_id)}.pdf"


def _attaching(pdf: Pdf | None) -> AlsoWrite | None:
    """Attach `pdf` in the same transaction as the Report's row, so the body
    and the file are saved together or not at all."""
    if pdf is None:
        return None

    def attach(conn: sqlite3.Connection, report_id: int) -> None:
        conn.execute("UPDATE reports SET file_name = ? WHERE id = ?", (pdf.name, report_id))
        write_atomically(file_path(report_id), pdf.data)

    return attach


def _missing_or_locked(report_id: int) -> bool:
    """After a guarded write changed nothing: False if there is no such
    Report, otherwise it was published and locked."""
    if get(report_id) is None:
        return False
    raise ReportLocked(LOCKED)


def create(title: str, slug: str, body: str, author_id: int, *,
           pdf: Pdf | None = None) -> int:
    """Create a draft Report, with its file if one is given. It starts with no
    images, even if a deleted Report that had its id left some behind (SQLite
    may reuse the highest id)."""
    attach = _attaching(pdf)

    def clear_images_then_attach(conn: sqlite3.Connection, report_id: int) -> None:
        chart_images.remove_all(_IMAGES, report_id)
        if attach:
            attach(conn, report_id)

    return _TABLE.create(title, slug, body, author_id, also=clear_images_then_attach)


def update(report_id: int, title: str, slug: str, body: str, *,
           user: sqlite3.Row, pdf: Pdf | None = None, base: str | None = None) -> bool:
    """Edit title, slug, and body on behalf of `user`, and attach or replace
    the file if one is given. False if there is no such Report; ReportLocked if
    it is published and `user` is not a Director; StaleItem if it has changed
    since `base` (ContentTable.update)."""
    if _TABLE.update(report_id, title, slug, body, drafts_only=not is_director(user),
                     also=_attaching(pdf), base=base):
        return True
    return _missing_or_locked(report_id)


def remove_file(report_id: int, *, user: sqlite3.Row) -> bool:
    """Remove the Report's file on behalf of `user`, as `update`."""
    with db.connect() as conn:
        removed = conn.execute(
            "UPDATE reports SET file_name = NULL, updated_at = datetime('now')"
            " WHERE id = ? AND (status = 'draft' OR ?)",
            (report_id, is_director(user)),
        ).rowcount == 1
    if not removed:
        return _missing_or_locked(report_id)
    # Only once the row no longer names it, so a failed commit keeps the file.
    file_path(report_id).unlink(missing_ok=True)
    return True


def images(report_id: int) -> dict[str, Path]:
    """The Report's chart images, {name: where it is stored}, by name."""
    return chart_images.stored(_IMAGES, report_id)


def add_image(report_id: int, image: chart_images.Image, *, user: sqlite3.Row) -> bool:
    """Add a chart image on behalf of `user`, or replace the one of the same
    name. False if there is no such Report; ReportLocked as `update`;
    ContentError if it already has the most allowed."""
    if _TABLE.touch(report_id, drafts_only=not is_director(user),
                    also=lambda conn, item_id: chart_images.save(_IMAGES, item_id, image)):
        return True
    return _missing_or_locked(report_id)


def remove_image(report_id: int, name: str, *, user: sqlite3.Row) -> bool:
    """Remove a chart image on behalf of `user`. False if there is no such
    Report or it has no image of that name; ReportLocked as `update`."""
    if name not in images(report_id):
        return False
    if _TABLE.touch(report_id, drafts_only=not is_director(user),
                    also=lambda conn, item_id: chart_images.remove(_IMAGES, item_id, name)):
        return True
    return _missing_or_locked(report_id)


def delete(report_id: int) -> bool:
    """Delete the Report, its file, and its images. False if there is no such
    Report."""
    if not _TABLE.delete(report_id):
        return False
    file_path(report_id).unlink(missing_ok=True)
    chart_images.remove_all(_IMAGES, report_id)
    return True


def list_published() -> list[sqlite3.Row]:
    """The public-facing query: published Reports only, by title."""
    return _TABLE.list_published("c.title, c.id")
