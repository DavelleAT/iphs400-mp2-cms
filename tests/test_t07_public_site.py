"""T07: Public site pages (issue #8).

The live public pages sit at the same paths `cms publish` will export them to,
so every link between them is relative and works in both places.
"""
from __future__ import annotations

import re
from posixpath import dirname, join, normpath

import pytest
from fastapi.testclient import TestClient

from tests.conftest import backdate, post_form
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import REPORT, create_report
from tests.test_t05_report_files import PDF, pdf, post_with_file, reports_file


def published_bite(c: TestClient, **override) -> str:
    bite = create_bite(c, **override)
    assert post_form(c, f"/admin/data-bites/{bite}/publish", {}).status_code == 303
    return bite


def test_visitor_reads_a_published_data_bite(client_as, client):
    published_bite(client_as("editor"))

    response = client.get("/data-bites/fall-enrollment.html")
    assert response.status_code == 200
    assert BITE["title"] in response.text
    # The Markdown body is rendered, not shown raw.
    assert "<strong>1,745</strong>" in response.text


def test_a_draft_data_bite_has_no_public_page(client_as, client):
    analyst = client_as("editor")
    bite = published_bite(analyst)
    create_bite(analyst, slug="unreleased", title="Unreleased count")

    assert client.get("/data-bites/unreleased.html").status_code == 404
    assert client.get("/data-bites/no-such-bite.html").status_code == 404
    # Unpublishing takes the page down again.
    post_form(analyst, f"/admin/data-bites/{bite}/unpublish", {})
    assert client.get("/data-bites/fall-enrollment.html").status_code == 404


def test_visitor_lists_published_data_bites_newest_first(client_as, client):
    analyst = client_as("editor")
    older = published_bite(analyst)
    backdate("data_bites", older)
    published_bite(analyst, slug="spring-survey", title="Spring survey results")
    create_bite(analyst, slug="unreleased", title="Unreleased count")

    page = client.get("/data-bites/index.html")
    assert page.status_code == 200
    assert page.text.index("Spring survey results") < page.text.index(BITE["title"])
    # Each links to its page, relative to the data-bites/ folder it sits in.
    assert 'href="../data-bites/spring-survey.html"' in page.text
    assert "Unreleased count" not in page.text and "unreleased" not in page.text
    assert client.get("/data-bites/").text == page.text


def published_report(director: TestClient, **override) -> str:
    rid = create_report(director, **override)
    assert post_form(director, f"/admin/reports/{rid}/publish", {}).status_code == 303
    return rid


def test_visitor_reads_a_published_report_and_downloads_its_file(client_as, client):
    director = client_as("admin")
    rid = published_report(director)
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT,
                          pdf("Factbook 2026.pdf")).status_code == 303

    page = client.get("/reports/factbook.html")
    assert page.status_code == 200
    assert REPORT["title"] in page.text and "<strong>program</strong>" in page.text
    assert 'href="../reports/files/factbook.pdf"' in page.text

    download = client.get("/reports/files/factbook.pdf")
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-type"] == "application/pdf"


def test_a_published_report_with_no_file_has_no_download_link(client_as, client):
    published_report(client_as("admin"))

    page = client.get("/reports/factbook.html")
    assert page.status_code == 200 and "files/" not in page.text
    assert client.get("/reports/files/factbook.pdf").status_code == 404


def test_no_download_link_when_the_stored_file_is_gone(client_as, client):
    """e.g. uploads/ was wiped but cms.db kept: no link to a 404."""
    director = client_as("admin")
    rid = published_report(director)
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT, pdf()).status_code == 303
    reports_file(rid).unlink()

    page = client.get("/reports/factbook.html")
    assert page.status_code == 200 and "files/" not in page.text
    assert client.get("/reports/files/factbook.pdf").status_code == 404


def test_a_draft_report_and_its_file_are_not_public(client_as, client):
    director, analyst = client_as("admin"), client_as("editor")
    assert post_with_file(analyst, "/admin/reports", {**REPORT, "slug": "cds-draft"},
                          pdf()).status_code == 303
    assert client.get("/reports/cds-draft.html").status_code == 404
    assert client.get("/reports/files/cds-draft.pdf").status_code == 404

    rid = published_report(director)
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT, pdf()).status_code == 303
    post_form(director, f"/admin/reports/{rid}/unpublish", {})
    assert client.get("/reports/factbook.html").status_code == 404
    assert client.get("/reports/files/factbook.pdf").status_code == 404


def test_visitor_lists_published_reports_by_title(client_as, client):
    director = client_as("admin")
    published_report(director)
    published_report(director, slug="cds", title="Common Data Set 2025-26")
    create_report(director, slug="survey-calendar", title="Survey Calendar (draft)")

    page = client.get("/reports/index.html")
    assert page.status_code == 200
    content = page.text.split('<main id="main">')[1]  # the skip link's target since T19
    assert content.index("Common Data Set") < content.index(REPORT["title"])
    assert 'href="../reports/cds.html"' in content
    assert "Survey Calendar" not in page.text and "survey-calendar" not in page.text
    assert client.get("/reports/").text == page.text


