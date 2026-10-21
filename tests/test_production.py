"""F9: production configuration (issue #30). With CMS_ENV=production the app
refuses unsafe settings, never creates demo accounts, and creates its one
Director from the environment. The checks take the environment as a dict, so
these tests never change the real one."""
from __future__ import annotations

import sqlite3
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app import cli, db, production, settings
from app.main import create_app
from tests.conftest import DEMO_USERS, csrf_from

EXAMPLE = production.example_values()
SAFE = {
    "CMS_ENV": "production",
    "CMS_SECRET_KEY": "a-fresh-random-value-nobody-else-has-1234567890",
    "CMS_ADMIN_EMAIL": "director@kenyon.test",
    "CMS_ADMIN_PASSWORD": "a-fresh-director-password",
}


def env(**changes) -> dict[str, str]:
    """SAFE with some variables changed; None removes one."""
    result = {**SAFE, **changes}
    return {key: value for key, value in result.items() if value is not None}


def refusal(environment) -> str:
    with pytest.raises(production.UnsafeConfig) as caught:
        production.check(environment)
    return str(caught.value)


# Step 1: the secret key.

@pytest.mark.parametrize("secret", [None, "", settings.DEV_SECRET_KEY,
                                    EXAMPLE["CMS_SECRET_KEY"]])
def test_step1_unsafe_secret_key_is_refused_by_name(secret):
    assert "CMS_SECRET_KEY" in refusal(env(CMS_SECRET_KEY=secret))


def test_step1_cms_serve_refuses_to_start_and_names_the_variable(monkeypatch, capsys):
    def must_not_start(*args, **kwargs):
        raise AssertionError("uvicorn started with an unsafe configuration")

    monkeypatch.setattr("uvicorn.run", must_not_start)
    bad = env(CMS_SECRET_KEY=EXAMPLE["CMS_SECRET_KEY"])
    assert cli.main(["serve"], env=bad) == 1
    assert "CMS_SECRET_KEY" in capsys.readouterr().err


def test_step1_create_app_refuses_an_unsafe_configuration():
    with pytest.raises(production.UnsafeConfig, match="CMS_SECRET_KEY"):
        create_app(env(CMS_SECRET_KEY=None))


def test_step1_cms_serve_starts_with_a_safe_configuration(monkeypatch):
    started = []
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: started.append(k))
    assert cli.main(["serve", "--port", "8001"], env=SAFE) == 0
    assert started and started[0]["port"] == 8001


# Step 2: the admin account's variables.

@pytest.mark.parametrize("changes, variable", [
    ({"CMS_ADMIN_EMAIL": None}, "CMS_ADMIN_EMAIL"),
    ({"CMS_ADMIN_EMAIL": "  "}, "CMS_ADMIN_EMAIL"),
    ({"CMS_ADMIN_PASSWORD": None}, "CMS_ADMIN_PASSWORD"),
    ({"CMS_ADMIN_PASSWORD": EXAMPLE["CMS_ADMIN_PASSWORD"]}, "CMS_ADMIN_PASSWORD"),
])
def test_step2_unsafe_admin_variables_are_refused_by_name(changes, variable):
    assert variable in refusal(env(**changes))


def test_step2_every_problem_is_named_at_once():
    message = refusal({"CMS_ENV": "production"})
    for variable in ("CMS_SECRET_KEY", "CMS_ADMIN_EMAIL", "CMS_ADMIN_PASSWORD"):
        assert variable in message


def test_step2_a_safe_configuration_passes():
    production.check(SAFE)


def test_step2_development_is_unchanged():
    """No CMS_ENV, or development: the .env.example values still run."""
    production.check({})
    production.check({**EXAMPLE, "CMS_ENV": "development"})


# Step 3: the demo seed refuses to run.

def test_step3_seed_demo_exits_nonzero_and_creates_nothing(tmp_path):
    database = tmp_path / "prod-seed.db"
    result = subprocess.run(
        [sys.executable, "scripts/seed_demo.py"], cwd=settings.ROOT,
        env={**env(), "CMS_DATABASE": str(database), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True)
    assert result.returncode != 0
    assert "CMS_ENV=production" in result.stdout + result.stderr
    assert not database.exists()


# Step 4: the Director comes from the environment.

def _login(c: TestClient, email: str, password: str):
    token = csrf_from(c.get("/login").text)
    return c.post("/login", data={"email": email, "password": password,
                                  "csrf_token": token}, follow_redirects=False)


@pytest.fixture
def empty_db(tmp_path, monkeypatch):
    """An empty database in place of conftest's seeded one."""
    monkeypatch.setattr(settings, "DATABASE_PATH", tmp_path / "prod-check.db")
    return settings.DATABASE_PATH


def test_step4_startup_creates_one_director_from_the_environment(empty_db):
    with TestClient(create_app(SAFE)) as c:
        response = _login(c, SAFE["CMS_ADMIN_EMAIL"], SAFE["CMS_ADMIN_PASSWORD"])
        assert response.status_code == 303
        assert c.get("/admin/users").status_code == 200  # a Director's page
    with sqlite3.connect(empty_db) as conn:
        rows = conn.execute("SELECT email, role FROM users").fetchall()
    assert rows == [(SAFE["CMS_ADMIN_EMAIL"], "admin")]


@pytest.mark.parametrize("role", ["admin", "editor"])
def test_step4_demo_logins_are_refused(empty_db, role):
    with TestClient(create_app(SAFE)) as c:
        demo = DEMO_USERS[role]
        assert _login(c, demo["email"], demo["password"]).status_code == 401


def test_step4_a_restart_does_not_add_a_second_director(empty_db):
    for _ in range(2):
        with TestClient(create_app(SAFE)):
            pass
    with sqlite3.connect(empty_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1


def test_step4_development_startup_creates_no_account(empty_db):
    with TestClient(create_app({})):
        pass
    with sqlite3.connect(empty_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


# Step 5: .env.example and the README.

def test_step5_env_example_and_readme_document_production():
    example = (settings.ROOT / ".env.example").read_text().splitlines()
    assert "CMS_ENV=development" in example
    assert any(line.startswith("CMS_ADMIN_EMAIL=") for line in example)
    readme = (settings.ROOT / "README.md").read_text()
    section = readme.split("## Production", 1)[1].split("\n## ", 1)[0]
    for variable in ("CMS_ENV", "CMS_SECRET_KEY", "CMS_ADMIN_EMAIL",
                     "CMS_ADMIN_PASSWORD", "CMS_DATABASE"):
        assert variable in section
    assert "CMS_ENV=production uv run cms serve" in section
