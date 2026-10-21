# IPHS 400 MP2plus report

Davelle Ampofo-Twumasi · Kenyon Office of Institutional Research CMS · October 21, 2026
Repo: https://github.com/DavelleAT/iphs400-mp2-cms · Pages: https://davelleat.github.io/iphs400-mp2-cms/ · Tag: `mp2plus-final`

**Base.** `mp2plus-base` = `mp2-final` = `feb8733`. I did not resubmit MP2, so there is no resubmission merge. At the base, the checker passed 22/22 and pytest passed 1540, with no pre-existing failures (`notes/mp2plus-plan.md`). Test files that existed at the base only gained lines. `tests/conftest.py` gained the `reset_login_limiter` fixture and one import line.

| Id | Evidence |
|----|----------|
| S2 | tests/test_login_hardening.py; fixture reset_login_limiter in tests/conftest.py |
| F9 | issue #30; tests/test_production.py; mp2plus-production-1280.png, mp2plus-production-390.png |
| P1 | PR #31 closing issue #30; carries F9 |
| S1 | tests/test_access_matrix.py |
| P3 | CONTEXT.md Decisions table; docs/adr/ADR-008-deactivate-never-delete-accounts.md |
| P4 | before: commit 49cd879; after: commit 6af1232; see the P4 section |

**Left broken or limited, one line each:**
- **S2:** the lockout count is kept in memory, so a server restart clears it. That's acceptable for a console that runs as one process on one machine (ADR-001).
- **F9:** nothing known. The `/code-review` on PR #31 found that production would start on a database holding the demo accounts; the fix commit `d7d7277` refuses it.
- **P1:** nothing known.
- **S1:** the collector opens FastAPI 0.141's included-router wrappers through `original_router`, so a FastAPI upgrade that renames that attribute would empty the list. The floor of known Director-only routes in the test would fail loudly if that happened.
- **P3:** nothing known.
- **P4:** the ledger records the weekly meter in whole percents, so a short exercise can record 0.0% (see below).

## P4

Before (commit `49cd879`, `uv run python scripts/usage_report.py --remaining 4`):

```text
Tickets done: 24 · average weekly cost per ticket: 2.4%
Forecast: 4 tickets need ~10% of the weekly cap; 66% remains → FITS
```

After (`uv run python scripts/usage_report.py --remaining 1`, the one being P4 itself, which this commit finishes; the MP2plus rows of its phase table, then its last two lines):

| phase | turns | 5h spent | weekly |
|---|---|---|---|
| P3 | 1 | 0.0% | 0.0% |
| P4 | 1 | 0.0% | 0.0% |
| S1 | 1 | 0.0% | 0.0% |
| S2 | 2 | 0.0% | 0.0% |
| T30 | 3 | 3.0% | 1.0% |
| mp2plus-setup | 1 | 0.0% | 0.0% |

```text
Tickets done: 25 · average weekly cost per ticket: 2.3%
Forecast: 1 tickets need ~2% of the weekly cap; 64% remains → FITS
```

**The gap.** The forecast was 2.4% of the weekly cap per ticket, but S2 actually cost 0.0% weekly and F9 with P1 (T30), the largest exercise, cost 1.0%. The ledger stores the weekly meter in whole percents, and it only moved from 34 to 36 across all of MP2plus. So an exercise that doesn't tip it to the next percent records 0, and the real cost of all MP2plus work was about 2 points of the weekly cap. The 2.4% average comes from MP2, where planning phases (spec, tickets) and big tickets like T24 (24% weekly) ran at higher cost. The MP2plus exercises were small changes to an app and test suite that already existed, all done in one continuous session at medium effort.
