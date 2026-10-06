# IPHS 400 — Mini-Project #2 starter (Web CMS)

Click **Use this template** → name your repo **`iphs400-mp2-cms`** → make it **Public**.
Do not fork: a fork arrives without an Issues tab, and your tickets live in Issues.

## Live URL

https://davelleat.github.io/iphs400-mp2-cms/ — the public site, rebuilt with
`uv run cms publish && uv run cms deploy`.

## Start here

1. `docs/manual_iphs400_mp2-web-cms_20260922.md` — the manual. Read Part 0 and Part 1 first.
2. `docs/mp2-grading-rubric_20260922.md` — how you are graded. Read it **before** you build.
3. `docs/mp2-setup_context-threshold-hook_20260922.md` — Exercise A, in Part 4 of the manual.

## Run locally

```bash
uv sync
cp .env.example .env
git config core.hooksPath .githooks  # refuse to commit an unredacted transcript
uv run python scripts/seed_demo.py   # demo Director + Analyst (passwords from .env)
uv run cms serve        # then open http://localhost:8000/admin and log in as
                        # admin@example.test or editor@example.test
```

## What is here

```text
.claude/hooks/     the context meter and usage ledger (Exercise A lives in ctx_guard.py)
scripts/           usage_report.py (Exercise B lives in spend()), check_submission.py, seed_demo.py
tests/             the exercise tests, plus helpers such as client_as("editor")
app/, templates/   the T00 skeleton — every CMS feature is yours to build
docs/adr/          two example decision records
```

Two functions are deliberately unfinished and their tests fail until you write them:
`decide()` in `.claude/hooks/ctx_guard.py` and `spend()` in `scripts/usage_report.py`.
Both are graded. Use `/tdd`, as the manual says.

## Deadlines

Stage 1 (`mp2-mvp` tag): Tue Sep 29, 2:40 pm Eastern (soft target).
Stage 2 (`mp2-final` tag): Tue Oct 6, 2:40 pm Eastern, grace until Wed Oct 7, 2:40 pm.

Run `uv run python scripts/check_submission.py --stage 2` before you submit.

## Generative AI Use Statement

I used Claude Code throughout this project for planning, implementation, testing, code review, and design. Sonnet 5 helped with the first grill, specification, and ticket plan. Opus 5.5 handled most implementation and review sessions. I used OpenAI Codex based on GPT-5 for research support, the final rubric audit, and help organizing the report.

The main skills were `/grill-with-docs`, `/to-spec`, `/to-tickets`, `/implement`, `/tdd`, `/code-review`, and `/handoff`.

One prompt I used while reviewing the authoring specification was

> "Replace `body_base` with an item-level base hash covering at least `title`, `slug`, and `body`. The form saves all three, so a body-only hash could let a stale tab overwrite someone else's newer title or slug. Add a test for that conflict."

This changed stale-save protection so an old browser tab could not overwrite a newer title, slug, or body.

I also rejected an early visual direction with

> "its a bit too juvinile and AI-ey. lets be more creative and not dfall on the defaults."

I asked for a less generic design, later removed the bright green from the Chart palette, and requested a full Console redesign when the public site improved but the staff interface remained barebones.

The clearest model failure involved Analyst accounts. After the WordPress field trip, I changed the decision from a shared account to individual accounts. ADR-003 and the code used the new decision, but one old sentence in the specification still claimed individual accounts were out of scope. I caught the contradiction during submission review on September 29 and corrected the issue with an explanatory comment.

I checked AI output through acceptance criteria, tests, browser checks, and ticket reviews. The final suite has 1,540 passing tests. My token plan was completed late, and I have left that history unchanged rather than backdating it.

## Backends used


| Provider  | Model                | Use                                        |
| --------- | -------------------- | ------------------------------------------ |
| Anthropic | Sonnet 5             | Grill, specification, and ticket planning  |
| Anthropic | Opus 5.5             | Implementation, TDD, review, and design    |
| OpenAI    | Codex based on GPT-5 | Research, rubric audit, and report support |
