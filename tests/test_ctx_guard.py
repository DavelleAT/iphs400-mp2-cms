"""Tests for the context-threshold hooks (IPHS 400 MP2, setup exercise)."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / ".claude" / "hooks"


def load(name):
    spec = importlib.util.spec_from_file_location(name, HOOKS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


guard = load("ctx_guard")


def run(script, payload, project, **env):
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project), **env},
    )


# ---- pure logic -----------------------------------------------------------

def test_silent_below_50():
    assert guard.decide(49.9, guard.NONE) == (None, guard.NONE)


def test_warns_once_at_50():
    msg, band = guard.decide(52, guard.NONE)
    assert band == guard.WARN and "52%" in msg
    assert guard.decide(55, band) == (None, guard.WARN)  # no nagging


def test_compact_message_at_60_names_focus_note():
    msg, band = guard.decide(61, guard.WARN)
    assert band == guard.COMPACT and "/compact keep:" in msg


def test_urgent_at_80_suggests_split():
    msg, band = guard.decide(81, guard.COMPACT)
    assert band == guard.URGENT and "/to-tickets" in msg


def test_rearms_after_compaction():
    _, band = guard.decide(20, guard.COMPACT)   # usage dropped after /compact
    assert band == guard.NONE
    msg, _ = guard.decide(51, band)             # next crossing warns again
    assert msg is not None


def test_thresholds_from_env(monkeypatch):
    monkeypatch.setenv("CTX_WARN_PCT", "1")
    msg, _ = guard.decide(2, guard.NONE)
    assert msg is not None


# ---- end to end: status line -> Stop hook ---------------------------------

def test_statusline_then_stop_hook(tmp_path):
    sl = run("ctx_statusline.py",
             {"session_id": "s1", "model": {"display_name": "Opus"},
              "context_window": {"used_percentage": 63.4}}, tmp_path)
    assert "ctx 63%" in sl.stdout
    out = run("ctx_guard.py", {"session_id": "s1", "hook_event_name": "Stop"}, tmp_path)
    assert out.returncode == 0
    assert "/compact" in json.loads(out.stdout)["systemMessage"]
    again = run("ctx_guard.py", {"session_id": "s1", "hook_event_name": "Stop"}, tmp_path)
    assert again.stdout.strip() == ""           # warned once, then quiet


def test_stop_hook_silent_without_data(tmp_path):
    out = run("ctx_guard.py", {"session_id": "nobody"}, tmp_path)
    assert out.returncode == 0 and out.stdout == ""


def test_stop_hook_survives_garbage_stdin(tmp_path):
    out = subprocess.run([sys.executable, str(HOOKS / "ctx_guard.py")],
                         input="not json", capture_output=True, text=True,
                         env={**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path)})
    assert out.returncode == 0


def test_precompact_logs_focus_note(tmp_path):
    run("ctx_compact_log.py",
        {"session_id": "abcdef123", "trigger": "manual",
         "custom_instructions": "keep: ticket #5 criteria"}, tmp_path)
    log = (tmp_path / "docs/process/compaction-log.md").read_text()
    assert "| manual | keep: ticket #5 criteria |" in log
