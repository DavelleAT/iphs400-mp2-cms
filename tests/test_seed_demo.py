"""scripts/seed_demo.py: a fresh clone gets demo accounts and content (E4)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app import data_bites, db, reports

_SPEC = importlib.util.spec_from_file_location(
    "seed_demo", Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py")
seed_demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seed_demo)


def statuses(module) -> dict[str, str]:
    return {item["slug"]: item["status"] for item in module.list_all()}


def test_seed_creates_a_draft_and_a_published_item_of_each_type(monkeypatch):
    monkeypatch.setenv("CMS_ADMIN_PASSWORD", "test-admin-pw")
    monkeypatch.setenv("CMS_EDITOR_PASSWORD", "test-editor-pw")
    assert seed_demo.main() == 0

    assert sorted(statuses(data_bites).values()) == ["draft", "published"]
    assert sorted(statuses(reports).values()) == ["draft", "published"]
    assert data_bites.list_published() and reports.list_published()


def test_seed_is_safe_to_rerun(monkeypatch, capsys):
    monkeypatch.setenv("CMS_ADMIN_PASSWORD", "test-admin-pw")
    monkeypatch.setenv("CMS_EDITOR_PASSWORD", "test-editor-pw")
    assert seed_demo.main() == 0
    first = statuses(data_bites), statuses(reports)
    assert seed_demo.main() == 0
    assert (statuses(data_bites), statuses(reports)) == first
    assert "exists   survey-calendar" in capsys.readouterr().out
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
