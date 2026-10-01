"""Shared test fixtures.

`client` gives you the app. `client_as(role)` gives you a client that is logged
in as a seeded user of that role — it works as soon as your login route exists,
so access-control tests stay one line:

    def test_editor_cannot_manage_users(client_as):
        assert client_as("editor").get("/admin/users").status_code in (302, 403)
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import db, settings, users
from app.main import create_app

# Matches scripts/seed_demo.py. Passwords come from the environment there; in
# tests they are fixed and meaningless.
DEMO_USERS = {
    "admin": {"email": "admin@example.test", "password": "test-admin-pw"},
    "editor": {"email": "editor@example.test", "password": "test-editor-pw"},
}


def csrf_from(html: str) -> str:
    """Pull the CSRF token out of a rendered form."""
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "no csrf_token field in the page"
    return match.group(1)


def post_form(c: TestClient, path: str, data: dict, *, with_csrf=True):
    """POST an admin form as the logged-in client, with the session's CSRF token."""
    if with_csrf:
        data = {**data, "csrf_token": csrf_from(c.get("/admin").text)}
    return c.post(path, data=data, follow_redirects=False)


def user_row(director: TestClient, email: str) -> str:
    """This user's row of the Director's user list, as HTML."""
    for row in director.get("/admin/users").text.split("<tr")[1:]:
        if email in row:
            return row
    raise AssertionError(f"{email} is not listed")


def user_id(director: TestClient, email: str) -> str:
    return re.match(r' id="user-(\d+)"', user_row(director, email)).group(1)


def second_analyst(director: TestClient) -> TestClient:
    """A logged-in client for a second, named Analyst (not the seeded one)."""
    account = {"name": "Riley Intern", "email": "riley@example.test",
               "password": "a-long-enough-password", "role": "editor"}
    assert post_form(director, "/admin/users", account).status_code == 303
    c = TestClient(create_app())
    token = csrf_from(c.get("/login").text)
    c.post("/login", data={**account, "csrf_token": token})
    return c


def backdate(table: str, row_id: str) -> None:
    """Setup only: move a content row's timestamps into the past, so an edit
    made within the same second still visibly changes updated_at."""
    with db.connect() as conn:
        conn.execute(f"UPDATE {table} SET created_at = '2026-01-05 09:00:00',"
                     " updated_at = '2026-01-05 09:00:00' WHERE id = ?", (row_id,))


@pytest.fixture(autouse=True)
def seeded_db(tmp_path, monkeypatch):
    """Every test gets its own database holding the DEMO_USERS, and its own
    uploads directory. No deployed URL either, whatever a local .env says; a
    test that needs one sets it."""
    monkeypatch.setattr(settings, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(settings, "UPLOADS", tmp_path / "uploads")
    monkeypatch.setattr(settings, "BASE_PATH", "")
    db.init_db()
    for role, user in DEMO_USERS.items():
        users.create_user(user["email"], user["password"], role)
    return settings.DATABASE_PATH


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def client_as():
    """Return a factory: client_as("editor") -> a logged-in TestClient."""

    def _login(role: str) -> TestClient:
        user = DEMO_USERS[role]
        c = TestClient(create_app())
        form = c.get("/login")
        if form.status_code == 404:
            pytest.skip("No /login route yet — build the login ticket first.")
        response = c.post("/login", data={"email": user["email"],
                                          "password": user["password"],
                                          "csrf_token": csrf_from(form.text)},
                          follow_redirects=False)
        assert response.status_code in (200, 302, 303), (
            f"Login as {role} failed with {response.status_code}")
        return c

    return _login
