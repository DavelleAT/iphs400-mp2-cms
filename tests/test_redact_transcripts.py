"""Transcripts are redacted before they are committed: passwords, secrets,
tokens, password hashes, and the author's email become [REDACTED], and
nothing else changes (scripts/redact_transcripts.py)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("redact_transcripts",
                                              ROOT / "scripts" / "redact_transcripts.py")
rt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rt)
main, redact = rt.main, rt.redact

R = "[REDACTED]"


@pytest.mark.parametrize("before, after", [
    # env and shell
    ("CMS_ADMIN_PASSWORD=hunter-22 uv run", f"CMS_ADMIN_PASSWORD={R} uv run"),
    ("export CMS_SECRET_KEY=abc123def", f"export CMS_SECRET_KEY={R}"),
    ("GH_TOKEN=xyz12345\\n", f"GH_TOKEN={R}\\n"),
    # code and JSON, escaped the way a JSONL transcript escapes it
    ('{\\"password\\": \\"test-admin-pw\\"}', f'{{\\"password\\": \\"{R}\\"}}'),
    ("password: 'scratch-admin-pw'", f"password: '{R}'"),
    # form data, URLs, curl
    ("email=a@example.test&password=change-me-admin", f"email=a@example.test&password={R}"),
    ('--data-urlencode "password=t21-director-pw"', f'--data-urlencode "password={R}"'),
    # tokens and hashes
    ('name=\\"csrf_token\\" value=\\"Uhp_9Vbf12qf9u2Yxy5DQdveFKg\\"',
     f'name=\\"csrf_token\\" value=\\"{R}\\"'),
    ("session=eyJhbGciOiJIUzI1NiJ9abcdef", f"session={R}"),
    ("$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA", R),
    ("ghp_" + "a" * 36, R),
    # a test password named in prose
    ("then log in with scratch-editor-pw again", f"then log in with {R} again"),
])
def test_it_redacts(before, after):
    assert redact(before, secrets=(), email=None)[0] == after


@pytest.mark.parametrize("code", [
    "def login(email: str, password: str):",
    'password=user["password"]',
    "data = {**data, \"csrf_token\": csrf_from(c.get('/admin').text)}",
    "SECRET_KEY = os.environ.get(\"CMS_SECRET_KEY\", \"dev\")",
    "Passwords are hashed with argon2. Never store or log a plain password.",
    '[sys.executable, \\"-m\\", \\"ghp_import\\"]',
    "password=secrets.token_urlsafe(18)",
])
def test_it_leaves_code_and_prose_alone(code):
    assert redact(code, secrets=(), email=None) == (code, {})


def test_it_redacts_the_real_secrets_and_the_authors_email_wherever_they_are():
    text = "key Zq9-real-key, mail me at someone@mail.test."
    redacted, found = redact(text, secrets=("Zq9-real-key",), email="someone@mail.test")
    assert redacted == f"key {R}, mail me at [REDACTED-EMAIL]."
    assert found == {"secret from .env": 1, "author email": 1}


def test_redacting_twice_changes_nothing():
    once = redact("CMS_ADMIN_PASSWORD=x-pw-1 password: 'y-pw'", secrets=(), email=None)[0]
    assert redact(once, secrets=(), email=None) == (once, {})


def test_check_fails_on_a_transcript_with_something_to_redact(tmp_path, capsys):
    dirty, clean = tmp_path / "dirty.md", tmp_path / "clean.md"
    dirty.write_text("CMS_EDITOR_PASSWORD=t23-analyst-pw")
    clean.write_text("nothing here")
    assert main(["--check", str(dirty), str(clean)]) == 1
    output = capsys.readouterr().out
    assert "dirty.md" in output and "t23-analyst-pw" not in output  # never echoes a value
    assert dirty.read_text() == "CMS_EDITOR_PASSWORD=t23-analyst-pw"  # --check writes nothing
    assert main(["--check", str(clean)]) == 0


def test_without_check_it_redacts_the_files_in_place(tmp_path):
    dirty = tmp_path / "dirty.md"
    dirty.write_text("CMS_EDITOR_PASSWORD=t23-analyst-pw")
    assert main([str(dirty)]) == 0
    assert dirty.read_text() == f"CMS_EDITOR_PASSWORD={R}"
