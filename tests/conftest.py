"""Shared test fixtures.

`client` gives you the app. `client_as(role)` gives you a client that is logged
in as a seeded user of that role — it works as soon as your login route exists,
so access-control tests stay one line:

    def test_editor_cannot_manage_users(client_as):
        assert client_as("editor").get("/admin/users").status_code in (302, 403)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

# Matches scripts/seed_demo.py. Passwords come from the environment there; in
# tests they are fixed and meaningless.
DEMO_USERS = {
    "admin": {"email": "admin@example.test", "password": "test-admin-pw"},
    "editor": {"email": "editor@example.test", "password": "test-editor-pw"},
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def client_as():
    """Return a factory: client_as("editor") -> a logged-in TestClient."""

    def _login(role: str) -> TestClient:
        user = DEMO_USERS[role]
        c = TestClient(create_app())
        response = c.post("/login", data={"email": user["email"],
                                          "password": user["password"]},
                          follow_redirects=False)
        if response.status_code == 404:
            pytest.skip("No /login route yet — build the login ticket first.")
        assert response.status_code in (200, 302, 303), (
            f"Login as {role} failed with {response.status_code}")
        return c

    return _login
