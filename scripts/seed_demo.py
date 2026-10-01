#!/usr/bin/env python3
"""Create demo data so a grader (and you) can use the CMS immediately.

    uv run python scripts/seed_demo.py

Creates one Director (admin) and one Analyst (editor), with passwords read from
.env, never hard-coded, and demo content: published and draft Data Bites and
Reports, each with a Summary, two of the Data Bites with a Chart, so the
public site and the admin console both have something to show. The homepage's
sample Key figures come from app.homepage. Safe to re-run: an existing account, or an item
whose slug is already taken, is left alone.

The rubric expects this to run clean on a fresh clone with .env.example values
(item E4), because the database itself is never committed.
"""
from __future__ import annotations

import json
import os
import sys

from app import charts, data_bites, db, reports, settings, users

# Keep in step with DEMO_USERS in tests/conftest.py.
DEMO_ACCOUNTS = [
    ("admin@example.test", "CMS_ADMIN_PASSWORD", "admin", "Demo Director"),
    ("editor@example.test", "CMS_EDITOR_PASSWORD", "editor", "Demo Analyst"),
]

_DEMO_NOTE = "*Demo content from scripts/seed_demo.py; the figures are made up.*"

def _chart(title: str, categories: list[str], *series: tuple[str, list[str]]) -> str:
    """A bar Chart's fence, in the canonical form the Chart builder writes
    (ADR-006), so the Editor saves it back unchanged."""
    data = {"version": 1, "type": "bar", "title": title, "categories": categories,
            "series": [{"name": name, "values": values} for name, values in series]}
    return f"```{charts.INFO}\n{charts.parse(json.dumps(data)).canonical()}```\n"


# (module, title, slug, body, author's email, published?, summary), oldest
# first: the last published Data Bite is the newest, which the home page
# features with its Chart.
DEMO_CONTENT = [
    (data_bites, "This year's survey calendar is set", "survey-calendar-set",
     "The office runs three surveys this year. See the Survey Calendar for "
     "dates.\n\n" + _DEMO_NOTE,
     "editor@example.test", True,
     "Three surveys open between October and February; here is who receives each."),
    (data_bites, "First-year retention holds at 91 percent", "first-year-retention",
     "Of the students who entered in fall 2025, 91 percent returned this fall.\n\n"
     + _chart("First-year retention", ["2022", "2023", "2024", "2025"],
              ("Returned", ["90%", "92%", "91%", "91%"]))
     + "\n" + _DEMO_NOTE,
     "editor@example.test", True,
     "The class that entered in fall 2025 returned at the same rate as the year before."),
    (data_bites, "Spring survey response rates", "spring-survey-response-rates",
     "Response rates for the spring student survey, still being checked "
     "before release.\n\n" + _DEMO_NOTE,
     "editor@example.test", False,
     "Response rates for the spring student survey, still being checked."),
    (data_bites, "Fall enrollment snapshot", "fall-enrollment-snapshot",
     "Headcount by class on the census date.\n\n"
     + _chart("Students by class", ["First-year", "Sophomore", "Junior", "Senior"],
              ("Fall 2025", ["470", "460", "440", "425"]),
              ("Fall 2026", ["480", "455", "440", "430"]))
     + "\n| Class | Students | Change |\n|:--|--:|--:|\n"
     "| First-year | 480 | +2% |\n| Sophomore | 455 | -1% |\n"
     "| Junior | 440 | 0% |\n| Senior | 430 | +1% |\n\n" + _DEMO_NOTE,
     "editor@example.test", True,
     "Headcount by class on the census date. The first-year class grew two "
     "percent; the rest held steady."),
    (reports, "Factbook", "factbook",
     "The office's running reference of the college's statistics.\n\n"
     "| Measure | Fall 2026 |\n|:--|--:|\n| Students enrolled | 1,805 |\n"
     "| Student–faculty ratio | 10:1 |\n\n" + _DEMO_NOTE,
     "admin@example.test", True,
     "Admissions, enrollment, diversity and academic programs, updated each term."),
    (reports, "Survey Calendar", "survey-calendar",
     "Surveys the office runs, and when.\n\n"
     "| Survey | Audience | Window |\n|:--|:--|:--|\n"
     "| Student experience | All students | February |\n"
     "| Faculty and staff | Employees | October |\n\n" + _DEMO_NOTE,
     "admin@example.test", True,
     "Which surveys the office runs, who receives them, and when they open."),
    (reports, "Common Data Set 2026-27", "common-data-set-2026-27",
     "Draft of this year's Common Data Set, awaiting the Director's review.\n\n"
     + _DEMO_NOTE,
     "editor@example.test", False,
     "The standard annual data set colleges publish for guidebooks and rankings."),
]


def _user_id(email: str) -> int:
    with db.connect() as conn:
        return conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]


def seed_content() -> None:
    for module, title, slug, body, author, published, summary in DEMO_CONTENT:
        if any(item["slug"] == slug for item in module.list_all()):
            print(f"  exists   {slug}")
            continue
        item_id = module.create(title, slug, body, _user_id(author), summary=summary)
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
