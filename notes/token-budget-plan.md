# Token budget plan

Manual Part 5.4. Written 2026-09-29. The "Estimated" column is what I expected
going in; the "Actual" columns come from `notes/usage-ledger.csv` through
`uv run python scripts/usage_report.py`.

## Models and effort, as actually used

The manual's default puts Sonnet on `/implement`. I ran every ticket on Opus.

| Stage | Model | Effort |
|---|---|---|
| `/grill-with-docs`, `/to-spec`, `/to-tickets` | Sonnet 5 | medium |
| `/implement` + `/tdd`, T01–T11 | Opus 5.5 | high (one T02 turn at medium) |
| `/code-review` (sub-agents, same session as each ticket) | Opus 5.5 | high |
| `/research`, quick lookups | none run as a separate stage | — |

## Estimate vs. actual

The estimates are in % of the **weekly** cap; that is how I thought about it.
The 5-hour column is actual only.

| Stage | Estimated (weekly) | Actual (weekly) | Actual (5-hour window) |
|---|---|---|---|
| Grill + spec + tickets, combined | ~2% | 1.0% | 6.0% |
| `/implement` + `/tdd`, per ticket | ~1% | 0.8% on average, review included (0–1% each) | 3.0–6.0% each |
| `/code-review`, per ticket | ~1% | counted in the row above: it ran in the same session | — |
| Lookups | no estimate | none logged separately | — |

`/code-review` ran inside each ticket's own session, so the ledger can't split
it from `/implement`. Together I estimated about 2% of the week per ticket.
The measured cost was 0.8%.

## The questions in 5.4

**How many 5-hour windows?** Two, for the planning session and 11 tickets
(the original 9 plus T10 and T11):

- Sep 28: 0% → 50% of one window (planning, T01–T05).
- Sep 29: 7% → 60% of a second window (T06–T11).

Neither window filled.

**How much of the week?**

- Estimated: about 2% + 11 × 2% ≈ 24%.
- Actual: the weekly meter went from 1% to 16%, so about 15% of the week.

**What I'd cut first if over budget:** effort, from high to medium, keeping
Opus.

## Re-forecast

`usage_report.py` puts the average at 0.8% of the weekly cap per ticket, and
16% of the week is used. No core tickets remain. The weekly meter leaves room
for stretch tickets.
