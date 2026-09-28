"""Configuration, read from the environment (never hard-code secrets)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> None:
    """Read KEY=VALUE lines from .env into os.environ. Variables already set in
    the real environment win."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not key or key.startswith("#"):
            continue
        os.environ.setdefault(key, value.strip().strip("'\""))


_load_dotenv(ROOT / ".env")

TEMPLATES = ROOT / "templates"
SITE = ROOT / "site"

SECRET_KEY = os.environ.get("CMS_SECRET_KEY", "dev-only-not-for-production")
SECRET_KEY_IS_PLACEHOLDER = SECRET_KEY in (
    "dev-only-not-for-production", "change-me-to-a-long-random-string")
# A relative CMS_DATABASE is relative to the repo, not the current directory.
DATABASE_PATH = ROOT / os.environ.get("CMS_DATABASE", "cms.db")
SITE_TITLE = os.environ.get("CMS_SITE_TITLE", "My CMS")
# Set this to your Pages URL once you deploy, e.g.
# https://yourname.github.io/iphs400-mp2-cms/
BASE_PATH = os.environ.get("CMS_BASE_PATH", "")
