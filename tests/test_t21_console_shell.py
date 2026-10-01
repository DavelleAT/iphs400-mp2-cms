"""T21: Console shell (issue #26, spec #25).

Every signed-in console page has the slim bar: the IR mark, numbered nav
(Homepage and Users for a Director only) with the current section marked,
who is signed in, "View site ↗", and a Log out form with its CSRF token.
The console's own stylesheet carries the public site's fonts and tokens
without linking the public stylesheet (ADR-007).
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

import pytest
from fastapi.testclient import TestClient

from app import settings
from tests.conftest import csrf_from, post_form
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import create_report

FONTS = sorted(path.name for path in (settings.STATIC / "fonts").glob("*.woff2"))

DIRECTOR_PAGES = ["/admin", "/admin/content", "/admin/data-bites", "/admin/data-bites/new",
                  "/admin/data-bites/{bid}", "/admin/data-bites/{bid}/delete",
                  "/admin/reports", "/admin/reports/new", "/admin/reports/{rid}",
                  "/admin/reports/{rid}/delete", "/admin/users", "/admin/homepage"]
ANALYST_PAGES = ["/admin", "/admin/content", "/admin/data-bites", "/admin/data-bites/new",
                 "/admin/data-bites/{bid}", "/admin/reports", "/admin/reports/new",
                 "/admin/reports/{rid}",
                 "/admin/users", "/admin/homepage"]  # the last two: "Not allowed" (403)


def page(c: TestClient, path: str) -> str:
    bid, rid = create_bite(c), create_report(c)
    return c.get(path.format(bid=bid, rid=rid)).text


def nav(html: str) -> str:
    match = re.search(r'<nav class="nav-console" aria-label="Console">(.*?)</nav>', html, re.S)
    assert match, "no console nav"
    return match.group(1)


def nav_links(html: str) -> list[tuple[str, str, str]]:
    """(number, label, href) for each nav link, in order."""
    return [(number, label, href) for href, number, label in re.findall(
        r'<a href="([^"]+)"[^>]*><span class="text-mono">(\d\d)</span>([^<]+)</a>', nav(html))]


def current(html: str) -> list[str]:
    return re.findall(r'aria-current="page"><span class="text-mono">\d\d</span>([^<]+)<', nav(html))


def logout_form(html: str) -> str:
    match = re.search(r'<form method="post" action="/logout">(.*?)</form>', html, re.S)
    assert match, "no Log out form"
    return match.group(1)


# The bar, on every signed-in page

@pytest.mark.parametrize("path", DIRECTOR_PAGES)
def test_every_director_page_has_the_bar_nav_and_log_out(client_as, path):
    director = client_as("admin")
    html = page(director, path)
    assert nav_links(html) == [
        ("01", "Dashboard", "/admin"), ("02", "Data Bites", "/admin/data-bites"),
        ("03", "Reports", "/admin/reports"), ("04", "Homepage", "/admin/homepage"),
        ("05", "Users", "/admin/users")]
    form = logout_form(html)
    assert f'name="csrf_token" value="{csrf_from(html)}"' in form
    assert ">Log out</button>" in form
    assert '<span class="bar-console-mark" aria-hidden="true">IR</span>' in html
    assert "<b>Console</b>" in html


@pytest.mark.parametrize("path", ANALYST_PAGES)
def test_an_analysts_nav_has_no_homepage_or_users(client_as, path):
    analyst = client_as("editor")
    html = page(analyst, path)
    assert [label for _, label, _ in nav_links(html)] == ["Dashboard", "Data Bites", "Reports"]
    assert "/admin/homepage" not in nav(html) and "/admin/users" not in nav(html)
    assert 'name="csrf_token"' in logout_form(html)


def test_the_not_allowed_page_keeps_the_shell(client_as):
    response = client_as("editor").get("/admin/users")
    assert response.status_code == 403 and "Directors only." in response.text
    assert current(response.text) == [] and logout_form(response.text)


@pytest.mark.parametrize("path, section", [
    ("/admin", "Dashboard"), ("/admin/content", "Dashboard"),
    ("/admin/data-bites", "Data Bites"), ("/admin/data-bites/{bid}", "Data Bites"),
    ("/admin/data-bites/{bid}/delete", "Data Bites"),
    ("/admin/reports", "Reports"), ("/admin/reports/{rid}", "Reports"),
    ("/admin/homepage", "Homepage"), ("/admin/users", "Users")])
def test_the_nav_marks_the_current_section(client_as, path, section):
    assert current(page(client_as("admin"), path)) == [section]


@pytest.mark.parametrize("role, label", [("admin", "Director"), ("editor", "Analyst")])
def test_the_bar_shows_who_is_signed_in_and_the_public_site(client_as, role, label):
    html = client_as(role).get("/admin").text
    assert re.search(rf'<span class="user-console-name">{role} <span class="text-label">'
                     rf'{label}</span></span>', html), html
    assert '<a class="user-console-site" href="/index.html">View site ↗</a>' in html


@pytest.mark.parametrize("path", DIRECTOR_PAGES + ["/login"])
def test_every_console_page_has_a_skip_link_to_its_main(client_as, path):
    html = page(client_as("admin"), path) if path != "/login" else \
        TestClient(client_as("admin").app).get("/login").text
    assert '<a class="link-skip" href="#main">Skip to content</a>' in html
    assert re.search(r'<main id="main"[^>]*>', html)


def test_the_login_page_has_the_bar_but_no_nav_or_log_out(client):
    html = client.get("/login").text
    assert '<span class="bar-console-mark" aria-hidden="true">IR</span>' in html
    assert "nav-console" not in html and 'action="/logout"' not in html


def test_the_confirmation_keeps_its_fixed_text_in_its_new_look(client_as):
    director = client_as("admin")
    assert post_form(director, "/admin/data-bites", BITE).status_code == 303
    html = director.get("/admin/data-bites").text
    assert '<p class="confirmation-console" role="status">' \
           "Data Bite created as a Draft.</p>" in html


# The console's stylesheet

def test_the_consoles_stylesheet_has_the_sites_fonts_and_never_its_stylesheet(client):
    css = client.get("/admin.css").text
    assert FONTS
    for name in FONTS:
        assert f'url("fonts/{name}")' in css, name
        # Relative to /admin.css, which is the public site's /fonts/ route.
        font = client.get(urljoin("/admin.css", f"fonts/{name}"))
        assert font.status_code == 200 and font.headers["content-type"] == "font/woff2"
    assert "@import" not in css and "site.css" not in css and "style.css" not in css
    for needle in ("@media (prefers-color-scheme: dark)", ":focus-visible", ".link-skip",
                   "--color-field: #231443", "--color-citron: #d6f550"):
        assert needle in css, needle


def test_the_consoles_class_names_are_all_prefixed(client):
    css = re.sub(r"/\*.*?\*/", "", client.get("/admin.css").text, flags=re.S)
    classes = set(re.findall(r"\.(-?[a-zA-Z_][\w-]*)", re.sub(r'url\("[^"]*"\)', "", css)))
    assert classes and not [name for name in classes if "-" not in name.strip("-")], classes


@pytest.mark.parametrize("path", DIRECTOR_PAGES + ["/login"])
def test_no_console_page_links_the_public_stylesheet(client_as, path):
    director = client_as("admin")
    html = page(director, path) if path != "/login" else TestClient(director.app).get(path).text
    assert re.findall(r'<link rel="stylesheet" href="([^"]+)"', html) == ["/admin.css"]
