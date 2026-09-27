# ADR-002: FastAPI + Jinja + SQLite, with no frontend framework

**Status:** accepted (set by the assignment)
**Date:** 2026-09-22

## Context

The project has to be readable by someone who has never built a web application,
gradable from a clean clone, and finishable in two weeks on a $20 plan. Options
considered: Django (batteries included, but a large amount of generated code to
read), Flask (similar to FastAPI here), a JavaScript stack (a second language and
a build step), and FastAPI with server-rendered templates.

## Decision

FastAPI with Jinja2 templates, SQLite for storage, argon2 for password hashing,
and an HTML sanitizer for user Markdown. No frontend framework, no build step.

## Consequences

- Every page is server-rendered, so "view source" shows what the code produced,
  which makes debugging visible.
- SQLite is a single file, so a grader can seed and inspect it easily. It is
  gitignored; `scripts/seed_demo.py` rebuilds it.
- No build step means the file you preview is the file that ships.
- Interactive flourishes (live preview without reload, drag-and-drop) cost more
  here than in a JavaScript stack. That is an accepted trade.
