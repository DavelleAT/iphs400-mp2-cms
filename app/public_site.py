"""The public site: every page a visitor can see, each described by the path
it has in the exported site (e.g. "data-bites/fall-enrollment.html").

The app serves these pages at those same paths (app.routes.public), and
`cms publish` writes them there (app.publish), so the two render one set of pages
rather than two. Pages link to each other relatively, through `root` ("" at
the top of the site, "../" one folder down), so the same HTML works served
from / and exported to a GitHub Pages subfolder. Where each kind of page or
file sits is decided here, by the *_path functions, and nowhere else.

Content is read only through the published-only queries (`list_published`,
`get_published`), so a draft cannot reach a page, a link, or the navigation.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from app import data_bites, reports, settings
from app.templating import templates

CSS = """/* The public site's one stylesheet, at style.css in the site's root. */
:root { color-scheme: light dark; }
body { font: 16px/1.6 system-ui, sans-serif; margin: 0 auto; max-width: 42rem; padding: 1rem; }
.header-home { font-weight: 700; text-decoration: none; }
.nav-site ul { display: flex; flex-wrap: wrap; gap: 0.25rem 1rem; list-style: none; margin: 0.5rem 0 0; padding: 0; }
main { margin-block: 2rem; }
"""
RECENT_DATA_BITES = 5  # on the home page; the rest are on the Data Bites list


def data_bite_path(slug: str) -> str:
    return f"data-bites/{slug}.html"


def report_path(slug: str) -> str:
    return f"reports/{slug}.html"


def report_file_path(slug: str) -> str:
    # .pdf, not the upload's own extension: a Report's file is always a PDF (T05).
    return f"reports/files/{slug}.pdf"


@dataclass(frozen=True)
class Page:
    path: str      # where the page sits in the site, relative to its root
    template: str
    context: dict = field(default_factory=dict)

    def render(self) -> str:
        root = "../" * self.path.count("/")
        return templates.env.get_template(self.template).render(
            title=settings.SITE_TITLE, root=root, css_path=f"{root}style.css",
            home_path=f"{root}index.html", nav_reports=reports.list_published(),
            data_bite_path=data_bite_path, report_path=report_path,
            report_file_path=report_file_path, **self.context)


def home() -> Page:
    return Page("index.html", "public/home.html",
                {"data_bites": data_bites.list_published()[:RECENT_DATA_BITES]})


def data_bite_list() -> Page:
    return Page("data-bites/index.html", "public/data_bites.html",
                {"page_title": "Data Bites", "data_bites": data_bites.list_published()})


def data_bite(slug: str) -> Page | None:
    """A published Data Bite's page; None for a draft or no such Data Bite."""
    bite = data_bites.get_published(slug)
    return None if bite is None else _data_bite_page(bite)


def _data_bite_page(bite: sqlite3.Row) -> Page:
    return Page(data_bite_path(bite["slug"]), "public/data_bite.html",
                {"page_title": bite["title"], "bite": bite})


def report_list() -> Page:
    return Page("reports/index.html", "public/reports.html",
                {"page_title": "Reports", "reports": reports.list_published()})


def _stored_file(report: sqlite3.Row) -> Path | None:
    """Where the Report's file is stored, if it has one and it is there."""
    if report["file_name"] is None:
        return None
    stored = reports.file_path(report["id"])
    return stored if stored.is_file() else None


def report(slug: str) -> Page | None:
    """A published Report's page, linking its file only if that can be
    downloaded; None for a draft or no such Report."""
    found = reports.get_published(slug)
    return None if found is None else _report_page(found)


def _report_page(found: sqlite3.Row) -> Page:
    return Page(report_path(found["slug"]), "public/report.html",
                {"page_title": found["title"], "report": found,
                 "has_file": _stored_file(found) is not None})


def report_file(slug: str) -> tuple[Path, str] | None:
    """A published Report's attached file, at report_file_path(slug) in the
    site, as (where it is stored, its display name). None for a draft, a
    Report with no file, or no such Report."""
    found = reports.get_published(slug)
    stored = found and _stored_file(found)
    return (stored, found["file_name"]) if stored else None


def pages() -> list[Page]:
    """Every page of the site: what `cms publish` writes."""
    return [home(), data_bite_list(), report_list(),
            *map(_data_bite_page, data_bites.list_published()),
            *map(_report_page, reports.list_published())]


def files() -> dict[str, Path]:
    """Every file the site's pages link to besides the stylesheet, as
    {path in the site: where it is stored}: the published Reports' files."""
    stored = {found["slug"]: _stored_file(found) for found in reports.list_published()}
    return {report_file_path(slug): path for slug, path in stored.items() if path}
