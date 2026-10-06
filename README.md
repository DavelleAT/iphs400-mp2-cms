# Kenyon IR Office CMS — IPHS 400 Mini-Project #2

A small CMS for Kenyon College's Office of Institutional Research. Staff write
in a local Console (FastAPI, Jinja, SQLite); `cms publish` turns the published
content into a static site on GitHub Pages. The Console never goes online.

Two kinds of content, two roles. **Data Bites** are short updates an Analyst
can publish on their own. **Reports** are the durable documents people cite:
an Analyst can draft one, but only the Director publishes it, and published
Reports appear in the site's navigation. The Director also manages accounts
and the homepage. Writers use a document-style Editor with tables, Charts
built from pasted data, Chart images, and a Site preview of the public page.

## Live URL

https://davelleat.github.io/iphs400-mp2-cms/ — the public site, rebuilt with
`uv run cms publish && uv run cms deploy`.

## Run locally

```bash
uv sync
cp .env.example .env
git config core.hooksPath .githooks  # refuse to commit an unredacted transcript
uv run python scripts/seed_demo.py   # demo Director + Analyst (passwords from .env)
uv run cms serve        # then open http://localhost:8000/admin and log in as
                        # admin@example.test (Director) or editor@example.test (Analyst)
uv run pytest -q        # the test suite
```

## What is here

```text
app/               models and services (content, users, Charts, the Editor's Markdown, publish)
app/routes/        the Console's routes, one module per area
templates/         admin/ for the Console, public/ for the published site
static/            the Console and site stylesheets, the Editor's scripts, fonts
scripts/           seed_demo.py, check_submission.py, usage_report.py, redact_transcripts.py
tests/             one or more test files per ticket (test_t01_auth.py … test_t24_dashboard.py)
CONTEXT.md         the glossary: Director, Analyst, Data Bite, Report, Chart, …
docs/adr/          decision records, ADR-001 to ADR-007
docs/              the report, handoff, compaction log, transcripts, screenshots
notes/             field notes, client brief, token budget plan, usage ledger
```

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

Every Claude Code session ran on Anthropic's own API. No session used a
backup backend, so no commit has a `Backend:` trailer, and every row of
`notes/usage-ledger.csv` says `anthropic`.

| Provider  | Model    | Use                                                        |
| --------- | -------- | ---------------------------------------------------------- |
| Anthropic | Sonnet 5 | Stage 1 grill, specification, and tickets                  |
| Anthropic | Opus 5.5 | Stage 2 grills and specs, implementation, TDD, review, design |

**Other AI tools, outside Claude Code:** OpenAI Codex (GPT-5), used for
research, the final rubric audit, and help organizing the report. It was a
separate tool, not a Claude Code backend, so it does not appear in the ledger.
