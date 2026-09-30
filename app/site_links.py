"""Site links: a link in a body to another Data Bite or Report (spec #14,
"Links").

A link names its target by a *site reference*, `data-bite:<ref>` or
`report:<ref>`, never by title, slug, or id: a title or slug may be edited,
and SQLite may give a deleted item's id to a new one. Each item's `ref` is 32
random hex characters, set when it is created and never changed (a trigger in
app.db enforces it) or reused: deleting an item leaves its ref in
`deleted_refs`, and a new ref is checked against both tables and that one.

A site reference is resolved when a page is rendered (app.public_site), like
a chart image's `image:<name>`, so a link follows its target's slug, and only
a published target is linked.
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from collections.abc import Iterable

from app import db

# kind -> its table. The kind is also the site reference's scheme.
TABLES = {"data-bite": "data_bites", "report": "reports"}
REFERENCE = re.compile(rf"(?<![\w:-])({'|'.join(TABLES)}):([0-9a-f]{{32}})(?![\w-])")
# How many fresh refs to try before giving up.
_ATTEMPTS = 3

# What a site reference names, besides a published item: a draft, a deleted
# item, or nothing that ever existed.
PUBLISHED, DRAFT, DELETED, UNKNOWN = "published", "draft", "deleted", "unknown"


class RefCollision(RuntimeError):
    """Every fresh ref tried was taken: the generator is broken."""


def reference(kind: str, ref: str) -> str:
    return f"{kind}:{ref}"


def _generate() -> str:
    return secrets.token_hex(16)


def _taken(conn: sqlite3.Connection, ref: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM data_bites WHERE ref = ?1 UNION ALL"
        " SELECT 1 FROM reports WHERE ref = ?1 UNION ALL"
        " SELECT 1 FROM deleted_refs WHERE ref = ?1", (ref,)).fetchone() is not None


def new_ref(conn: sqlite3.Connection) -> str:
    """A ref no item has, and no deleted item had. Run it in the
    transaction that stores it, holding the write lock (BEGIN IMMEDIATE), so
    that nothing else takes it in between. RefCollision after _ATTEMPTS."""
    for _ in range(_ATTEMPTS):
        ref = _generate()
        if not _taken(conn, ref):
            return ref
    raise RefCollision(f"No unused ref after {_ATTEMPTS} attempts.")


def tombstone(conn: sqlite3.Connection, kind: str, item_id: int) -> None:
    """Record the ref of the item about to be deleted, in the transaction
    that deletes it."""
    conn.execute(f"INSERT INTO deleted_refs (ref, kind) SELECT ref, ? FROM {TABLES[kind]}"
                 " WHERE id = ? AND ref IS NOT NULL", (kind, item_id))


def states(references: Iterable[str]) -> dict[str, str]:
    """What each site reference names: PUBLISHED, DRAFT, DELETED, or
    UNKNOWN (for anything not a well-formed one, too)."""
    found = {}
    with db.connect() as conn:
        for link in set(references):
            match = REFERENCE.fullmatch(link)
            if match is None:
                found[link] = UNKNOWN
                continue
            kind, ref = match.groups()
            row = conn.execute(f"SELECT status FROM {TABLES[kind]} WHERE ref = ?",
                               (ref,)).fetchone()
            if row is not None:
                found[link] = PUBLISHED if row["status"] == "published" else DRAFT
            elif conn.execute("SELECT 1 FROM deleted_refs WHERE ref = ? AND kind = ?",
                              (ref, kind)).fetchone():
                found[link] = DELETED
            else:
                found[link] = UNKNOWN
    return found


def state(link: str) -> str:
    return states([link])[link]


def in_body(body: str) -> set[str]:
    """The site references a body names."""
    return {match[0] for match in REFERENCE.finditer(body or "")}


# The Editor's link dialog.

NOUNS = {"report": "Report", "data-bite": "Data Bite"}


def choices() -> list[dict]:
    """Every Report, then every Data Bite, each by title, for the Editor's
    picker: {href: its site reference, title, kind: its noun, draft}."""
    found = []
    with db.connect() as conn:
        for kind in ("report", "data-bite"):
            found += [{"href": reference(kind, row["ref"]), "title": row["title"],
                       "kind": NOUNS[kind], "draft": row["status"] != "published"}
                      for row in conn.execute(f"SELECT ref, title, status FROM {TABLES[kind]}"
                                              " ORDER BY title, id")]
    return found


def unresolved(body: str) -> dict[str, str]:
    """The state of each site link in `body` that won't be a link on the
    site: DRAFT, DELETED, or UNKNOWN, for the Editor to mark."""
    return {link: found for link, found in states(in_body(body)).items()
            if found != PUBLISHED}


def linked_from(link: str) -> list[dict]:
    """Every other Report and Data Bite whose body names the site reference
    `link`, for the Director to see before deleting its target: {kind,
    noun, id, title}, Reports first, each by title."""
    found = []
    with db.connect() as conn:
        for kind in ("report", "data-bite"):
            found += [{"kind": kind, "noun": NOUNS[kind], "id": row["id"], "title": row["title"]}
                      for row in conn.execute(
                          f"SELECT id, title, body, ref FROM {TABLES[kind]}"
                          " WHERE instr(body, ?) ORDER BY title, id", (link,))
                      if reference(kind, row["ref"]) != link and link in in_body(row["body"])]
    return found
