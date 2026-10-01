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
The one exception is a Site preview (`data_bite_preview`, `report_preview`),
which the admin console renders for one item, as if it were published, and
which is never written to the site.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

from markupsafe import Markup

from app import data_bites, reports, settings, site_links
from app.templating import templates

# The site's stylesheet and the fonts it loads, with their licences (ADR-007).
STYLESHEET = settings.STATIC / "site.css"
FONTS = settings.STATIC / "fonts"
# What each kind of asset is served as, by extension; never sniffed.
ASSET_TYPES = {".css": "text/css; charset=utf-8", ".woff2": "font/woff2",
               ".txt": "text/plain; charset=utf-8"}
RECENT_DATA_BITES = 5  # on the home page; the rest are on the Data Bites list
# A new item's slug in its Site preview, which only its paths use.
_UNSAVED_SLUG = "untitled"


def data_bite_path(slug: str) -> str:
    return f"data-bites/{slug}.html"


def data_bite_image_path(slug: str, name: str) -> str:
    return f"images/data-bites/{slug}/{name}"


def report_path(slug: str) -> str:
    return f"reports/{slug}.html"


def report_file_path(slug: str) -> str:
    # .pdf, not the upload's own extension: a Report's file is always a PDF (T05).
    return f"reports/files/{slug}.pdf"


def report_image_path(slug: str, name: str) -> str:
    return f"images/reports/{slug}/{name}"


@dataclass(frozen=True)
class Page:
    path: str      # where the page sits in the site, relative to its root
    template: str
    context: dict = field(default_factory=dict)
    # The chart images its body may show, {name: path in the site}.
    images: dict[str, str] = field(default_factory=dict)
    # The Reports in its navigation; None for the published ones.
    nav_reports: list[Mapping] | None = None
    # Where each site link its body may have leads, {site reference: path in
    # the site}; None for the published items' (published_links).
    links: Mapping[str, str] | None = None

    def render(self) -> str:
        return self._render(preview_base=None)

    def render_preview(self, at: str) -> str:
        """The page as a Site preview, served from `at`: the root of the
        preview's own copy of the site, an admin path ending in "/". Its links
        stay relative, as in the export, and a <base> puts the page at its
        path under `at`, where they reach the preview's stylesheet and files.
        It shows the "Draft preview, not published" banner."""
        return self._render(preview_base=f"{at}{self.path}")

    def _render(self, *, preview_base: str | None) -> str:
        root = "../" * self.path.count("/")

        def image_src(name: str) -> str | None:
            path = self.images.get(name)
            return None if path is None else f"{root}{path}"

        links = published_links() if self.links is None else self.links

        def link_href(reference: str) -> str | None:
            path = links.get(reference)
            return None if path is None else f"{root}{path}"

        nav_reports = reports.list_published() if self.nav_reports is None else self.nav_reports
        return templates.env.get_template(self.template).render(
            image_src=image_src, link_href=link_href,
            title=settings.SITE_TITLE, root=root, page_path=self.path,
            home_path=f"{root}index.html", nav_reports=nav_reports,
            data_bite_path=data_bite_path, report_path=report_path,
            report_file_path=report_file_path, report_format=report_format,
            preview_base=preview_base, **self.context)


def published_links() -> dict[str, str]:
    """Where a site link to each published item leads, {site reference: path
    in the site}. A draft, deleted, or unknown one is not here, so a link to
    it is its text."""
    return {**{site_links.reference("data-bite", bite["ref"]): data_bite_path(bite["slug"])
               for bite in data_bites.list_published()},
            **{site_links.reference("report", found["ref"]): report_path(found["slug"])
               for found in reports.list_published()}}


def _linked_as_published(page: Page, kind: str, item: Mapping) -> Page:
    """A Site preview's page, whose item's own site links resolve as if it
    were published; a new item has no ref yet."""
    links = published_links()
    if item.get("ref"):
        links[site_links.reference(kind, item["ref"])] = page.path
    return replace(page, links=links)


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


def _data_bite_page(bite: Mapping) -> Page:
    return Page(data_bite_path(bite["slug"]), "public/data_bite.html",
                {"page_title": bite["title"], "bite": bite,
                 "description": bite["summary"], "og_type": "article"},
                images={name: data_bite_image_path(bite["slug"], name)
                        for name in _stored_images(data_bites, bite)})


def _stored_images(module: ModuleType, item: Mapping) -> dict[str, Path]:
    """A Data Bite's or Report's chart images (`module` is its type's),
    {name: where it is stored}; none for one not yet saved."""
    return {} if item["id"] is None else module.images(item["id"])


def data_bite_files(bite: Mapping) -> dict[str, Path]:
    """The files a Data Bite's page links to, its chart images, as {path in
    the site: where it is stored}."""
    return {data_bite_image_path(bite["slug"], name): path
            for name, path in _stored_images(data_bites, bite).items()}


def data_bite_image(slug: str, name: str) -> Path | None:
    """Where a published Data Bite's chart image, at
    data_bite_image_path(slug, name) in the site, is stored. None for a
    draft, no such image, or no such Data Bite."""
    bite = data_bites.get_published(slug)
    return None if bite is None else data_bites.images(bite["id"]).get(name)


def report_list() -> Page:
    return Page("reports/index.html", "public/reports.html",
                {"page_title": "Reports", "reports": reports.list_published()})


def _stored_file(report: Mapping) -> Path | None:
    """Where the Report's file is stored, if it has one and it is there."""
    if report["file_name"] is None:
        return None
    stored = reports.file_path(report["id"])
    return stored if stored.is_file() else None


