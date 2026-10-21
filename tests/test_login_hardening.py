"""S2: login hardening. A failed login never says whether the account exists,
and after 5 failed logins for one email within 15 minutes further attempts
for that email are refused, even with the right password."""
from __future__ import annotations

import pytest

from app import login_limiter
from tests.conftest import DEMO_USERS, csrf_from

ADMIN = DEMO_USERS["admin"]
EDITOR = DEMO_USERS["editor"]
LOCKED = "Too many failed logins for this email. Try again in 15 minutes."


class FrozenClock:
    """A clock the test moves by hand, in seconds."""

    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, minutes: float) -> None:
        self.now += minutes * 60


@pytest.fixture
def clock(monkeypatch) -> FrozenClock:
    frozen = FrozenClock()
    monkeypatch.setattr(login_limiter.limiter, "clock", frozen)
    return frozen


def _post_login(client, email, password):
    token = csrf_from(client.get("/login").text)
    return client.post("/login", data={"email": email, "password": password,
                                       "csrf_token": token},
                       follow_redirects=False)


def _fail(client, email, times):
    for _ in range(times):
        assert _post_login(client, email, "wrong-password").status_code == 401


def test_wrong_password_and_unknown_email_get_identical_responses(client):
    wrong_password = _post_login(client, ADMIN["email"], "wrong-password")
    unknown_email = _post_login(client, "nobody@example.test", "wrong-password")
    assert wrong_password.status_code == unknown_email.status_code == 401
    # The whole page, not only the message: same client, so same CSRF token.
    assert wrong_password.text == unknown_email.text
    assert "Invalid email or password." in wrong_password.text


def test_sixth_attempt_is_refused_even_with_the_right_password(client, clock):
    _fail(client, ADMIN["email"], 5)
    clock.advance(minutes=1)
    response = _post_login(client, ADMIN["email"], ADMIN["password"])
    assert response.status_code == 429
    assert LOCKED in response.text
    # No session was started.
    assert client.get("/admin", follow_redirects=False).status_code == 303


def test_four_failures_do_not_lock(client, clock):
    _fail(client, ADMIN["email"], 4)
    assert _post_login(client, ADMIN["email"], ADMIN["password"]).status_code == 303


def test_login_works_again_once_15_minutes_have_passed(client, clock):
    _fail(client, ADMIN["email"], 5)
    clock.advance(minutes=14.9)
    assert _post_login(client, ADMIN["email"], ADMIN["password"]).status_code == 429
    clock.advance(minutes=0.1)
    response = _post_login(client, ADMIN["email"], ADMIN["password"])
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


def test_failures_older_than_15_minutes_do_not_count(client, clock):
    _fail(client, ADMIN["email"], 4)
    clock.advance(minutes=16)
    _fail(client, ADMIN["email"], 1)
    assert _post_login(client, ADMIN["email"], ADMIN["password"]).status_code == 303


def test_lockout_is_keyed_on_the_account_not_the_client(client, clock):
    _fail(client, ADMIN["email"], 5)
    # Same client, another account: still logs in.
    response = _post_login(client, EDITOR["email"], EDITOR["password"])
    assert response.status_code == 303


def test_email_case_and_spaces_share_one_count(client, clock):
    _fail(client, ADMIN["email"].upper(), 3)
    _fail(client, f"  {ADMIN['email']} ", 2)
    assert _post_login(client, ADMIN["email"], ADMIN["password"]).status_code == 429


def test_unknown_email_locks_the_same_way(client, clock):
    """A lockout must not reveal which emails have accounts either."""
    _fail(client, "nobody@example.test", 5)
    response = _post_login(client, "nobody@example.test", "wrong-password")
    assert response.status_code == 429
    assert LOCKED in response.text


def test_a_successful_login_clears_the_count(client, clock):
    _fail(client, ADMIN["email"], 4)
    assert _post_login(client, ADMIN["email"], ADMIN["password"]).status_code == 303
    client.post("/logout", data={"csrf_token": csrf_from(client.get("/admin").text)})
    _fail(client, ADMIN["email"], 4)
    assert _post_login(client, ADMIN["email"], ADMIN["password"]).status_code == 303
