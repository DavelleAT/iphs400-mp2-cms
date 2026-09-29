"""`cms publish`: write the public site into site/ as plain HTML.

The pages and files come from app.public_site, the same ones the app serves,
at the same paths, so the export is the live public site rather than a second
rendering of it. That module reads only published content and links only
relatively, which gives the two rules the rubric checks here:

  1. Only PUBLISHED content is written here. A draft that reaches site/ is a bug.
  2. Every href and src is RELATIVE ("style.css", "reports/x.html"), never
     root-absolute ("/style.css"), because Pages serves this from a subfolder.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from app import public_site, settings


def render_site(out: Path | None = None) -> Path:
    """Regenerate `out` (site/ by default) from scratch, so a page taken down
    since the last publish is gone from it too."""
    out = out or settings.SITE
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    # UTF-8, as the app serves them, whatever this machine's locale.
    (out / "style.css").write_text(public_site.CSS, encoding="utf-8")
    for page in public_site.pages():
        _target(out, page.path).write_text(page.render(), encoding="utf-8")
    for path, stored in public_site.files().items():
        shutil.copyfile(stored, _target(out, path))
    return out


def _target(out: Path, path: str) -> Path:
    """Where `path` in the site goes under `out`, its folder made."""
    target = out / path
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
