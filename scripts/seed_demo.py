#!/usr/bin/env python3
"""Create demo data so a grader (and you) can use the CMS immediately.

    uv run python scripts/seed_demo.py

Creates one Director (admin) and one Analyst (editor), with passwords read from
.env, never hard-coded. Safe to re-run: existing accounts are left alone.
As content types land (T03+), extend this with demo Data Bites and Reports,
at least one draft and one published.

The rubric expects this to run clean on a fresh clone with .env.example values
(item E4), because the database itself is never committed.
"""
from __future__ import annotations

import os
import sys

from app import db, settings, users

# Keep in step with DEMO_USERS in tests/conftest.py.
DEMO_ACCOUNTS = [
    ("admin@example.test", "CMS_ADMIN_PASSWORD", "admin", "Demo Director"),
    ("editor@example.test", "CMS_EDITOR_PASSWORD", "editor", "Demo Analyst"),
]


def main() -> int:
    missing = [var for _, var, _, _ in DEMO_ACCOUNTS if not os.environ.get(var)]
    if missing:
        print(f"Set {' and '.join(missing)} in .env (copy .env.example).")
        return 1

    db.init_db()
    for email, var, role, name in DEMO_ACCOUNTS:
        try:
            users.create_user(email, os.environ[var], role, name=name)
        except users.DuplicateEmail:
            print(f"  exists   {email}")
        except users.UserError as exc:
            print(f"  {var}: {exc}")
            return 1
        else:
            print(f"  created  {email} ({users.ROLE_LABELS[role]})")
    print(f"Seeded {settings.DATABASE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
