# CLAUDE.md — standing instructions

Keep this file short. It is prepended to every turn, so every line costs context
on every message. Add a rule only after you have had to correct the same thing
twice.

## What this repo is

A small web CMS for IPHS 400 Mini-Project #2. A local admin console
(FastAPI + Jinja + SQLite) writes content; `cms publish` renders the published
content into `site/` as static HTML, which is deployed to GitHub Pages. The
admin console never goes on the public internet.

## Hard constraints

- Published HTML uses **relative** paths only. Never `href="/..."` or `src="/..."`.
- Never commit `.env`, `*.db`, keys, or tokens. Read secrets from the environment.
- Passwords are hashed with argon2. Never store or log a plain password.
- Every state-changing form carries a CSRF token.
- User-written Markdown is sanitized before it is rendered anywhere.
- `site/` is generated. Never edit it by hand.
- Only published content reaches `site/`. Drafts never leave the database.

## How to work with me

- One ticket per session. Read the ticket issue, the spec issue, and `CONTEXT.md`
  before writing code.
- Write the ticket id into `.claude/state/phase` when a stage starts
  (`grill`, `spec`, `tickets`, or `T03`), so the usage ledger is labelled.
- Use the vocabulary in `CONTEXT.md`. If a better word appears, update the
  glossary rather than using both.
- When `/status` shows a non-Anthropic base URL, add a `Backend: <provider> <model>`
  trailer to every commit made in that session.
- Before a commit that closes a ticket: post the `/code-review` findings, and how
  each was resolved, as a comment on that issue. Then commit with a message that
  starts `T0N:` and ends `Closes #N`.
- Ask before adding a dependency. The stack in `pyproject.toml` is fixed for this
  project.
