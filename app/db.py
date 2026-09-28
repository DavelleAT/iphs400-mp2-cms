"""SQLite access. Every table's schema lives here, so init_db() builds them all."""
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
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS reports (
    id         INTEGER PRIMARY KEY,
    title      TEXT    NOT NULL,
    slug       TEXT    NOT NULL UNIQUE,  -- unique among Reports only; a Data Bite may share it
    body       TEXT    NOT NULL,  -- raw Markdown; sanitized only when rendered
    status     TEXT    NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    author_id  INTEGER NOT NULL REFERENCES users (id),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
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
    with connect() as conn:
        conn.executescript(SCHEMA)
