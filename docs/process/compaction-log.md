# Compaction log

One compaction in 30 sessions. Sessions 1–29 had none: none of their saved
transcripts has a compaction in it. Each ticket ran in a fresh context after
`/clear`. The one row below was appended by the PreCompact hook
(`.claude/hooks/ctx_compact_log.py`, wired in `.claude/settings.json`). It
is session `61d98248`, which ran T24 and then kept going for the post-ticket
wrap-up (transcript redaction, the rubric scorecard, the redeploy, and
splitting the files over 500 lines). It compacted automatically during that
wrap-up, after T24 had been committed. The work went on from the summary,
and `docs/handoff/01_stage2-wrapup_20261001.md` records where it stopped.

The highest context in `notes/usage-ledger.csv` was 40%, in session
`9020c1e3` (2026-10-01, cutting spec #25 into tickets). Next were T17 (37%),
T13 (36%), and T16 and T19 (33%). From 2026-10-01 the status line warns at
30% and auto-compaction is set at 40% (`8d0d7dd`), below the 50–60% where
the course rule says to `/compact`. A session that would have gone further
stopped at a ticket boundary instead.

| UTC time | Session | Trigger | Focus note |
|---|---|---|---|
| 2026-10-02 00:28 | 61d98248 | auto | (none) |
