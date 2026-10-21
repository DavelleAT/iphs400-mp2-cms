# ADR-008: Accounts are deactivated, never deleted

**Status:** accepted (built in T02, issue #3; recorded for MP2plus P3)
**Date:** 2026-10-21

## Context

Interns rotate every semester, so Analyst accounts come and go several times a
year. Every Data Bite and Report stores its author as
`author_id INTEGER NOT NULL REFERENCES users (id)` (`app/db.py`), and the
Director answers to the board and accreditors for who wrote what. An account
that leaves must lose access at once without erasing who wrote the published
work.

## Decision

The Director can **deactivate** an account (`users.deactivate`, the
Deactivate button on the Users page). It sets `is_active = 0`: the account
can no longer log in, and its open sessions end on their next request, because
every protected request reloads the user (`auth.signed_in_user`). The row stays,
so every item keeps its author. There is no delete.

Options rejected:
- **Hard delete.** Breaks `author_id` for every item the intern wrote, or
  forces the item to be deleted with them. Lost authorship can't be recovered.
- **Delete and reassign the content to the Director.** Keeps the foreign key
  valid, but records the wrong author on historical Reports.

## Consequences

- Authorship history is never lost: a Report from three semesters ago still
  names the intern who drafted it.
- The users table only grows. A few rows per semester is nothing for SQLite.
- A deactivated email stays taken. Bringing an intern back means reactivating
  their row, which is not built yet, not creating a new one.
- This is hard to reverse: once rows are deleted, their authorship is gone.
