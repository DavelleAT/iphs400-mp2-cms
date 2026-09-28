"""User accounts: creation, lookup, and password checks.

Roles are stored as `admin` / `editor` and shown as Director / Analyst.
Passwords only ever exist here as argon2 hashes.
"""
from __future__ import annotations

import re
import sqlite3

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app import db

ROLE_LABELS = {"admin": "Director", "editor": "Analyst"}
MIN_PASSWORD_LENGTH = 8
_EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

_hasher = PasswordHasher()
# Verified against when the email is unknown, so a miss costs the same time as
# a wrong password and response timing does not reveal which accounts exist.
_DUMMY_HASH = _hasher.hash("not-a-real-password")


class UserError(ValueError):
    """A user-management request broke a rule; the message is safe to show."""


class DuplicateEmail(UserError):
    pass


def is_director(user: sqlite3.Row) -> bool:
    return user["role"] == "admin"


def _check_role(role: str) -> None:
    if role not in ROLE_LABELS:
        raise UserError(f"Choose a role: {' or '.join(ROLE_LABELS.values())}.")


def create_user(email: str, password: str, role: str, name: str | None = None) -> int:
    """Create an active user. `name` defaults to the email's local part."""
    email = email.strip()
    if not _EMAIL_PATTERN.fullmatch(email):
        raise UserError("Enter a valid email address.")
    if name is not None and not name.strip():
        raise UserError("Enter a name.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise UserError(f"Passwords must be at least {MIN_PASSWORD_LENGTH} characters.")
    _check_role(role)
    try:
        with db.connect() as conn:
            cursor = conn.execute(
                "INSERT INTO users (email, name, role, password_hash) VALUES (?, ?, ?, ?)",
                (email, (name or email.split("@")[0]).strip(), role,
                 _hasher.hash(password)),
            )
    except sqlite3.IntegrityError:
        raise DuplicateEmail(f"{email} already has an account.") from None
    return cursor.lastrowid


def set_role(user_id: int, role: str) -> bool:
    """Change a user's role. False if there is no such user. Takes effect on the
    user's next request, since sessions re-load the user every time."""
    _check_role(role)
    with db.connect() as conn:
        return conn.execute("UPDATE users SET role = ? WHERE id = ?",
                            (role, user_id)).rowcount == 1


def deactivate(user_id: int) -> bool:
    """Block a user from logging in and end their open sessions. The row is
    kept so their content stays attributed. False if there is no such user."""
    with db.connect() as conn:
        return conn.execute("UPDATE users SET is_active = 0 WHERE id = ?",
                            (user_id,)).rowcount == 1


def list_users() -> list[sqlite3.Row]:
    with db.connect() as conn:
        return conn.execute(
            "SELECT id, email, name, role, is_active FROM users"
            " ORDER BY is_active DESC, name COLLATE NOCASE"
        ).fetchall()


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
