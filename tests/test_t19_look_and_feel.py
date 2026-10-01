"""T19: Public site look and feel (issue #23, spec #22, ADR-007).

The public site has its own stylesheet and self-hosted fonts, served and
exported at the same relative paths, and the admin console keeps its own.
Every public page shares one layout: numbered nav, a title field, ISO dates,
and a 404.html that works at any depth once CMS_BASE_PATH is set.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import public_site, settings
from app.publish import render_site
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import REPORT
from tests.test_t05_report_files import pdf, post_with_file
from tests.test_t07_public_site import nav, published_bite, published_report
from tests.test_t08_publish import exported
from tests.test_t12_site_preview import preview

FONTS = sorted(path.name for path in (settings.STATIC / "fonts").glob("*.woff2"))
PUBLIC_PAGES = ["/", "/data-bites/index.html", "/data-bites/fall-enrollment.html",
                "/reports/index.html", "/reports/factbook.html", "/404.html"]


def a_published_site(director: TestClient) -> None:
    published_bite(director)
    rid = published_report(director)
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT, pdf()).status_code == 303
    published_report(director, slug="cds", title="Common Data Set 2025-26")


def stylesheets(html: str) -> list[str]:
    return re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)


# Stylesheets and fonts

def test_the_app_serves_the_stylesheet_and_its_fonts(client):
    css = client.get("/style.css")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    assert css.text == (settings.STATIC / "site.css").read_text()
    assert FONTS, "no fonts in static/fonts"
    for name in FONTS:
        assert f'url("fonts/{name}")' in css.text, name
        font = client.get(f"/fonts/{name}")
        assert font.status_code == 200 and font.headers["content-type"] == "font/woff2", name
        assert font.content == (settings.STATIC / "fonts" / name).read_bytes()


@pytest.mark.parametrize("path", ["/fonts/nope.woff2", "/fonts/..%2Fsite.css", "/fonts/"])
def test_only_the_sites_own_fonts_are_served(client, path):
    assert client.get(path).status_code == 404


def test_publish_writes_the_stylesheet_fonts_and_licences_and_404(client_as, tmp_path):
    a_published_site(client_as("admin"))
    site = exported(render_site(tmp_path / "site"))
    assert site["style.css"] == (settings.STATIC / "site.css").read_bytes()
    for name in FONTS:
        assert site[f"fonts/{name}"] == (settings.STATIC / "fonts" / name).read_bytes()
    assert {"fonts/OFL-atkinson-hyperlegible-next.txt",
            "fonts/OFL-atkinson-hyperlegible-mono.txt", "404.html"} <= set(site)


def test_public_site_css_is_gone_from_python():
    assert not hasattr(public_site, "CSS")


@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_a_public_page_links_only_the_sites_stylesheet(client_as, client, path):
    a_published_site(client_as("admin"))
    page = client.get(path).text
    root = "../" * path.removeprefix("/").count("/")
    assert stylesheets(page) == [f"{root}style.css"] or path == "/404.html", stylesheets(page)
    assert "admin.css" not in page


@pytest.mark.parametrize("path", ["/login", "/admin", "/admin/content", "/admin/users",
                                  "/admin/data-bites", "/admin/data-bites/{bid}",
                                  "/admin/reports"])
def test_an_admin_page_links_only_the_consoles_stylesheet(client_as, path):
    director = client_as("admin")
    page = director.get(path.format(bid=create_bite(director))).text
    # An edit page's Site preview is a public page, in an escaped srcdoc.
    assert stylesheets(page) == ["/admin.css"]


def test_the_consoles_stylesheet_has_the_editors_rules_and_the_sites_has_no_admin_rules(client):
    # T21 (spec #25) gave the console the site's fonts, copied into its own
    # stylesheet (tests/test_t21_console_shell.py); the Editor's rules stay.
    admin = client.get("/admin.css")
    assert admin.status_code == 200 and admin.headers["content-type"].startswith("text/css")
    assert ".admin-editor-toolbar" in admin.text and ".chart-svg-phone" in admin.text
    assert "site-preview-banner" not in admin.text
    site = client.get("/style.css").text
    assert ".admin-" not in site and "body:has(" not in site


def test_the_stylesheet_has_dark_mode_print_reduced_motion_and_a_focus_ring(client):
    css = client.get("/style.css").text
    for needle in ("@media (prefers-color-scheme: dark)", "@media print",
                   "@media (prefers-reduced-motion: reduce)", ":focus-visible", ".skip-link"):
        assert needle in css, needle
    # A Chart is capped at the width it is drawn for.
    assert re.search(r"\.chart-figure \{[^}]*max-width: 40rem", css)


# The layout

@pytest.mark.parametrize("path", PUBLIC_PAGES)
def test_every_public_page_has_the_layout(client_as, client, path):
    a_published_site(client_as("admin"))
    page = client.get(path).text
    assert '<a class="skip-link" href="#main">Skip to content</a>' in page
    assert '<header class="header-site">' in page and '<main id="main">' in page
    assert '<footer class="footer-site field-site">' in page
    assert page.count("<h1") == 1


def test_the_nav_numbers_reports_in_title_order_then_data_bites(client_as, client):
    a_published_site(client_as("admin"))
    links = re.findall(r'<a href="([^"]+)"[^>]*><span class="text-mono">(\d\d)</span>([^<]+)</a>',
                       nav(client.get("/").text))
    assert links == [("reports/cds.html", "01", "Common Data Set 2025-26"),
                     ("reports/factbook.html", "02", REPORT["title"]),
                     ("data-bites/index.html", "03", "Data Bites")]


@pytest.mark.parametrize("path, current, marked", [
    ("/reports/factbook.html", "reports/factbook.html", "page"),
    ("/data-bites/index.html", "data-bites/index.html", "page"),
    # A Data Bite is in the Data Bites section, but isn't that page.
    ("/data-bites/fall-enrollment.html", "data-bites/index.html", "true"),
])
def test_the_nav_marks_where_the_visitor_is(client_as, client, path, current, marked):
    a_published_site(client_as("admin"))
    shown = nav(client.get(path).text)
    assert re.findall(r'href="\.\./([^"]+)" aria-current="(\w+)"', shown) == [(current, marked)]


def test_the_home_page_marks_nothing_in_the_nav(client_as, client):
    a_published_site(client_as("admin"))
    assert "aria-current" not in nav(client.get("/").text)


def test_a_data_bite_has_its_title_and_facts_on_the_field(client_as, client):
    published_bite(client_as("editor"))
    page = client.get("/data-bites/fall-enrollment.html").text
    field = page[page.index('<div class="title-item">'):page.index('<div class="layout-wrap">', page.index("</dl>"))]
    assert '<nav class="nav-breadcrumb text-label" aria-label="Breadcrumb">' in field
    assert '<a href="../index.html">Home</a> / <a href="../data-bites/index.html">Data Bites</a>' in field
    assert f"<h1>{BITE['title']}</h1>" in field
    assert re.search(r'<dt>Published</dt><dd><span class="text-mono"><time datetime="(\d{4}-\d\d-\d\d)">\1</time>',
                     field)
    assert "<dt>Type</dt><dd>Data Bite</dd>" in field
    # The body below it, at the measure.
    assert '<article class="body-item"><div class="content-body">' in page


def test_a_report_has_its_pdf_in_its_facts(client_as, client):
    a_published_site(client_as("admin"))
    page = client.get("/reports/factbook.html").text
    facts = page[page.index('<dl class="meta-item'):page.index("</dl>")]
    assert "<dt>Type</dt><dd>Report</dd>" in facts
    assert ('<dt>PDF</dt><dd><a class="report-download" href="../reports/files/factbook.pdf"'
            ' download="factbook-2026.pdf">Download factbook-2026.pdf</a></dd>') in facts
    # A Report with no file has no PDF fact.
    assert "<dt>PDF</dt>" not in client.get("/reports/cds.html").text


def test_public_dates_are_iso(client_as, client):
    a_published_site(client_as("admin"))
    for path in ["/", "/data-bites/index.html", "/reports/index.html",
                 "/data-bites/fall-enrollment.html", "/reports/factbook.html"]:
        dates = re.findall(r'<time datetime="([^"]*)">([^<]*)</time>', client.get(path).text)
        assert dates, path
        for machine, shown in dates:
            assert re.fullmatch(r"\d{4}-\d\d-\d\d", shown) and shown == machine, (path, shown)


# 404.html

def test_404_without_a_base_path_inlines_its_styles_and_links_from_the_root(client, monkeypatch):
    monkeypatch.setattr(settings, "BASE_PATH", "")
    page = client.get("/404.html").text
    assert "<base" not in page and stylesheets(page) == []
    assert "<style>" in page and '@font-face { font-family: "Atkinson Next"' in page
    assert '<a href="index.html">Go to the home page</a>' in page
    assert "Page not found" in page


@pytest.mark.parametrize("configured", ["https://example.github.io/cms/",
                                        "https://example.github.io/cms"])
def test_404_with_a_base_path_is_based_at_the_site_root(client, monkeypatch, configured):
    monkeypatch.setattr(settings, "BASE_PATH", configured)
    page = client.get("/404.html").text
    assert re.findall(r'<base href="([^"]+)">', page) == ["https://example.github.io/cms/"]
    assert stylesheets(page) == ["style.css"] and "<style>" not in page
    # "#main" would resolve against the <base>, the site's root: the skip
    # link names this page at its own path instead.
    assert '<a class="skip-link" href="404.html#main">Skip to content</a>' in page
    assert 'href="#' not in page


@pytest.mark.parametrize("configured", ["/cms/", "cms/", "//example.github.io/cms/"])
def test_a_base_path_that_is_not_a_url_is_ignored(client, monkeypatch, configured):
    monkeypatch.setattr(settings, "BASE_PATH", configured)
    page = client.get("/404.html").text
    assert "<base" not in page and "<style>" in page


def test_the_only_base_in_the_export_is_404s_and_no_link_is_root_absolute(
        client_as, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BASE_PATH", "https://example.github.io/cms/")
    a_published_site(client_as("admin"))
    create_bite(client_as("editor"), slug="unreleased-bite", title="Unreleased")
    site = exported(render_site(tmp_path / "site"))
    pages = {path: content.decode() for path, content in site.items() if path.endswith(".html")}
    assert {path for path, html in pages.items() if "<base" in html} == {"404.html"}
    for path, html in pages.items():
        for tag, link in re.findall(r'<(\w+)\b[^>]*?\b(?:href|src)="([^"]+)"', html):
            assert not link.startswith("/"), (path, link)
            if tag not in ("a", "base"):
                assert "://" not in link, (path, link)


def test_a_preview_has_no_skip_link_but_has_its_banner(client_as):
    page = preview(client_as("editor"), "data-bites", **BITE).text
    assert "skip-link" not in page.split("</head>")[1].split("</header>")[0]
    assert '<p class="site-preview-banner" role="note">Draft preview, not published</p>' in page


def test_the_site_preview_serves_the_fonts(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    for name in FONTS:
        response = analyst.get(f"/admin/data-bites/{bid}/preview/fonts/{name}")
        assert response.status_code == 200 and response.headers["content-type"] == "font/woff2"


def test_each_font_has_its_licence_beside_it():
    fonts = Path(settings.STATIC / "fonts")
    for family in ("next", "mono"):
        assert (fonts / f"OFL-atkinson-hyperlegible-{family}.txt").is_file()
        assert any(family in name for name in FONTS)
