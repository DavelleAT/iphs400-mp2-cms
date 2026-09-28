"""Data Bites: short, dated Markdown items.

Any Analyst or Director may create, edit, publish, and unpublish any Data Bite
(shift continuity, ADR-003); only a Director may delete one, which the routes
enforce. Editing never changes the author or created_at.

Public-facing code reads Data Bites only through `list_published`, so a draft
cannot leak through it.
"""
from __future__ import annotations

import re
import sqlite3

from app import db

STATUS_LABELS = {"draft": "Draft", "published": "Published"}
_SLUG_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SELECT = ("SELECT d.*, u.name AS author_name FROM data_bites d"
           " JOIN users u ON u.id = d.author_id")


class DataBiteError(ValueError):
    """A Data Bite broke a rule; the message is safe to show."""


class DuplicateSlug(DataBiteError):
    pass


def _validate(title: str, slug: str, body: str) -> tuple[str, str, str]:
    title, slug = title.strip(), slug.strip()
    if not title:
        raise DataBiteError("Enter a title.")
    if not _SLUG_PATTERN.fullmatch(slug):
        raise DataBiteError("Slugs use lowercase letters, digits, and single "
                            "hyphens, e.g. fall-enrollment.")
    if not body.strip():
        raise DataBiteError("Enter a body.")
    return title, slug, body


def _duplicate_slug_error(exc: sqlite3.IntegrityError, slug: str) -> DataBiteError:
    """Translate the slug's UNIQUE violation; re-raise any other constraint."""
    if "data_bites.slug" not in str(exc):
        raise exc
    return DuplicateSlug(f"Another Data Bite already uses the slug {slug}.")


def create(title: str, slug: str, body: str, author_id: int) -> int:
    """Create a draft Data Bite."""
    title, slug, body = _validate(title, slug, body)
    try:
        with db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO data_bites (title, slug, body, author_id) VALUES (?, ?, ?, ?)",
                (title, slug, body, author_id),
            )
    except sqlite3.IntegrityError as exc:
        raise _duplicate_slug_error(exc, slug) from None
    return cursor.lastrowid


def update(bite_id: int, title: str, slug: str, body: str) -> bool:
    """Edit title, slug, and body. The author, created_at, and status are kept.
    False if there is no such Data Bite."""
    title, slug, body = _validate(title, slug, body)
    try:
        with db.connect() as conn:
            return conn.execute(
                "UPDATE data_bites SET title = ?, slug = ?, body = ?,"
                " updated_at = datetime('now') WHERE id = ?",
                (title, slug, body, bite_id),
            ).rowcount == 1
    except sqlite3.IntegrityError as exc:
        raise _duplicate_slug_error(exc, slug) from None


def get(bite_id: int) -> sqlite3.Row | None:
    with db.connect() as conn:
        return conn.execute(f"{_SELECT} WHERE d.id = ?", (bite_id,)).fetchone()


def list_all() -> list[sqlite3.Row]:
    with db.connect() as conn:
        return conn.execute(f"{_SELECT} ORDER BY d.updated_at DESC, d.id DESC").fetchall()


def set_status(bite_id: int, status: str) -> bool:
    """Publish or unpublish. False if there is no such Data Bite."""
    with db.connect() as conn:
        return conn.execute(
            "UPDATE data_bites SET status = ?, updated_at = datetime('now') WHERE id = ?",
            (status, bite_id),
        ).rowcount == 1


def delete(bite_id: int) -> bool:
    """False if there is no such Data Bite."""
    with db.connect() as conn:
        return conn.execute("DELETE FROM data_bites WHERE id = ?", (bite_id,)).rowcount == 1


def list_published() -> list[sqlite3.Row]:
    """The public-facing query: published Data Bites only, newest first."""
    with db.connect() as conn:
        return conn.execute(
            f"{_SELECT} WHERE d.status = 'published' ORDER BY d.created_at DESC, d.id DESC"
        ).fetchall()
