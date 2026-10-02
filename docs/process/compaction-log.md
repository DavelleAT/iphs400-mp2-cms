# Compaction log

No compactions through session 29 (2026-10-01): none of the 28 saved
transcripts has a compaction in it, and the PreCompact hook
(`.claude/hooks/ctx_compact_log.py`, wired in `.claude/settings.json`) has
appended no row below. Each ticket ran in a fresh context after `/clear`.

The highest context in `notes/usage-ledger.csv` was 40%, in session
`9020c1e3` (2026-10-01, cutting spec #25 into tickets). Next were T17 (37%),
T13 (36%), and T16 and T19 (33%). From 2026-10-01 the status line warns at
30% and auto-compaction is set at 40% (`8d0d7dd`), below the 50–60% where
the course rule says to `/compact`. A session that would have gone further
stopped at a ticket boundary instead.

| UTC time | Session | Trigger | Focus note |
|---|---|---|---|
