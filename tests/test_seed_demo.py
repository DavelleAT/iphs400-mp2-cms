"""scripts/seed_demo.py: a fresh clone gets demo accounts and content (E4)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from app import data_bites, db, reports
from app.rendering import first_chart

_SPEC = importlib.util.spec_from_file_location(
    "seed_demo", Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py")
seed_demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seed_demo)


def statuses(module) -> dict[str, str]:
    return {item["slug"]: item["status"] for item in module.list_all()}


def test_seed_creates_drafts_and_published_items_of_each_type(monkeypatch):
    monkeypatch.setenv("CMS_ADMIN_PASSWORD", "test-admin-pw")
    monkeypatch.setenv("CMS_EDITOR_PASSWORD", "test-editor-pw")
    assert seed_demo.main() == 0

    # Enough to see every part of the public site (T20): each type both ways,
    # every item with a Summary, and a Chart for the home page to feature.
    for module in (data_bites, reports):
        assert set(statuses(module).values()) == {"draft", "published"}
        assert all(item["summary"] for item in module.list_all())
    assert len(data_bites.list_published()) >= 3
    assert first_chart(data_bites.list_published()[0]["body"])


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
