"""What Data Bites and Reports share: the title/slug/Markdown-body fields, their
validation, the draft/published status, and the table-level reads and writes.

Each content type keeps its own table, so a slug is unique within a type but a
Data Bite and a Report may share one (spec #1, "Publish gate & export paths":
exports are namespaced by type). Who may do what is decided by each type's own
module and routes, not here.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from app import db, site_links

STATUS_LABELS = {"draft": "Draft", "published": "Published"}
# Runs inside the transaction that wrote an item's row, given the connection and
# the item's id; if it raises, the row's change is rolled back with it.
AlsoWrite = Callable[[sqlite3.Connection, int], None]
_SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
# A slug names its item's page, <type folder>/<slug>.html, on the public site;
# <type folder>/index.html is taken by the type's list page.
_RESERVED_SLUGS = {"index"}


class ContentError(ValueError):
    """Content broke a rule; the message is safe to show."""


class DuplicateSlug(ContentError):
    pass


STALE = "This item changed since you opened it. Reload to see the latest version."


class StaleItem(ContentError):
    """Saved from an edit form opened on an older version of the item."""


def item_base(title: str, slug: str, body: str) -> str:
    """The version of an item an edit form was opened on: a hash of its
    stored title, slug, and body, all three of which the form saves. A hash
    of the body alone would let a stale form overwrite a newer title or slug."""
    return hashlib.sha256(json.dumps([title, slug, body]).encode()).hexdigest()


def validate(title: str, slug: str, body: str) -> tuple[str, str, str]:
    title, slug = title.strip(), slug.strip()
    if not title:
        raise ContentError("Enter a title.")
    if not _SLUG_PATTERN.fullmatch(slug):
        raise ContentError("Slugs use lowercase letters, digits, and single "
                           "hyphens, e.g. fall-enrollment.")
    if slug in _RESERVED_SLUGS:
        raise ContentError(f"The slug {slug} is reserved for the list page; "
                           "choose another.")
    if not body.strip():
        raise ContentError("Enter a body.")
    return title, slug, body


@dataclass(frozen=True)
class ContentTable:
    """One content type's table. `table` is a fixed identifier from this
    codebase, never user input."""
    table: str  # e.g. "reports"
    noun: str   # e.g. "Report", for messages
    kind: str   # e.g. "report", its site links' scheme (app.site_links)

    def _select(self, where: str, order: str, params: tuple = ()) -> list[sqlite3.Row]:
        with db.connect() as conn:
            return conn.execute(
                f"SELECT c.*, u.name AS author_name FROM {self.table} c"
                f" JOIN users u ON u.id = c.author_id WHERE {where} ORDER BY {order}",
                params,
            ).fetchall()

    def _duplicate_slug_error(self, exc: sqlite3.IntegrityError, slug: str) -> DuplicateSlug:
        """Translate the slug's UNIQUE violation; re-raise any other constraint."""
        if f"{self.table}.slug" not in str(exc):
            raise exc
        return DuplicateSlug(f"Another {self.noun} already uses the slug {slug}.")

    def create(self, title: str, slug: str, body: str, author_id: int, *,
               also: AlsoWrite | None = None) -> int:
        """Create a draft, with a new ref."""
        title, slug, body = validate(title, slug, body)
        try:
            with db.connect() as conn:
                # Held from choosing the ref to storing it (site_links.new_ref).
                conn.execute("BEGIN IMMEDIATE")
                item_id = conn.execute(
                    f"INSERT INTO {self.table} (title, slug, body, author_id, ref)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (title, slug, body, author_id, site_links.new_ref(conn)),
                ).lastrowid
                if also:
                    also(conn, item_id)
        except sqlite3.IntegrityError as exc:
            raise self._duplicate_slug_error(exc, slug) from None
        return item_id

    def update(self, item_id: int, title: str, slug: str, body: str, *,
               drafts_only: bool = False, also: AlsoWrite | None = None,
               base: str | None = None) -> bool:
        """Edit title, slug, and body. The author, created_at, and status are
        kept. With drafts_only, a published item is left alone. With `base`,
        the item_base the edit form was opened on, StaleItem if the item has
        changed since, and nothing is written. False if nothing was changed."""
        title, slug, body = validate(title, slug, body)
        try:
            with db.connect() as conn:
                if base is not None:
                    # Held from the check to the write, so no other save
                    # lands between them.
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute(f"SELECT title, slug, body FROM {self.table}"
                                       " WHERE id = ?", (item_id,)).fetchone()
                    if row is not None and item_base(*row) != base:
                        raise StaleItem(STALE)
                changed = conn.execute(
                    f"UPDATE {self.table} SET title = ?, slug = ?, body = ?,"
                    " updated_at = datetime('now')"
                    " WHERE id = ? AND (status = 'draft' OR NOT ?)",
                    (title, slug, body, item_id, drafts_only),
                ).rowcount == 1
                if changed and also:
                    also(conn, item_id)
                return changed
        except sqlite3.IntegrityError as exc:
            raise self._duplicate_slug_error(exc, slug) from None

    def touch(self, item_id: int, *, drafts_only: bool = False,
              also: AlsoWrite | None = None) -> bool:
        """Mark the item as changed now, for a change outside its row (e.g.
        its images), made by `also` in the same transaction. With drafts_only,
        a published item is left alone, as `update`. False if nothing was
        changed."""
        with db.connect() as conn:
            changed = conn.execute(
                f"UPDATE {self.table} SET updated_at = datetime('now')"
                " WHERE id = ? AND (status = 'draft' OR NOT ?)",
                (item_id, drafts_only),
            ).rowcount == 1
            if changed and also:
                also(conn, item_id)
            return changed

    def get(self, item_id: int) -> sqlite3.Row | None:
        rows = self._select("c.id = ?", "c.id", (item_id,))
        return rows[0] if rows else None

    def list_all(self, status: str | None = None) -> list[sqlite3.Row]:
        """Every item, or only those in `status`; most recently updated first."""
        where, params = ("1", ()) if status is None else ("c.status = ?", (status,))
        return self._select(where, "c.updated_at DESC, c.id DESC", params)

    def count_by_status(self) -> dict[str, int]:
        """How many items are in each status, zero included, e.g.
        {"draft": 2, "published": 0}."""
        with db.connect() as conn:
            rows = conn.execute(
                f"SELECT status, COUNT(*) FROM {self.table} GROUP BY status").fetchall()
        return {**dict.fromkeys(STATUS_LABELS, 0), **dict(rows)}

    def list_published(self, order: str) -> list[sqlite3.Row]:
        return self._select("c.status = 'published'", order)

    def get_published(self, slug: str) -> sqlite3.Row | None:
        """The published item with this slug; None for a draft or no such item."""
        rows = self._select("c.status = 'published' AND c.slug = ?", "c.id", (slug,))
        return rows[0] if rows else None

    def set_status(self, item_id: int, status: str) -> bool:
        """Publish or unpublish. False if there is no such item."""
        with db.connect() as conn:
            return conn.execute(
                f"UPDATE {self.table} SET status = ?, updated_at = datetime('now')"
                " WHERE id = ?",
                (status, item_id),
            ).rowcount == 1

    def delete(self, item_id: int) -> bool:
        """Delete the item, leaving its ref's tombstone. False if there is no
        such item."""
        with db.connect() as conn:
            site_links.tombstone(conn, self.kind, item_id)
            return conn.execute(
                f"DELETE FROM {self.table} WHERE id = ?", (item_id,)).rowcount == 1