def report_format(report: Mapping) -> str:
    """How a Report is offered, for the Reports table: PDF if its file can be
    downloaded, otherwise WEB, its page alone."""
    return "PDF" if _stored_file(report) is not None else "WEB"


def report(slug: str) -> Page | None:
    """A published Report's page, linking its file only if that can be
    downloaded; None for a draft or no such Report."""
    found = reports.get_published(slug)
    return None if found is None else _report_page(found)


def _report_page(found: Mapping) -> Page:
    return Page(report_path(found["slug"]), "public/report.html",
                {"page_title": found["title"], "report": found,
                 "description": found["summary"], "og_type": "article",
                 "has_file": _stored_file(found) is not None},
                images={name: report_image_path(found["slug"], name)
                        for name in _stored_images(reports, found)})


def report_image_files(found: Mapping) -> dict[str, Path]:
    """A Report's chart images, as {path in the site: where it is stored}."""
    return {report_image_path(found["slug"], name): path
            for name, path in _stored_images(reports, found).items()}


def report_pdf_file(found: Mapping) -> dict[str, Path]:
    """A Report's file, if its page links to it (it can be downloaded), as
    {path in the site: where it is stored}; empty if not."""
    stored = _stored_file(found)
    return {report_file_path(found["slug"]): stored} if stored else {}


def report_files(found: Mapping) -> dict[str, Path]:
    """Every file a Report's page links to, as {path in the site: where it is
    stored}."""
    return {**report_image_files(found), **report_pdf_file(found)}


def report_file(slug: str) -> tuple[Path, str] | None:
    """A published Report's attached file, at report_file_path(slug) in the
    site, as (where it is stored, its display name). None for a draft, a
    Report with no file, or no such Report."""
    found = reports.get_published(slug)
    stored = found and _stored_file(found)
    return (stored, found["file_name"]) if stored else None


def report_image(slug: str, name: str) -> Path | None:
    """Where a published Report's chart image, at report_image_path(slug,
    name) in the site, is stored. None for a draft, no such image, or no such
    Report."""
    found = reports.get_published(slug)
    return None if found is None else reports.images(found["id"]).get(name)


def not_found() -> Page:
    """404.html, which GitHub Pages serves at whatever missing path was asked
    for, at any depth, so its relative links can't be trusted (ADR-007). It
    carries a <base> at the deployed site's root, CMS_BASE_PATH. Without one
    (local use) it inlines its stylesheet and links as from the site's root,
    which is right for a miss at the top level."""
    base = settings.BASE_PATH
    if not base.startswith(("https://", "http://")):
        base = ""  # a path alone would be a root-absolute link (ADR-001)
    elif not base.endswith("/"):
        base += "/"  # else the <base> is the site's parent folder
    return Page("404.html", "public/not_found.html",
                {"page_title": "Page not found", "site_base": base,
                 "inline_css": None if base else Markup(STYLESHEET.read_text(encoding="utf-8"))})


def pages() -> list[Page]:
    """Every page of the site: what `cms publish` writes."""
    return [home(), data_bite_list(), report_list(), not_found(),
            *map(_data_bite_page, data_bites.list_published()),
            *map(_report_page, reports.list_published())]


def assets() -> dict[str, Path]:
    """The stylesheet and its fonts, as {path in the site: where it is
    stored}: style.css, and fonts/ beside it with the fonts' OFL licences."""
    return {"style.css": STYLESHEET,
            **{f"fonts/{font.name}": font for font in sorted(FONTS.iterdir())
               if font.suffix in ASSET_TYPES}}


def files() -> dict[str, Path]:
    """Every file the site's pages link to besides assets(), as {path in the
    site: where it is stored}: the published Data Bites' and Reports' chart
    images, and the published Reports' files."""
    found: dict[str, Path] = {}
    for bite in data_bites.list_published():
        found.update(data_bite_files(bite))
    for report in reports.list_published():
        found.update(report_files(report))
    return found


# Site previews: one item's page, as if it were published, with unsaved edits.

def _as_if_published(form: Mapping[str, str], saved: sqlite3.Row | None) -> dict:
    """The item a Site preview shows: `saved` (None for a new item, dated now)
    with `form`'s unsaved title, Summary (as it would be saved, but not
    refused for its length), and body, published. It keeps the saved slug:
    an unsaved slug would change only paths, which no reader sees, and with
    the saved one the preview finds the item's files where it puts them."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    item = dict(saved) if saved is not None else {
        "id": None, "slug": _UNSAVED_SLUG, "file_name": None,
        "created_at": now, "updated_at": now}
    return {**item, "title": form["title"].strip(), "summary": " ".join(form["summary"].split()),
            "body": form["body"], "status": "published"}


def data_bite_preview(form: Mapping[str, str], saved: sqlite3.Row | None) -> Page:
    """The Site preview of `form`'s edits to the Data Bite `saved` (None on
    the create page). Render it with Page.render_preview."""
    bite = _as_if_published(form, saved)
    return _linked_as_published(_data_bite_page(bite), "data-bite", bite)


def report_preview(form: Mapping[str, str], saved: sqlite3.Row | None) -> Page:
    """As data_bite_preview, for a Report. The Report is in the navigation,
    in title order, as if published; every other draft is not."""
    report = _as_if_published(form, saved)
    others = [found for found in reports.list_published() if found["id"] != report["id"]]
    # The order reports.list_published gives (title, then id), the new one last.
    nav = sorted([*others, report],
                 key=lambda found: (found["title"], found["id"] is None, found["id"] or 0))
    return _linked_as_published(replace(_report_page(report), nav_reports=nav),
                                "report", report)
