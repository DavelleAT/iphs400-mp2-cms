# Token budget plan

Manual Part 5.4. Written 2026-09-29 for Stage 1. Updated 2026-10-05 with
Stage 2 (T12–T24) and the wrap-up. The "Estimated" column is what I expected
going in. The "Actual" columns come from `notes/usage-ledger.csv`.

## How the actuals are measured

Each row of the ledger is one turn, with the 5-hour and weekly meters as the
status line read them. A turn's cost is the rise from the reading before it,
in time order across the whole ledger. A drop means a window reset, and
counts as zero. Gaps of more than two hours are not counted, because usage
outside this project falls into them.

`scripts/usage_report.py` takes the deltas only between rows of the same
phase. That works for a ticket that runs once. It overcounts a phase that
comes back days later, because it charges the gap to that phase. Its
`spec` row says 87% of a 5-hour window, but the measured cost was 9%.
Its `T24` row says 24% of the week, but 21 points of that are the gap from
Oct 2 to Oct 5. The figures below use the time-ordered method.

Both meters move in whole percents. A single ticket's weekly figure is
accurate only to ±1.

## Models and effort, as actually used

The manual's default puts Sonnet on `/implement`. I ran every ticket on Opus.

| Stage | Model | Effort |
|---|---|---|
| Stage 1 `/grill-with-docs`, `/to-spec`, `/to-tickets` | Sonnet 5 | medium |
| Stage 2 grill, spec, and tickets (specs #14, #22, #25) | Opus 5.5 | high |
| `/implement` + `/tdd`, T01–T24 | Opus 5.5 | high (two T02 turns at medium) |
| `/code-review` (sub-agents, same session as each ticket) | Opus 5.5 | high |
| `/research`, quick lookups | none run as a separate stage | — |

## Estimate vs. actual

The estimates are in % of the **weekly** cap. That is how I thought about it.
The 5-hour column shows actuals only. I made no new estimate for Stage 2, so
the Stage 1 per-ticket estimate stands for both stages.

| Stage | Estimated (weekly) | Actual (weekly) | Actual (5-hour) |
|---|---|---|---|
| Stage 1 planning (grill + spec + tickets) | ~2% | 1% | 6% |
| Stage 1 tickets, T01–T11, per ticket | ~2% | 1.1% average (0–2% each) | 8.6% average (4–14%) |
| Spec #11 tickets (T10, T11) | — | 1% | 2% |
| Stage 1 submission + feedback | no estimate | 2% | 19% |
| Stage 2 planning, three specs | ~2% per spec | 3% in all | 20% in all |
| Stage 2 tickets, T12–T24, per ticket | ~2% | 3.2% average (2–5% each) | 23.8% average (14–35%) |
| Stage 2 wrap-up (session 29, after T24) | no estimate | 3% | 27% |

`/code-review` ran inside each ticket's own session, so the ledger can't split
it from `/implement`.

Stage 1 tickets came in under the estimate. Stage 2 tickets came in about
60% over it. The costliest were the Editor (T13, 4%), the Chart builder (T17,
5%), and the homepage, summaries, and search (T20, 4%). From T16 on, each
ticket also had a browser check with screenshots.

| Ticket | Weekly | 5-hour | | Ticket | Weekly | 5-hour |
|---|---|---|---|---|---|---|
| T12 | 3% | 20% | | T19 | 2% | 16% |
| T13 | 4% | 35% | | T20 | 4% | 31% |
| T14 | 4% | 26% | | T21 | 2% | 22% |
| T15 | 2% | 15% | | T22 | 4% | 20% |
| T16 | 4% | 31% | | T23 | 3% | 24% |
| T17 | 5% | 35% | | T24 | 2% | 14% |
| T18 | 3% | 21% | | | | |

## The questions in 5.4

**How many 5-hour windows?** Seven, two for Stage 1 and five for Stage 2.

| Window starts (UTC) | Meter | Work |
|---|---|---|
| Sep 28 | 0 → 50% | Stage 1 planning, T01–T05 |
| Sep 29 | 7 → 79% | T06–T11, Stage 1 submission |
| Sep 30, 19:09 | 1 → 100% | Stage 2 planning (spec #14), T12–T15 |
| Oct 1, 00:04 | 0 → 9% | end of T15, start of T16 |
| Oct 1, 13:47 | 2 → 91% | T16–T18, spec #22 and its tickets |
| Oct 1, 17:49 | 4 → 99% | T19, T20, spec #25's tickets, T21, T22 |
| Oct 1, 22:41 | 4 → 69% | end of T22, T23, T24, wrap-up |

Stage 1 never filled a window. Stage 2 filled one and nearly filled another:

- T15 reached 100% at 23:26 on Sep 30. Its last turns logged 100% until the
  window rolled over at about 00:00.
- T22 reached 99% at 20:53 on Oct 1. The next turn was at 22:41, in a new
  window.

The 17:49 window began less than five hours after the 13:47 one. The weekly
meter reset at the same moment, from 12% to 1%.

**How much of the week?**

- Estimated: 2% (Stage 1 planning) + 24 tickets × 2% + 3 Stage 2 specs × 2% = 56%.
- Actual: 64 weekly points in all, over three cycles of the weekly meter:
  - Sep 28 – Oct 1 at 00:19: 1 → 33%. This was all of Stage 1, plus spec #14
    and T12–T15.
  - Oct 1, 13:47 – 17:17: 0 → 12%.
  - Oct 1 at 17:49 – Oct 2: 1 → 22%.

  Stage 1 used 16 points and Stage 2 used 48. No single weekly cycle went
  past 33%.

**Context:** the peak was 40%, in session `9020c1e3` while cutting spec #25
into tickets. There was one compaction, in session 29's wrap-up (see
`docs/process/compaction-log.md`).

**What I'd cut first if over budget:** effort, from high to medium, keeping
Opus. That cut was never made. When the 5-hour window ran out in T15 and
T22, the work waited for the window to reset instead.

## Re-forecast

No tickets remain. What is left is the report, the AI Use Statement, the
issue comments, and the `mp2-final` tag. I write those myself, so they need
little model time.

This session started on Oct 5 with the weekly meter at 43% and the 5-hour
meter at 1%. The 21 points between Oct 2 and Oct 5 aren't in the ledger.
Nothing in this repo was committed in that time, so I don't count them
toward this project.

Even at the Stage 2 wrap-up's cost (3% of the week, 27% of a window), the
rest fits easily in the 57% of the week that is left.
