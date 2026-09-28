"""T01: login, logout, sessions (issue #2)."""
from __future__ import annotations

import sqlite3

import pytest

from tests.conftest import DEMO_USERS, csrf_from, post_form, user_id


def _post_login(client, email, password, *, with_csrf=True):
    data = {"email": email, "password": password}
    if with_csrf:
        data["csrf_token"] = csrf_from(client.get("/login").text)
    return client.post("/login", data=data, follow_redirects=False)


def _deactivate(client_as, email):
    """Deactivate through the Director's user-management UI (T02)."""
    director = client_as("admin")
    response = post_form(director, f"/admin/users/{user_id(director, email)}/deactivate", {})
    assert response.status_code == 303


@pytest.mark.parametrize("role, label", [("admin", "Director"), ("editor", "Analyst")])
def test_seeded_user_logs_in_and_reaches_admin(client_as, role, label):
    response = client_as(role).get("/admin", follow_redirects=False)
    assert response.status_code == 200
    assert DEMO_USERS[role]["email"] in response.text
    assert label in response.text


def test_login_redirects_to_admin(client):
    user = DEMO_USERS["admin"]
    response = _post_login(client, user["email"], user["password"])
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


def test_wrong_password_and_unknown_account_get_the_same_generic_error(client):
    wrong_pw = _post_login(client, DEMO_USERS["admin"]["email"], "nope")
    unknown = _post_login(client, "nobody@example.test", "nope")
    assert wrong_pw.status_code == unknown.status_code == 401
    assert "Invalid email or password." in wrong_pw.text
    assert "Invalid email or password." in unknown.text
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_deactivated_user_cannot_log_in(client, client_as):
    user = DEMO_USERS["editor"]
    _deactivate(client_as, user["email"])
    response = _post_login(client, user["email"], user["password"])
    assert response.status_code == 401
    assert "Invalid email or password." in response.text


@pytest.mark.parametrize("role", ["admin", "editor"])
def test_logout_clears_the_session(client_as, role):
    c = client_as(role)
    token = csrf_from(c.get("/admin").text)
    response = c.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert c.get("/admin", follow_redirects=False).status_code == 303


@pytest.mark.parametrize("path", ["/admin", "/admin/", "/admin/users", "/admin/anything/else"])
def test_anonymous_visitor_is_redirected_to_login(client, path):
    response = client.get(path, follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].endswith("/login")


@pytest.mark.parametrize("method, path", [("POST", "/admin"), ("PUT", "/admin/x"),
                                          ("DELETE", "/admin/x"), ("PATCH", "/admin")])
def test_anonymous_visitor_is_redirected_whatever_the_method(client, method, path):
    response = client.request(method, path, follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].endswith("/login")


def test_signed_in_user_gets_404_for_unknown_admin_path(client_as):
    response = client_as("admin").get("/admin/no-such-page", follow_redirects=False)
    assert response.status_code == 404


def test_deactivated_users_existing_session_fails_on_next_request(client_as):
    c = client_as("editor")
    assert c.get("/admin", follow_redirects=False).status_code == 200
    _deactivate(client_as, DEMO_USERS["editor"]["email"])
    response = c.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_login_without_csrf_token_is_rejected(client):
    user = DEMO_USERS["admin"]
    client.get("/login")  # the session has a token; the POST just omits it
    response = _post_login(client, user["email"], user["password"], with_csrf=False)
    assert response.status_code == 403
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_login_with_wrong_csrf_token_is_rejected(client):
    user = DEMO_USERS["admin"]
    client.get("/login")
    response = client.post("/login", data={"email": user["email"],
                                           "password": user["password"],
                                           "csrf_token": "forged"},
                           follow_redirects=False)
    assert response.status_code == 403


def test_logout_without_csrf_token_is_rejected(client_as):
    c = client_as("admin")
    response = c.post("/logout", follow_redirects=False)
    assert response.status_code == 403
    assert c.get("/admin", follow_redirects=False).status_code == 200


def test_passwords_are_stored_as_argon2_hashes(seeded_db):
    with sqlite3.connect(seeded_db) as conn:
        rows = conn.execute("SELECT password_hash FROM users").fetchall()
    assert len(rows) == len(DEMO_USERS)
    for (stored,) in rows:
        assert stored.startswith("$argon2")
        assert all(u["password"] not in stored for u in DEMO_USERS.values())
