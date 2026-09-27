"""Tests for the token-budget report (IPHS 400 MP2, exercise 2)."""
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("usage_report", ROOT / "scripts" / "usage_report.py")
ur = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ur)

HEADER = "ts,session,phase,provider,model,effort,ctx_pct,five_h_pct,weekly_pct\n"


def ledger(tmp_path, *rows):
    p = tmp_path / "usage-ledger.csv"
    p.write_text(HEADER + "".join(rows))
    return p


def row(phase, five, weekly, model="Sonnet", provider="anthropic"):
    return f"2026-09-30T10:00:00Z,abc,{phase},{provider},{model},medium,40.0,{five},{weekly}\n"


def test_spend_counts_only_increases():
    assert ur.spend([10.0, 12.0, 15.0]) == 5.0


def test_spend_ignores_window_reset():
    assert ur.spend([80.0, 5.0, 9.0]) == 4.0


def test_spend_skips_blanks():
    assert ur.spend([None, 4.0, None, 7.0]) == 3.0


def test_spend_empty_is_zero():
    assert ur.spend([]) == 0.0 and ur.spend([None, None]) == 0.0


def test_report_groups_by_phase(tmp_path):
    p = ledger(tmp_path, row("grill", 5, 2, model="Opus"), row("grill", 15, 6, model="Opus"),
               row("T01", 20, 8), row("T01", 30, 12))
    out = subprocess.run([sys.executable, str(ROOT / "scripts/usage_report.py"),
                          "--ledger", str(p)], capture_output=True, text=True)
    assert "grill" in out.stdout and "10.0%" in out.stdout   # 5 -> 15
    assert "Opus" in out.stdout
    assert "average weekly cost per ticket: 4.0%" in out.stdout


def test_forecast_flags_over_budget(tmp_path):
    p = ledger(tmp_path, row("T01", 10, 60), row("T01", 40, 80))
    out = subprocess.run([sys.executable, str(ROOT / "scripts/usage_report.py"),
                          "--ledger", str(p), "--remaining", "4"], capture_output=True, text=True)
    assert "OVER BUDGET" in out.stdout and "split fat tickets" in out.stdout


def test_missing_ledger_explains(tmp_path):
    out = subprocess.run([sys.executable, str(ROOT / "scripts/usage_report.py"),
                          "--ledger", str(tmp_path / "nope.csv")], capture_output=True, text=True)
    assert out.returncode != 0 and "Stop hook" in out.stderr


def test_backup_provider_shown(tmp_path):
    p = ledger(tmp_path, row("T05", 0, 10, model="glm-5.3", provider="api.z.ai"),
               row("T05", 5, 14, model="glm-5.3", provider="api.z.ai"))
    out = subprocess.run([sys.executable, str(ROOT / "scripts/usage_report.py"),
                          "--ledger", str(p)], capture_output=True, text=True)
    assert "@api.z.ai" in out.stdout
