#!/usr/bin/env python3
"""Stop hook: warn when the context window crosses 50% / 60% / 80%.

Claude Code runs this after every Claude turn (the Stop event) and pipes the
event JSON to stdin. It reads the percentage the status line recorded, and
prints {"systemMessage": "..."} the first time usage crosses a threshold.
The message is shown to YOU, not to Claude. The hook never blocks and never
runs /compact itself: slash commands are yours to type.

Thresholds (override when launching:  CTX_WARN_PCT=1 claude  to test):
  CTX_WARN_PCT     default 50  -> "plan a /compact"
  CTX_COMPACT_PCT  default 60  -> "/compact at the next green test"
  urgent = CTX_COMPACT_PCT + 20 -> "compact or /handoff now; consider splitting"
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

NONE, WARN, COMPACT, URGENT = 0, 1, 2, 3


def thresholds() -> tuple[float, float, float]:
    warn = float(os.environ.get("CTX_WARN_PCT", 50))
    compact = float(os.environ.get("CTX_COMPACT_PCT", 60))
    return warn, compact, compact + 20


def band_for(pct: float, warn: float, compact: float, urgent: float) -> int:
    if pct >= urgent:
        return URGENT
    if pct >= compact:
        return COMPACT
    if pct >= warn:
        return WARN
    return NONE


def message_for(band: int, pct: float) -> str:
    p = f"{pct:.0f}%"
    return {
        WARN: (
            f"Context {p}: finish the current red-green cycle, then plan a "
            "/compact at the next green test."
        ),
        COMPACT: (
            f"Context {p}: at the next green test run  /compact keep: ticket #N "
            "acceptance criteria, what is left, files touched"
        ),
        URGENT: (
            f"Context {p}: compact now (or /handoff and start fresh). If this "
            "ticket keeps overflowing, split it with /to-tickets."
        ),
    }[band]


def decide(pct: float, last_band: int) -> tuple[str | None, int]:
    """Pure function (unit-tested): return (message or None, band to store).

    Warn once per upward crossing. When usage drops (after /compact or
    /clear), store the lower band so the next crossing warns again.
    """
    raise NotImplementedError("MP2 Exercise A: implement me with /tdd")

LEDGER_COLUMNS = [
    "ts", "session", "phase", "provider", "model", "effort",
    "ctx_pct", "five_h_pct", "weekly_pct",
]


def log_usage(project: Path, session: str, state: dict) -> None:
    """Append one row per turn to notes/usage-ledger.csv (rubric item B7)."""
    ledger = project / "notes" / "usage-ledger.csv"
    phase_file = project / ".claude" / "state" / "phase"
    try:
        phase = phase_file.read_text().strip() or "unlabelled"
    except OSError:
        phase = "unlabelled"

    def cell(value: object) -> str:
        return "" if value is None else str(value)

    row = [
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        session[:8], phase, cell(state.get("provider")), cell(state.get("model")),
        cell(state.get("effort")), f"{float(state.get('pct', 0)):.1f}",
        cell(state.get("five_h")), cell(state.get("weekly")),
    ]
    try:
        ledger.parent.mkdir(parents=True, exist_ok=True)
        new = not ledger.exists()
        with ledger.open("a", newline="") as f:
            writer = csv.writer(f)
            if new:
                writer.writerow(LEDGER_COLUMNS)
            writer.writerow(row)
    except OSError:
        pass


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or os.getcwd())
    session = event.get("session_id") or "default"
    state_dir = project / ".claude" / "state"
    ctx_file = state_dir / f"ctx_{session}.json"
    band_file = state_dir / f"ctx_{session}_band.json"

    try:
        state = json.loads(ctx_file.read_text())
        pct = float(state["pct"])
    except (OSError, ValueError, KeyError):
        return  # no status-line data yet: stay silent
    try:
        last_band = int(json.loads(band_file.read_text())["band"])
    except (OSError, ValueError, KeyError):
        last_band = NONE

    log_usage(project, session, state)

    msg, band = decide(pct, last_band)
    try:
        band_file.write_text(json.dumps({"band": band}))
    except OSError:
        pass
    if msg:
        print(json.dumps({"systemMessage": msg}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a warning hook must never break the session
    sys.exit(0)
