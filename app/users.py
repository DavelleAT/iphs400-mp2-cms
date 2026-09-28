"""User accounts: creation, lookup, and password checks.

Roles are stored as `admin` / `editor` and shown as Director / Analyst.
Passwords only ever exist here as argon2 hashes.
"""
from __future__ import annotations

import sqlite3

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app import db

ROLE_LABELS = {"admin": "Director", "editor": "Analyst"}

_hasher = PasswordHasher()
# Verified against when the email is unknown, so a miss costs the same time as
# a wrong password and response timing does not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


def create_user(email: str, password: str, role: str, name: str | None = None) -> int:
    if role not in ROLE_LABELS:
        raise ValueError(f"unknown role {role!r}")
    with db.connect() as conn:
        cursor = conn.execute(
            "INSERT INTO users (email, name, role, password_hash) VALUES (?, ?, ?, ?)",
            (email.strip(), name or email.split("@")[0], role, _hasher.hash(password)),
        )
    return cursor.lastrowid


def get_active_user(user_id: int) -> sqlite3.Row | None:
    with db.connect() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,)
        ).fetchone()


def authenticate(email: str, password: str) -> sqlite3.Row | None:
    """Return the active user with these credentials, or None — never says why."""
    with db.connect() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.strip(),)
        ).fetchone()
    try:
        _hasher.verify(user["password_hash"] if user else _DUMMY_HASH, password)
    except (VerificationError, InvalidHashError):
        return None
    if user is None or not user["is_active"]:
        return None
    if _hasher.check_needs_rehash(user["password_hash"]):
        with db.connect() as conn:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                         (_hasher.hash(password), user["id"]))
    return user
