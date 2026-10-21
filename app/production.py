"""Production configuration (F9; ADR-001: an admin password from the
environment, no default accounts).

With CMS_ENV=production the console refuses to start on settings that are only
safe on a laptop: a missing or well-known secret key (anyone who knows it can
forge a session cookie), or a missing or well-known Director password. It
never creates the demo accounts; it creates one Director from CMS_ADMIN_EMAIL
and CMS_ADMIN_PASSWORD when the database has none. Development is unchanged.

Every function takes the environment as a mapping, so tests pass a dict and
never touch the real one.
"""
from __future__ import annotations

from collections.abc import Mapping

from app import settings, users


class UnsafeConfig(Exception):
    """The production configuration is unsafe; the message names each variable."""


def is_production(env: Mapping[str, str]) -> bool:
    return env.get("CMS_ENV", "development").strip().lower() == "production"


def example_values() -> dict[str, str]:
    """The values .env.example ships with: public, so never safe in production."""
    values = {}
    for line in (settings.ROOT / ".env.example").read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.strip().startswith("#"):
            values[key.strip()] = value.strip().strip("'\"")
    return values


def problems(env: Mapping[str, str]) -> list[str]:
    """What makes this configuration unsafe for production: one line per
    problem, each naming its variable. Empty outside production."""
    if not is_production(env):
        return []
    example = example_values()
    found = []

    secret = env.get("CMS_SECRET_KEY", "").strip()
    if not secret:
        found.append("CMS_SECRET_KEY is unset.")
    elif secret in (settings.DEV_SECRET_KEY, example.get("CMS_SECRET_KEY")):
        found.append("CMS_SECRET_KEY is a published default; set a long random value.")

    if not env.get("CMS_ADMIN_EMAIL", "").strip():
        found.append("CMS_ADMIN_EMAIL is unset.")

    password = env.get("CMS_ADMIN_PASSWORD", "")
    if not password:
        found.append("CMS_ADMIN_PASSWORD is unset.")
    elif password == example.get("CMS_ADMIN_PASSWORD"):
        found.append("CMS_ADMIN_PASSWORD is the .env.example value; choose a new one.")
    elif len(password) < users.MIN_PASSWORD_LENGTH:
        found.append(f"CMS_ADMIN_PASSWORD must be at least "
                     f"{users.MIN_PASSWORD_LENGTH} characters.")
    return found


def check(env: Mapping[str, str]) -> None:
    """Raise UnsafeConfig listing every problem, or return quietly."""
    found = problems(env)
    if found:
        raise UnsafeConfig("Refusing to start with CMS_ENV=production:\n  "
                           + "\n  ".join(found))


def ensure_director(env: Mapping[str, str]) -> None:
    """In production, create the Director from the environment if the database
    has none. Call after db.init_db()."""
    if not is_production(env) or users.has_director():
        return
    try:
        users.create_user(env["CMS_ADMIN_EMAIL"], env["CMS_ADMIN_PASSWORD"],
                          "admin", name="Director")
    except users.UserError as exc:
        raise UnsafeConfig(f"CMS_ADMIN_EMAIL / CMS_ADMIN_PASSWORD: {exc}") from None
