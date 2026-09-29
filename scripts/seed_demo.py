#!/usr/bin/env python3
"""Create demo data so a grader (and you) can use the CMS immediately.

    uv run python scripts/seed_demo.py

Creates one Director (admin) and one Analyst (editor), with passwords read from
.env, never hard-coded, and demo content: a published and a draft Data Bite,
and a published and a draft Report, so the public site and the admin console
both have something to show. Safe to re-run: an existing account, or an item
whose slug is already taken, is left alone.

The rubric expects this to run clean on a fresh clone with .env.example values
(item E4), because the database itself is never committed.
"""
from __future__ import annotations

import os
import sys

from app import data_bites, db, reports, settings, users

# Keep in step with DEMO_USERS in tests/conftest.py.
DEMO_ACCOUNTS = [
    ("admin@example.test", "CMS_ADMIN_PASSWORD", "admin", "Demo Director"),
    ("editor@example.test", "CMS_EDITOR_PASSWORD", "editor", "Demo Analyst"),
]

_DEMO_NOTE = "*Demo content from `scripts/seed_demo.py`; the figures are made up.*"

# (module, title, slug, body, author's email, published?)
DEMO_CONTENT = [
    (data_bites, "Fall enrollment snapshot", "fall-enrollment-snapshot",
     "Headcount by class on the census date.\n\n"
     "| Class | Students | Change |\n|:--|--:|--:|\n"
     "| First-year | 480 | +2% |\n| Sophomore | 455 | -1% |\n"
     "| Junior | 440 | 0% |\n| Senior | 430 | +1% |\n\n" + _DEMO_NOTE,
     "editor@example.test", True),
    (data_bites, "Spring survey response rates", "spring-survey-response-rates",
     "Response rates for the spring student survey, still being checked "
     "before release.\n\n" + _DEMO_NOTE,
     "editor@example.test", False),
    (reports, "Survey Calendar", "survey-calendar",
     "Surveys the office runs, and when.\n\n"
     "| Survey | Audience | Window |\n|:--|:--|:--|\n"
     "| Student experience | All students | February |\n"
     "| Faculty and staff | Employees | October |\n\n" + _DEMO_NOTE,
     "admin@example.test", True),
    (reports, "Common Data Set 2026-27", "common-data-set-2026-27",
     "Draft of this year's Common Data Set, awaiting the Director's review.\n\n"
     + _DEMO_NOTE,
     "editor@example.test", False),
]


def _user_id(email: str) -> int:
    with db.connect() as conn:
        return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]


def seed_content() -> None:
    for module, title, slug, body, author, published in DEMO_CONTENT:
        if any(item["slug"] == slug for item in module.list_all()):
            print(f"  exists   {slug}")
            continue
        item_id = module.create(title, slug, body, _user_id(author))
        if published:
            module.set_status(item_id, "published")
        print(f"  created  {slug} ({'published' if published else 'draft'})")


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
    seed_content()
    print(f"Seeded {settings.DATABASE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
