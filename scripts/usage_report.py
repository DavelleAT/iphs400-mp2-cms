#!/usr/bin/env python3
"""Turn notes/usage-ledger.csv into a plan-vs-actual budget report.

Usage:
    uv run python scripts/usage_report.py                 # summary + forecast
    uv run python scripts/usage_report.py --remaining 4   # 4 tickets still to do

Why positive deltas: the 5-hour and weekly meters RESET (drop to 0) when their
window rolls over, and the weekly one only ever climbs inside a week. Summing
only the increases between consecutive rows measures what you actually spent
and ignores the resets. That is what spend() does, and it is your exercise.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

LEDGER = Path("notes/usage-ledger.csv")


def spend(series: list[float | None]) -> float:
    """Total rise across a meter that can reset to a lower value.

    Sum every increase between consecutive readings; ignore blanks (None) and
    any drop, which means the window reset.

    >>> spend([10.0, 12.0, 15.0])
    5.0
    >>> spend([80.0, 5.0, 9.0])
    4.0
    >>> spend([None, 4.0, None, 7.0])
    3.0
    """
    raise NotImplementedError("MP2 Exercise B: implement me with /tdd")

def read_rows(path: Path) -> list[dict]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def to_float(text: str | None) -> float | None:
    try:
        return float(text) if text not in (None, "") else None
    except ValueError:
        return None


def by_phase(rows: list[dict]) -> dict[str, dict]:
    phases: dict[str, dict] = defaultdict(
        lambda: {"turns": 0, "five": [], "weekly": [], "models": set(), "providers": set()}
    )
    for row in rows:
        phase = phases[row.get("phase") or "unlabelled"]
        phase["turns"] += 1
        phase["five"].append(to_float(row.get("five_h_pct")))
        phase["weekly"].append(to_float(row.get("weekly_pct")))
        if row.get("model"):
            phase["models"].add(row["model"])
        if row.get("provider"):
            phase["providers"].add(row["provider"])
    return phases


def ticket_phases(phases: dict[str, dict]) -> list[str]:
    return sorted(p for p in phases if p.upper().startswith("T") and p[1:].isdigit())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--remaining", type=int, default=0, help="tickets not yet built")
    args = ap.parse_args()

    if not args.ledger.exists():
        raise SystemExit(f"No ledger at {args.ledger}. Is the Stop hook registered?")
    rows = read_rows(args.ledger)
    if not rows:
        raise SystemExit("Ledger is empty.")
    phases = by_phase(rows)

    print(f"{'phase':<14}{'turns':>6}{'5h spent':>10}{'weekly':>9}  models / provider")
    for name, data in sorted(phases.items()):
        mix = ",".join(sorted(data["models"])) or "?"
        prov = ",".join(sorted(data["providers"] - {"anthropic"}))
        print(f"{name:<14}{data['turns']:>6}{spend(data['five']):>9.1f}%"
              f"{spend(data['weekly']):>8.1f}%  {mix}{(' @' + prov) if prov else ''}")

    tickets = ticket_phases(phases)
    if tickets:
        per = sum(spend(phases[t]["weekly"]) for t in tickets) / len(tickets)
        print(f"\nTickets done: {len(tickets)} · average weekly cost per ticket: {per:.1f}%")
        last = next((to_float(r.get("weekly_pct")) for r in reversed(rows)
                     if to_float(r.get("weekly_pct")) is not None), None)
        if last is not None and args.remaining:
            need, headroom = per * args.remaining, 100 - last
            verdict = "FITS" if need <= headroom * 0.8 else "TIGHT" if need <= headroom else "OVER BUDGET"
            print(f"Forecast: {args.remaining} tickets need ~{need:.0f}% of the weekly cap; "
                  f"{headroom:.0f}% remains → {verdict}")
            if verdict != "FITS":
                print("Fix in this order: 1) lower effort  2) switch to Sonnet/Haiku  "
                      "3) /clear more often  4) split fat tickets  5) Plan B backend (declare it)")
    else:
        print("\nNo ticket phases yet. Write the ticket id into .claude/state/phase "
              "at the start of each /implement session.")


if __name__ == "__main__":
    main()
