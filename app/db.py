"""SQLite access. Every content table's schema lives here, and init_db() builds
them all, with the homepage settings' one-row table (app.homepage)."""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from app import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('admin', 'editor')),
    password_hash TEXT    NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS data_bites (
    id         INTEGER PRIMARY KEY,
    title      TEXT    NOT NULL,
    slug       TEXT    NOT NULL UNIQUE,
    body       TEXT    NOT NULL,  -- raw Markdown; sanitized only when rendered
    status     TEXT    NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    author_id  INTEGER NOT NULL REFERENCES users (id),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now')),
    ref        TEXT    -- what a site link names it by (app.site_links); never changes
);

CREATE TABLE IF NOT EXISTS reports (
    id         INTEGER PRIMARY KEY,
    title      TEXT    NOT NULL,
    slug       TEXT    NOT NULL UNIQUE,  -- unique among Reports only; a Data Bite may share it
    body       TEXT    NOT NULL,  -- raw Markdown; sanitized only when rendered
    status     TEXT    NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    author_id  INTEGER NOT NULL REFERENCES users (id),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now')),
    file_name  TEXT,   -- the attached PDF's sanitized name for display; NULL if none
    ref        TEXT    -- what a site link names it by (app.site_links); never changes
);

-- The ref of each deleted Data Bite and Report (kind: "data-bite" or
-- "report"), so a link to one reads as deleted, and no new item reuses it.
CREATE TABLE IF NOT EXISTS deleted_refs (
    ref        TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    deleted_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

# Columns added after a table was first created: (table, column, definition).
# CREATE TABLE IF NOT EXISTS leaves an existing table alone, so init_db adds
# any of these an older database is missing.
ADDED_COLUMNS = [
    ("reports", "file_name", "TEXT"),
    ("data_bites", "ref", "TEXT"),
    ("reports", "ref", "TEXT"),
    # A Summary: plain text, at most 200 characters (app.content).
    ("data_bites", "summary", "TEXT NOT NULL DEFAULT ''"),
    ("reports", "summary", "TEXT NOT NULL DEFAULT ''"),
]
# The tables whose rows have a ref. Built after ADDED_COLUMNS, which may add
# the column: a unique index, and a trigger that keeps a ref from changing
# once set.
_REF_TABLES = ("data_bites", "reports")
_REF_RULES = """
CREATE UNIQUE INDEX IF NOT EXISTS {table}_ref ON {table} (ref);
CREATE TRIGGER IF NOT EXISTS {table}_ref_fixed BEFORE UPDATE OF ref ON {table}
    WHEN OLD.ref IS NOT NULL AND NEW.ref IS NOT OLD.ref
    BEGIN SELECT RAISE(ABORT, 'a ref never changes'); END;
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open the database named by settings (read at call time, so tests can swap
    it). Commits on success, rolls back on error, always closes."""
    conn = sqlite3.connect(settings.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    # Imported here: these read the database through this module.
    from app import homepage, site_links

    with connect() as conn:
        conn.executescript(SCHEMA)
        homepage.seed(conn)
        for table, column, definition in ADDED_COLUMNS:
            existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        for table in _REF_TABLES:
            conn.executescript(_REF_RULES.format(table=table))
            # Rows made before refs existed get one now.
            for (row_id,) in conn.execute(
                    f"SELECT id FROM {table} WHERE ref IS NULL").fetchall():
                conn.execute(f"UPDATE {table} SET ref = ? WHERE id = ?",
                             (site_links.new_ref(conn), row_id))
