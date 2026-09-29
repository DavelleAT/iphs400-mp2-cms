# Evidence outline: README AI Use Statement and final report

Facts only, each with where to find it. It is not written in your voice: the
README statement and the report are yours to write from these. Items marked
**YOU** need something only you know.

## 1. Models and tools used

| Tool | What for | Evidence |
|---|---|---|
| Claude Code, **Sonnet 5**, medium effort | Session 1 (Sep 28): `/grill-with-docs`, `/to-spec`, `/to-tickets` (you confirmed this; the ledger labels it `unlabelled`) | `notes/usage-ledger.csv`, session `999d2722`, 15 rows; transcript session 01 |
| Claude Code, **Opus 5.5**, high effort | Every ticket, T01–T11: `/implement`, `/tdd`, `/code-review` (review sub-agents ran in the same sessions) | ledger rows for T01–T11; one T02 row at medium effort |
| Claude Code, Opus 5.5 | Submission work: Exercises A and B, the admin-link fix, the spec #1 correction | commits `27c662c`, `34f6b59`; issue #1 comment |
| mattpocock skills | `grill-with-docs`, `to-spec`, `to-tickets`, `implement`, `tdd`, `code-review` | transcripts 01–12 (`<command-name>` lines) |
| **Codex** (research and support) | **YOU**: there is no trace of Codex in the repo, ledger, or transcripts. Say what you used it for, which model, and when. Did any of the pasted prompts in session 01 (the `<pasted_content>` blocks) come from it? | **YOU** |
| Backends | Anthropic only: every ledger row says `provider=anthropic` | ledger `provider` column |

## 2. Two real prompts you sent (verbatim, from the transcripts)

1. Session 01, answering the grill (this is also where the accounts decision starts; see 3):
   > to be clear  Each intern should a shared editor account and publish routine Updates without waiting for the Director(Data bites). Reports need the Director’s approval because they are durable documents that people may cite.
2. Session 11, the request that became spec #11, ADR-004, T10, and T11:
   > so for the darrta bites and reports, i want to be able to include graphs and other things, charts ,tables and all that, how do we go about doing so

   Its follow-up: `both should get images. and let us do 1 and 2`

Others you could use instead: `Iwant to build this for the office of instituitional research here at kenyon, can we work with that` (session 01), and the pasted "Split T07 into two tickets…" instruction (session 01).

## 3. AI drift example: the individual-accounts contradiction in spec #1

- **Sequence:**
  - In the grill (session 01) you first asked for a shared intern account (prompt 1 above).
  - The WordPress Playground field notes then changed your mind: `notes/cms-field-notes.md`, item 5.
  - ADR-003 was revised to individual named Analyst accounts.
  - An issue #1 comment records that revision ("Revised after WordPress Playground field notes…").
- **The drift:** when spec #1 was revised, its Implementation Decisions section was updated ("Individual Analyst accounts (ADR-003, reversed from an earlier shared-account draft)"), but its Out of Scope section still said "per-intern individual accounts (deliberately rejected, see ADR-003)". The spec contradicted itself and misquoted the ADR it cited.
- **How long:** it stayed wrong through all eleven tickets. It was only caught during submission review on 2026-09-29.
- **Fix:** issue #1 body edited, with an explanatory comment: https://github.com/DavelleAT/iphs400-mp2-cms/issues/1#issuecomment-5896237324. The same edit fixed a second stale clause ("Data Bites stay Markdown-only"), which ADR-004 had reversed.
- **Why it matters for the report:** the model edited the section it was pointed at and didn't check the rest of the document for the old decision.

## 4. A real bug

Three bugs are documented in `/code-review` comments. Pick one:

| Bug | Caught by | Evidence |
|---|---|---|
| `create_app()` ran `db.init_db()` at import, so importing `app.main` (as the tests do) created or touched the **real** `cms.db` | T01 `/code-review` | issue #2 review comment; fix: FastAPI `lifespan` hook |
| Downloading a Report's file returned **500** when the row named a file that was missing on disk | T05 `/code-review` | issue #6 comment; test `test_a_file_missing_from_disk_is_404_not_a_crash` |
| The table sanitizer let `text-align:url(…)`, `expression(…)` and `var(…)` through in a cell's `style` | T09 `/code-review` | issue #10 comment; fix: the `_cell_alignment` attribute filter |

A process failure, not a code bug: in session 11 you reported "it saus ivalid log in credentials". The accounts and `.env` matched. The cause was which password to type, and the answer was the `.env.example` placeholders. That's a documentation gap, not a defect.

## 5. Budget numbers (from `uv run python scripts/usage_report.py`, 2026-09-29)

| Phase | Turns | 5h window spent | Weekly spent | Model |
|---|---|---|---|---|
| grill + spec + tickets (`unlabelled`) | 15 | 6.0% | 1.0% | Sonnet 5 |
| T01–T11, each | 3–9 | 3.0–6.0% | 0–1% | Opus 5.5 |
| `tickets` (T10/T11 slicing, session 11) | 2 | 1.0% | 0.0% | Opus 5.5 |

- 11 tickets done. Average weekly cost per ticket: **0.8%**.
- **Windows used:**
  - Sep 28: one window, 0% → 50% (session 1 through T05).
  - Sep 29: one window, 7% → 60% (T06 through T11).
  - That is two 5-hour windows in all, neither full.
- **Weekly meter:** 1% → 16% over the two days.
- **Coverage:** the ledger holds 13 sessions and there are 12 transcripts. Rubric B7(b) needs the ledger to cover at least 90% of transcript sessions.
- **Plan vs. actual:** `notes/token-budget-plan.md` was still the template stub when T01 was committed (`d4d3707`, Sep 28). The plan was written on Sep 29, after T11. **YOU**: the estimates you give for step 4.

## 6. Test results

- 279 tests pass (`uv run pytest -q`). This includes the 10 context-hook tests and the 8 usage-report tests, which passed for the first time in `27c662c`.
- A fresh clone passes too: `uv sync`, then `.env` from `.env.example`, then `seed_demo.py`, then pytest (279 passed). The seeded Director and Analyst both log in, and the Analyst gets 403 on `/admin/users`.
- Stage 1 checker: 10/12. It still needs the compaction log (step 6) and the `mp2-mvp` tag (step 8).

## 7. Workflow facts for the report

- **Order of work:** the spec (#1) came before the tickets (#2 onward). Spec #11 was a second spec, for charts, written before T10 and T11.
- **Session per ticket:** mostly one fresh session per ticket, with `/clear` or a new session before `/implement` (transcripts 02–12). The exception: the ledger shows T02 and T03 sharing session `c82bd2e4`.
- **Reviews:** a `/code-review` comment on every ticket issue before it closed (#2–#10, #12, #13).
- **ADRs:**
  - ADR-003: publish rights and accounts.
  - ADR-004: chart images, which reversed spec #1's "no Data Bite uploads".
- **Compactions:** none so far. `docs/process/compaction-log.md` doesn't exist yet (step 6).
