#!/usr/bin/env python3
"""Redact the session transcripts in docs/transcripts/ before they are committed.

    python3 scripts/redact_transcripts.py            # redact every transcript in place
    python3 scripts/redact_transcripts.py FILE...    # redact these
    python3 scripts/redact_transcripts.py --check FILE...   # exit 1 if any needs it
    python3 scripts/redact_transcripts.py --staged   # --check what is staged (pre-commit)

Passwords, secret keys, tokens, CSRF and session values, password hashes, and
the author's email (`git config user.email`) become [REDACTED]. So do the
real secrets in .env, wherever they appear. Nothing else changes. Values are
found by their context (`password: "..."`, `CMS_ADMIN_PASSWORD=...`), so this
file names none. --check reports what it found, never the values.

The SessionEnd hook (.claude/hooks/save_transcript.py) redacts each
transcript as it is saved, and .githooks/pre-commit refuses a commit that
would add an unredacted one.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPTS = ROOT / "docs" / "transcripts"
R = "[REDACTED]"
_NOT_DONE = r"(?!\[REDACTED\])"
_QUOTE = r"\\*[\"']"  # a quote, possibly JSON-escaped, as in a JSONL transcript
_KEY = r"(?:new_|old_|confirm_)?password"
# What follows `password=` in code, not a value: a type, a lookup, a call.
_CODE = r"(?!str\b|None\b|user\[|form\[|data\[|secrets\.|os\.|Form\(|getpass|<|\{|\$)"
RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("env value", re.compile(
        r"\b((?:[A-Z][A-Z0-9_]*_)?(?:PASSWORD|PASSWD|SECRET(?:_KEY)?|TOKEN|API_KEY)=)"
        + _NOT_DONE + r"([^\s\\\"'`;&|)]+)"), r"\1" + R),
    ("password", re.compile(
        r"(" + _KEY + r"\\*[\"']?\s*[:=]\s*" + _QUOTE + r")" + _NOT_DONE
        + r"([^\"'\\\s,&)}]{3,})", re.I), r"\1" + R),
    ("password", re.compile(
        r"(" + _KEY + r"=)" + _NOT_DONE + _CODE + r"([^\"'\\\s,&)}\]]{3,})", re.I), r"\1" + R),
    ("password", re.compile(r"(--password[= ])" + _NOT_DONE + r"([^\s\\\"']+)"), r"\1" + R),
    ("CSRF token", re.compile(
        r"(csrf_token\\*\"?\s*(?:value=|[:=])\s*\\*[\"']?)([A-Za-z0-9_\-]{16,})"), r"\1" + R),
    ("session cookie", re.compile(r"(\bsession=)([A-Za-z0-9._\-]{16,})"), r"\1" + R),
    ("password hash", re.compile(r"\$argon2(?:id|i|d)\$[^\s\"'\\]+"), R),
    ("token", re.compile(
        r"\b(?:ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|github_pat_\w{20,}"
        r"|sk-ant-[\w-]{20,}|sk-[A-Za-z0-9]{32,}|AKIA[0-9A-Z]{16}|xox[baprs]-[\w-]{10,})"), R),
    # A test password named in prose, after its assignment was redacted:
    # this repo's are shaped like scratch-admin-pw.
    ("password", re.compile(r"\b[a-z0-9]+(?:-[a-z0-9]+)*-pw(?:-[a-z0-9]+)?\b"), R),
]
_SECRET_NAMES = re.compile(r"^(?:[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|API_KEY)[A-Z0-9_]*)$")


def redact(text: str, *, secrets: Iterable[str], email: str | None) -> tuple[str, Counter]:
    """`text` with everything sensitive replaced, and what was found, by kind."""
    found: Counter = Counter()
    for secret in secrets:
        if len(secret) >= 6 and secret in text:
            found["secret from .env"] += text.count(secret)
            text = text.replace(secret, R)
    if email and email in text:
        found["author email"] += text.count(email)
        text = text.replace(email, "[REDACTED-EMAIL]")
    for kind, pattern, replacement in RULES:
        text, n = pattern.subn(replacement, text)
        if n:
            found[kind] += n
    return text, found


def local_secrets() -> list[str]:
    """The values of secret-looking variables in .env and the environment."""
    values = {value for name, value in os.environ.items() if _SECRET_NAMES.match(name)}
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            name, _, value = line.partition("=")
            if _SECRET_NAMES.match(name.strip()):
                values.add(value.strip().strip("'\""))
    return sorted((v for v in values if v), key=len, reverse=True)


def author_email() -> str | None:
    result = subprocess.run(["git", "config", "user.email"], cwd=ROOT,
                            capture_output=True, text=True)
    return result.stdout.strip() or None


def redact_text(text: str) -> tuple[str, Counter]:
    """`redact` with this machine's .env secrets and git email."""
    return redact(text, secrets=local_secrets(), email=author_email())


def _staged() -> list[tuple[str, str]]:
    """Each staged transcript, as (path, staged content)."""
    names = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "--",
         "docs/transcripts"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    return [(name, subprocess.run(["git", "show", f":{name}"], cwd=ROOT,
                                  capture_output=True, text=True).stdout) for name in names]


def _summary(found: Counter) -> str:
    return ", ".join(f"{n} {kind}" for kind, n in found.most_common())


def main(argv: list[str]) -> int:
    check = "--check" in argv or "--staged" in argv
    if "--staged" in argv:
        files = _staged()
    else:
        paths = [Path(a) for a in argv if not a.startswith("--")] or sorted(TRANSCRIPTS.glob("*.md"))
        files = [(str(path), path.read_text(encoding="utf-8")) for path in paths]
    secrets, email = local_secrets(), author_email()
    dirty = 0
    for name, text in files:
        redacted, found = redact(text, secrets=secrets, email=email)
        if not found:
            continue
        dirty += 1
        if check:
            print(f"needs redacting: {name}: {_summary(found)}")
        else:
            Path(name).write_text(redacted, encoding="utf-8")
            print(f"redacted: {name}: {_summary(found)}")
    if check and dirty:
        print("Run: python3 scripts/redact_transcripts.py, then stage the transcripts again.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
