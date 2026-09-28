"""T02: user management (issue #3)."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEMO_USERS, csrf_from, post_form, user_id, user_row

NEW_ANALYST = {"name": "Riley Intern", "email": "riley@example.test",
               "password": "a-long-enough-password", "role": "editor"}


def _can_log_in(client: TestClient, email, password) -> bool:
    token = csrf_from(client.get("/login").text)
    response = client.post("/login", data={"email": email, "password": password,
                                           "csrf_token": token},
                           follow_redirects=False)
    return response.status_code == 303


def test_director_creates_a_user_who_can_then_log_in(client_as, client):
    director = client_as("admin")
    response = post_form(director, "/admin/users", NEW_ANALYST)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"

    listing = director.get("/admin/users").text
    assert NEW_ANALYST["name"] in listing and NEW_ANALYST["email"] in listing
    assert _can_log_in(client, NEW_ANALYST["email"], NEW_ANALYST["password"])
    assert "Analyst" in client.get("/admin").text


@pytest.mark.parametrize("override, error", [
    ({"email": DEMO_USERS["editor"]["email"].upper()}, "already has an account"),
    ({"email": "not-an-email"}, "valid email"),
    ({"password": "short"}, "at least 8 characters"),
    ({"role": "superuser"}, "Choose a role"),
    ({"name": "   "}, "Enter a name"),
])
def test_invalid_new_user_is_rejected_with_a_clear_error(client_as, client, override, error):
    director = client_as("admin")
    response = post_form(director, "/admin/users", {**NEW_ANALYST, **override})
    assert response.status_code == 400
    assert error in response.text
    assert not _can_log_in(client, NEW_ANALYST["email"], NEW_ANALYST["password"])


def test_role_change_takes_effect_on_the_users_next_request(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    assert analyst.get("/admin/users", follow_redirects=False).status_code == 403
    uid = user_id(director, DEMO_USERS["editor"]["email"])

    response = post_form(director, f"/admin/users/{uid}/role", {"role": "admin"})
    assert response.status_code == 303
    assert analyst.get("/admin/users", follow_redirects=False).status_code == 200

    post_form(director, f"/admin/users/{uid}/role", {"role": "editor"})
    assert analyst.get("/admin/users", follow_redirects=False).status_code == 403


def test_deactivated_user_is_signed_out_and_cannot_log_in_again(client_as, client):
    director, analyst = client_as("admin"), client_as("editor")
    uid = user_id(director, DEMO_USERS["editor"]["email"])

    response = post_form(director, f"/admin/users/{uid}/deactivate", {})
    assert response.status_code == 303
    assert analyst.get("/admin", follow_redirects=False).status_code == 303
    assert not _can_log_in(client, DEMO_USERS["editor"]["email"],
                           DEMO_USERS["editor"]["password"])
    # Kept, not deleted, so their history stays attributed.
    assert "Deactivated" in user_row(director, DEMO_USERS["editor"]["email"])


@pytest.mark.parametrize("action, data", [("deactivate", {}), ("role", {"role": "editor"})])
def test_director_cannot_lock_themselves_out(client_as, action, data):
    director = client_as("admin")
    uid = user_id(director, DEMO_USERS["admin"]["email"])
    response = post_form(director, f"/admin/users/{uid}/{action}", data)
    assert response.status_code == 400
    assert "your own account" in response.text
    assert director.get("/admin/users", follow_redirects=False).status_code == 200
    # The UI doesn't offer the controls on the Director's own row in the first place.
    assert "<form" not in user_row(director, DEMO_USERS["admin"]["email"])


@pytest.mark.parametrize("role, label", [("admin", "Director"), ("editor", "Analyst")])
def test_director_sees_each_users_role_as_director_or_analyst(client_as, role, label):
    director = client_as("admin")
    assert director.get("/admin/users").status_code == 200
    row = user_row(director, DEMO_USERS[role]["email"])
    shown = re.search(r"<option[^>]* selected>(\w+)<|<td>(Director|Analyst)</td>", row)
    assert label in shown.group(0)


# Every user-management route. {id} is filled with the seeded Analyst's id.
ROUTES = [
    ("GET", "/admin/users", {}),
    ("POST", "/admin/users", NEW_ANALYST),
    ("POST", "/admin/users/{id}/role", {"role": "admin"}),
    ("POST", "/admin/users/{id}/deactivate", {}),
]
POST_ROUTES = [r for r in ROUTES if r[0] == "POST"]


@pytest.fixture
def analyst_id(client_as):
    return user_id(client_as("admin"), DEMO_USERS["editor"]["email"])


@pytest.mark.parametrize("method, path, data", ROUTES)
def test_analyst_is_refused_every_user_management_route(client_as, analyst_id,
                                                        method, path, data):
    analyst = client_as("editor")
    token = csrf_from(analyst.get("/admin").text)
    response = analyst.request(method, path.format(id=analyst_id),
                               data={**data, "csrf_token": token} if data else None,
                               follow_redirects=False)
    assert response.status_code == 403
    # And nothing changed: the Analyst is still an active Analyst, no user added.
    assert analyst.get("/admin/users", follow_redirects=False).status_code == 403
    assert NEW_ANALYST["email"] not in client_as("admin").get("/admin/users").text


@pytest.mark.parametrize("method, path, data", ROUTES)
def test_anonymous_visitor_is_redirected_from_every_user_management_route(
        client, analyst_id, method, path, data):
    response = client.request(method, path.format(id=analyst_id), data=data or None,
                              follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].endswith("/login")


@pytest.mark.parametrize("method, path, data", POST_ROUTES)
def test_user_management_posts_without_csrf_token_are_rejected(
        client_as, client, analyst_id, method, path, data):
    director = client_as("admin")
    director.get("/admin")  # the session has a token; the POST just omits it
    response = post_form(director, path.format(id=analyst_id), data, with_csrf=False)
    assert response.status_code == 403
    # Nothing changed: no new user, the Analyst is still an active Analyst.
    assert not _can_log_in(client, NEW_ANALYST["email"], NEW_ANALYST["password"])
    assert client_as("editor").get("/admin/users", follow_redirects=False).status_code == 403


def test_only_a_director_sees_the_user_management_link(client_as):
    assert 'href="/admin/users"' in client_as("admin").get("/admin").text
    assert 'href="/admin/users"' not in client_as("editor").get("/admin").text
