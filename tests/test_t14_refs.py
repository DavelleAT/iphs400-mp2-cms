"""T14: every Data Bite and Report has an immutable, never-reused `ref`
(issue #17), which a site link names it by: `report:<ref>` or
`data-bite:<ref>`."""
from __future__ import annotations

import re
import sqlite3

import pytest

from app import data_bites, db, reports, settings, site_links, users

HEX_REF = re.compile(r"[0-9a-f]{32}")
KINDS = [pytest.param(data_bites, "data-bite", id="data-bite"),
         pytest.param(reports, "report", id="report")]


def director() -> sqlite3.Row:
    found = next(u for u in users.list_users() if u["email"] == "admin@example.test")
    return users.get_active_user(found["id"])


def author() -> int:
    return director()["id"]


def create(module, slug: str = "fall-enrollment", title: str = "Fall enrollment") -> int:
    return module.create(title, slug, "Body.", author())


@pytest.mark.parametrize("module, kind", KINDS)
def test_a_new_item_gets_a_ref_that_editing_never_changes(module, kind):
    item_id = create(module)
    ref = module.get(item_id)["ref"]
    assert HEX_REF.fullmatch(ref)

    edit = {"user": director()} if module is reports else {}
    assert module.update(item_id, "Renamed", "renamed", "New body.", **edit)
    module.set_status(item_id, "published")
    assert module.get(item_id)["ref"] == ref
    assert site_links.state(f"{kind}:{ref}") == "published"


@pytest.mark.parametrize("module, kind", KINDS)
def test_a_ref_can_never_be_changed_in_the_database(module, kind):
    item_id = create(module)
    with pytest.raises(sqlite3.IntegrityError), db.connect() as conn:
        conn.execute(f"UPDATE {module._TABLE.table} SET ref = ? WHERE id = ?",
                     ("0" * 32, item_id))


def test_refs_are_unique_across_both_tables():
    refs = {data_bites.get(create(data_bites, f"b{n}"))["ref"] for n in range(5)}
    refs |= {reports.get(create(reports, f"r{n}"))["ref"] for n in range(5)}
    assert len(refs) == 10


@pytest.mark.parametrize("module, kind", KINDS)
def test_deleting_an_item_tombstones_its_ref(module, kind):
    item_id = create(module)
    reference = f"{kind}:{module.get(item_id)['ref']}"
    assert site_links.state(reference) == "draft"

    assert module.delete(item_id)
    assert site_links.state(reference) == "deleted"
    assert site_links.state(f"{kind}:{'f' * 32}") == "unknown"


def test_a_ref_names_one_kind_only():
    ref = reports.get(create(reports))["ref"]
    assert site_links.state(f"data-bite:{ref}") == "unknown"


@pytest.mark.parametrize("module, kind", KINDS)
def test_a_new_ref_is_never_a_tombstoned_one(module, kind, monkeypatch):
    """The generator is forced to give a deleted item's ref first: the insert
    tries again, with a fresh one."""
    old = create(module)
    tombstoned = module.get(old)["ref"]
    module.delete(old)

    fresh = iter([tombstoned, "a" * 32])
    calls = []
    monkeypatch.setattr(site_links, "_generate",
                        lambda: calls.append(1) or next(fresh))
    new = create(module)
    assert module.get(new)["ref"] == "a" * 32
    assert len(calls) == 2
    # SQLite may have reused the id; the ref still says "deleted".
    assert site_links.state(f"{kind}:{tombstoned}") == "deleted"


def test_a_new_ref_is_never_one_the_other_table_uses(monkeypatch):
    taken = reports.get(create(reports))["ref"]
    fresh = iter([taken, "b" * 32])
    monkeypatch.setattr(site_links, "_generate", lambda: next(fresh))
    assert data_bites.get(create(data_bites))["ref"] == "b" * 32


def test_three_collisions_fail_loudly_and_write_nothing(monkeypatch):
    taken = reports.get(create(reports))["ref"]
    monkeypatch.setattr(site_links, "_generate", lambda: taken)
    with pytest.raises(site_links.RefCollision):
        create(data_bites)
    assert data_bites.list_all() == []


OLD_SCHEMA = """
CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL, role TEXT NOT NULL, password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE data_bites (id INTEGER PRIMARY KEY, title TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', author_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')));
CREATE TABLE reports (id INTEGER PRIMARY KEY, title TEXT NOT NULL, slug TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', author_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')));
INSERT INTO users (email, name, role, password_hash) VALUES ('a@example.test', 'A', 'admin', 'x');
INSERT INTO data_bites (title, slug, body, author_id) VALUES ('One', 'one', 'B', 1), ('Two', 'two', 'B', 1);
INSERT INTO reports (title, slug, body, author_id) VALUES ('Three', 'three', 'B', 1);
"""


def test_init_db_gives_existing_rows_unique_refs_once(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_PATH", tmp_path / "old.db")
    with sqlite3.connect(settings.DATABASE_PATH) as conn:
        conn.executescript(OLD_SCHEMA)

    db.init_db()
    refs = [row["ref"] for row in [*data_bites.list_all(), *reports.list_all()]]
    assert len(refs) == 3 and len(set(refs)) == 3
    assert all(HEX_REF.fullmatch(ref) for ref in refs)

    db.init_db()
    assert [row["ref"] for row in [*data_bites.list_all(), *reports.list_all()]] == refs
    with pytest.raises(sqlite3.IntegrityError), db.connect() as conn:
        conn.execute("INSERT INTO data_bites (title, slug, body, author_id, ref)"
                     " VALUES ('Four', 'four', 'B', 1, ?)", (refs[0],))
