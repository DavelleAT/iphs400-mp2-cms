# Compaction log

No compactions through session 13 (2026-09-29). Each ticket ran in a fresh
context after `/clear`, and no session passed 28% context in
`notes/usage-ledger.csv` (peak: T11, session `60601091`), below the 50–60%
point where the course rule says to `/compact`. The PreCompact hook
(`.claude/hooks/ctx_compact_log.py`) is wired in `.claude/settings.json` and
appends a row below if a compaction ever happens.

| UTC time | Session | Trigger | Focus note |
|---|---|---|---|