def nav(html: str) -> str:
    """The page's site navigation, as HTML."""
    start = html.index('<nav class="nav-site"')
    return html[start:html.index("</nav>", start)]


def test_navigation_on_every_page_lists_only_published_reports(client_as, client):
    director = client_as("admin")
    published_report(director)
    create_report(director, slug="survey-calendar", title="Survey Calendar (draft)")
    published_bite(director)

    for path, root in [("/", ""), ("/index.html", ""), ("/data-bites/index.html", "../"),
                       ("/data-bites/fall-enrollment.html", "../"),
                       ("/reports/index.html", "../"), ("/reports/factbook.html", "../")]:
        links = nav(client.get(path).text)
        assert f'href="{root}reports/factbook.html"' in links, path
        assert REPORT["title"] in links, path
        assert "survey-calendar" not in links and "Survey Calendar" not in links, path
        # Built from Reports only: no Data Bite reaches the navigation.
        assert BITE["title"] not in links, path


# An explicit external link, which the rule lets be absolute (T14): an <a>'s
# https: or mailto: href. It leaves the site, so it is not followed.
EXTERNAL = re.compile(r"(?:https:|mailto:)", re.I)


def crawl(client: TestClient) -> dict[str, bytes]:
    """Every public page and file a visitor can reach by following links from
    the home page, or from 404.html, where a missed link lands, by path.
    Follows the stylesheet's url()s too, to its fonts (T19), and the search
    form's action and what search.js fetches, the index (T20). Fails on a broken
    link, and on any link but an <a>'s https: or mailto: that isn't relative:
    root-absolute, any other scheme, or any absolute src. The one <base>
    allowed is 404.html's (ADR-007)."""
    seen, queue = {}, ["/index.html", "/404.html"]
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        response = client.get(path)
        assert response.status_code == 200, f"broken link to {path}"
        seen[path] = response.content
        if path.endswith(".css"):
            found = [("url", "url", link) for link in re.findall(r'url\("([^"]+)"\)', response.text)]
        elif path.endswith(".html"):
            found = re.findall(r'<(\w+)\b[^>]*?\b(href|src|action)="([^"]+)"', response.text)
        elif path.endswith(".js"):
            # Relative to the page that runs it, search.html, beside it.
            found = [("fetch", "fetch", link) for link in re.findall(r'fetch\("([^"]+)"\)', response.text)]
        else:
            continue
        for tag, attribute, link in found:
            if tag == "a" and attribute == "href" and EXTERNAL.match(link):
                continue
            if tag == "base":
                assert path == "/404.html", (path, link)
                continue
            assert not link.startswith("/") and not re.match(r"[a-z][a-z0-9+.-]*:", link, re.I), (
                path, link)
            link = link.partition("#")[0]  # "#main", the skip link, is this page
            if link:
                queue.append(normpath(join(dirname(path), link)))
    return seen


# What a_site_with_drafts puts in its drafts, and nowhere else.
DRAFT_LEAKS = (b"Unreleased enrollment", b"unreleased-bite", b"Draft CDS",
               b"draft-cds", b"unreleased-cds", b"DRAFT-MARKER")


def a_site_with_drafts(director: TestClient, analyst: TestClient) -> None:
    """Setup: a published Data Bite and a published Report with its file,
    beside a draft Data Bite and a draft Report with its own file."""
    published_bite(analyst)
    create_bite(analyst, slug="unreleased-bite", title="Unreleased enrollment count")
    rid = published_report(director)
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT, pdf()).status_code == 303
    assert post_with_file(analyst, "/admin/reports",
                          {**REPORT, "slug": "draft-cds", "title": "Draft CDS"},
                          pdf("unreleased-cds.pdf", PDF + b"% DRAFT-MARKER\n%%EOF\n")
                          ).status_code == 303


def test_no_draft_is_reachable_anywhere_on_the_public_site(client_as, client):
    a_site_with_drafts(client_as("admin"), client_as("editor"))

    site = crawl(client)
    assert {"/data-bites/fall-enrollment.html", "/reports/factbook.html",
            "/reports/files/factbook.pdf", "/data-bites/index.html",
            "/reports/index.html", "/style.css"} <= set(site)
    for path, content in site.items():
        for leak in DRAFT_LEAKS:
            assert leak not in content, (path, leak)


@pytest.mark.parametrize("path, item", [("/admin/data-bites", BITE), ("/admin/reports", REPORT)])
def test_the_slug_index_is_rejected_because_it_is_the_list_page(client_as, path, item):
    """data-bites/index.html and reports/index.html are the list pages."""
    response = post_form(client_as("editor"), path, {**item, "slug": "index"})
    assert response.status_code == 400
    assert "index is reserved" in response.text


def test_script_in_a_body_is_inert_on_the_public_pages(client_as, client):
    director = client_as("admin")
    payload = 'Hi <script>alert(1)</script> <img src="x.png" onerror="alert(2)">'
    published_bite(director, body=payload)
    published_report(director, body=payload)

    for path in ("/data-bites/fall-enrollment.html", "/reports/factbook.html"):
        html = client.get(path).text
        assert "<script>alert" not in html and "onerror" not in html, path
