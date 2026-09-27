#!/usr/bin/env python3
"""PreCompact hook: log every compaction to docs/process/compaction-log.md.

This is grading evidence for rubric item B6 (session hygiene):
  - trigger "manual" + a focus note  = you compacted on purpose (good)
  - trigger "auto"                   = the session overflowed (fix the habit)
Never exits 2: exit 2 on PreCompact would BLOCK compaction.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HEADER = (
    "# Compaction log\n\n"
    "| UTC time | Session | Trigger | Focus note |\n"
    "|---|---|---|---|\n"
)


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())
    log = project / "docs" / "process" / "compaction-log.md"
    log.parent.mkdir(parents=True, exist_ok=True)
    if not log.exists():
        log.write_text(HEADER)
    note = (event.get("custom_instructions") or "").replace("|", "/").replace("\n", " ").strip()
    row = "| {} | {} | {} | {} |\n".format(
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
        (event.get("session_id") or "?")[:8],
        event.get("trigger", "unknown"),
        note or "(none)",
    )
    with log.open("a") as f:
        f.write(row)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
