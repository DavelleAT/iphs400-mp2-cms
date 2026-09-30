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

from app import data_bites, reports, settings, site_links
from app.templating import templates

CSS = """/* The public site's one stylesheet, at style.css in the site's root. */
:root { color-scheme: light dark; }
body { font: 16px/1.6 system-ui, sans-serif; margin: 0 auto; max-width: 42rem; padding: 1rem; }
.header-home { font-weight: 700; text-decoration: none; }
.nav-site ul { display: flex; flex-wrap: wrap; gap: 0.25rem 1rem; list-style: none; margin: 0.5rem 0 0; padding: 0; }
main { margin-block: 2rem; }
/* Admin only: the message after a successful save (app.flash). */
.admin-confirmation { background: color-mix(in srgb, #2e7d32 12%, transparent); border-left: 4px solid #2e7d32; margin: 0 0 1.5rem; padding: 0.6rem 0.9rem; }
/* Markdown tables, in a Data Bite's or Report's body. A wide one scrolls
   sideways in its wrapper (app.rendering.TABLE_SCROLL) rather than widening
   the page; on a phone, rather than squeezing its text to a word a line. */
.content-body .content-table-scroll { margin-block: 1rem; overflow-x: auto; }
/* Chart images (app.chart_images) shrink to the column, keeping their shape. */
.content-body img { height: auto; max-width: 100%; }
.content-body table { border-collapse: collapse; }
.content-body th, .content-body td { border: 1px solid color-mix(in srgb, currentColor 30%, transparent); padding: 0.35rem 0.7rem; }
.content-body th { background: color-mix(in srgb, currentColor 8%, transparent); font-weight: 600; }
@media (max-width: 40rem) { .content-body th, .content-body td { min-width: 10ch; } }
/* A Site preview's banner (Page.render_preview); never on a published page. */
.site-preview-banner { background: #fff4ce; border-left: 4px solid #9a6700; color: #4d3800; font-weight: 600; margin: 0 0 1rem; padding: 0.5rem 0.9rem; }
/* Admin only: an edit form's fields beside its Site preview, stacked below
   them on a narrow screen. */
body:has(.admin-site-preview) { max-width: 90rem; }
.admin-content-fields textarea { box-sizing: border-box; width: 100%; }
.admin-site-preview-frame { border: 1px solid color-mix(in srgb, currentColor 30%, transparent); box-sizing: border-box; display: block; height: 75vh; min-height: 24rem; width: 100%; }
.admin-site-preview-frame[data-width="phone"] { max-width: 100%; width: 390px; }
/* Admin only: the Editor (static/editor.js), its toolbar, and the parts of a
   body it can't edit, shown read-only. */
.admin-editor-label { font-weight: 600; margin: 0 0 0.25rem; }
.admin-editor-toolbar { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-bottom: 0.25rem; }
/* The table controls, shown while the cursor is in a table. Not named
   "table": only .content-body's own rules may style tables (T09). */
.admin-editor-cell-tools { display: flex; flex-wrap: wrap; gap: 0.25rem; margin-bottom: 0.25rem; }
.admin-editor-cell-tools[hidden] { display: none; }
.admin-editor-toolbar [aria-pressed="true"] { background: color-mix(in srgb, currentColor 18%, transparent); }
.admin-editor-link { margin-block: 0.25rem; }
.admin-editor-link p { align-items: center; display: flex; flex-wrap: wrap; gap: 0.25rem 0.75rem; margin: 0.25rem 0; }
.admin-editor-link[hidden], .admin-editor-link p[hidden] { display: none; }
/* A site link that won't be a link on the site, marked for the writer. */
.admin-editor-area a[data-link-mark]::after { background: #fff4ce; border-radius: 3px; color: #4d3800; content: attr(data-link-mark); display: inline-block; font-size: 0.75rem; font-style: normal; font-weight: 600; margin-left: 0.3em; padding: 0 0.35em; }
.admin-editor-message { background: color-mix(in srgb, #b3261e 12%, transparent); border-left: 4px solid #b3261e; margin: 0.25rem 0; padding: 0.4rem 0.8rem; }
.admin-editor-message:empty { display: none; }
.admin-editor-area { border: 1px solid color-mix(in srgb, currentColor 30%, transparent); min-height: 16rem; overflow-wrap: anywhere; padding: 0.25rem 0.75rem; }
.admin-editor-locked { background: color-mix(in srgb, currentColor 5%, transparent); border: 1px dashed color-mix(in srgb, currentColor 40%, transparent); margin-block: 0.75rem; padding: 0 0.75rem; }
.admin-editor-locked-note { font-size: 0.875rem; font-style: italic; margin: 0.4rem 0; }
.admin-editor-locked pre { overflow-x: auto; }
@media (min-width: 64rem) {
  .admin-content-editing { align-items: start; display: grid; gap: 0 2rem; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .admin-content-editing .admin-site-preview { position: sticky; top: 1rem; }
}
"""
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
            title=settings.SITE_TITLE, root=root, css_path=f"{root}style.css",
            home_path=f"{root}index.html", nav_reports=nav_reports,
            data_bite_path=data_bite_path, report_path=report_path,
            report_file_path=report_file_path, preview_base=preview_base, **self.context)


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
                {"page_title": bite["title"], "bite": bite},
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


def report(slug: str) -> Page | None:
    """A published Report's page, linking its file only if that can be
    downloaded; None for a draft or no such Report."""
    found = reports.get_published(slug)
    return None if found is None else _report_page(found)


def _report_page(found: Mapping) -> Page:
    return Page(report_path(found["slug"]), "public/report.html",
                {"page_title": found["title"], "report": found,
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


def pages() -> list[Page]:
    """Every page of the site: what `cms publish` writes."""
    return [home(), data_bite_list(), report_list(),
            *map(_data_bite_page, data_bites.list_published()),
            *map(_report_page, reports.list_published())]


def files() -> dict[str, Path]:
    """Every file the site's pages link to besides the stylesheet, as
    {path in the site: where it is stored}: the published Data Bites' and
    Reports' chart images, and the published Reports' files."""
    found: dict[str, Path] = {}
    for bite in data_bites.list_published():
        found.update(data_bite_files(bite))
    for report in reports.list_published():
        found.update(report_files(report))
    return found


# Site previews: one item's page, as if it were published, with unsaved edits.

def _as_if_published(form: Mapping[str, str], saved: sqlite3.Row | None) -> dict:
    """The item a Site preview shows: `saved` (None for a new item, dated now)
    with `form`'s unsaved title and body, published. It keeps the saved slug:
    an unsaved slug would change only paths, which no reader sees, and with
    the saved one the preview finds the item's files where it puts them."""
    item = dict(saved) if saved is not None else {
        "id": None, "slug": _UNSAVED_SLUG, "file_name": None,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}
    return {**item, "title": form["title"].strip(), "body": form["body"],
            "status": "published"}


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
