#!/usr/bin/env python3
"""Status line for IPHS 400 MP2.

Claude Code runs this script on every status-line refresh and pipes session
JSON to stdin. The script does two things:
  1. prints one line under the prompt:  [Opus] ctx 47% ▓▓▓▓▓░░░░░
  2. records the context percentage in .claude/state/ctx_<session>.json so the
     Stop hook (ctx_guard.py) can read it at the end of each turn.
It must never crash: a broken status line hides the meter, nothing else.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def project_dir(data: dict) -> Path:
    ws = data.get("workspace") or {}
    return Path(
        os.environ.get("CLAUDE_PROJECT_DIR")
        or ws.get("project_dir")
        or ws.get("current_dir")
        or os.getcwd()
    )


def bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return "▓" * filled + "░" * (width - filled)


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except Exception:
        print("ctx ?")
        return

    model = (data.get("model") or {}).get("display_name", "Claude")
    effort = (data.get("effort") or {}).get("level", "")
    limits = data.get("rate_limits") or {}
    five = (limits.get("five_hour") or {}).get("used_percentage")
    week = (limits.get("seven_day") or {}).get("used_percentage")
    base = os.environ.get("ANTHROPIC_BASE_URL", "")
    provider = "anthropic" if not base else base.split("/")[2]
    pct = (data.get("context_window") or {}).get("used_percentage")
    if pct is None:
        print(f"[{model}] ctx --")
        return
    pct = float(pct)

    session = data.get("session_id") or "default"
    state_dir = project_dir(data) / ".claude" / "state"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        tmp = state_dir / f"ctx_{session}.json.tmp"
        tmp.write_text(json.dumps({
            "pct": pct, "ts": time.time(), "model": model, "effort": effort,
            "provider": provider, "five_h": five, "weekly": week,
        }))
        tmp.replace(state_dir / f"ctx_{session}.json")  # atomic swap
    except OSError:
        pass  # meter still prints even if the disk write fails

    def show(v):
        return f"{v:.0f}%" if isinstance(v, (int, float)) else "n/a"

    flag = "  ⚠ compact at next green test" if pct >= 60 else ""
    tag = f"{model}·{effort}" if effort else model
    if provider != "anthropic":
        tag += f"@{provider}"
    print(f"[{tag}] ctx {pct:.0f}% {bar(pct)} │ 5h {show(five)} │ wk {show(week)}{flag}")


if __name__ == "__main__":
    main()
