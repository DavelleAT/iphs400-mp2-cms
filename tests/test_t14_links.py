"""T14: links to Reports and Data Bites, and the link rule (issue #17).

A site link is stored as `report:<ref>` or `data-bite:<ref>` and resolved
when a page is rendered to the target's page-relative path, only if the
target is published. Every other <a> keeps its href only as `https:` or
`mailto:`; anything else, and a site link that doesn't resolve, renders as
its text. Only `image:<name>` renders an <img>.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import data_bites, public_site, reports
from app.publish import render_site
from tests.conftest import post_form
from tests.test_t03_data_bites import create_bite
from tests.test_t04_reports import create_report
from tests.test_t07_public_site import crawl, published_bite, published_report
from tests.test_t08_publish import exported
from tests.test_t09_tables import content_body
from tests.test_t12_site_preview import preview

BITE_PAGE = "/data-bites/fall-enrollment.html"


def report_link(rid: str) -> str:
    return f"report:{reports.get(int(rid))['ref']}"


def bite_link(bid: str) -> str:
    return f"data-bite:{data_bites.get(int(bid))['ref']}"


def anchors(html: str) -> list[str]:
    """Each <a>'s href in `html` (None for an <a> without one)."""
    return [href or None for href in
            (m[1] for m in re.finditer(r'<a\b(?:[^>]*?\bhref="([^"]*)")?[^>]*>', html))]


def linking_bite(c: TestClient, target: str, **override) -> str:
    """A published Data Bite at BITE_PAGE whose body links to `target`."""
    return published_bite(c, body=f"See [the CDS]({target}) for more.", **override)


def public_body(client: TestClient, path: str = BITE_PAGE) -> str:
    return content_body(client.get(path).text)


# Resolved site links

def test_a_link_to_a_published_report_is_page_relative(client_as, client, tmp_path):
    director = client_as("admin")
    rid = published_report(director, slug="cds", title="Common Data Set")
    linking_bite(director, report_link(rid))

    assert anchors(public_body(client)) == ["../reports/cds.html"]
    site = exported(render_site(tmp_path / "site"))
    assert anchors(content_body(site["data-bites/fall-enrollment.html"].decode())) == [
        "../reports/cds.html"]
    # crawl() follows it, so it reaches the page.
    assert "/reports/cds.html" in crawl(client)


def test_a_link_to_a_published_data_bite_is_page_relative(client_as, client):
    analyst = client_as("editor")
    target = published_bite(analyst, slug="spring-survey", title="Spring survey")
    linking_bite(analyst, bite_link(target))
    assert anchors(public_body(client)) == ["../data-bites/spring-survey.html"]


def test_a_link_follows_its_targets_slug(client_as, client):
    director = client_as("admin")
    rid = published_report(director, slug="cds", title="Common Data Set")
    linking_bite(director, report_link(rid))
    post_form(director, f"/admin/reports/{rid}",
              {"title": "Common Data Set 2026", "slug": "cds-2026", "body": "New."})
    assert anchors(public_body(client)) == ["../reports/cds-2026.html"]


@pytest.mark.parametrize("path, root", [("index.html", ""), ("data-bites/x.html", "../"),
                                        ("a/b/c.html", "../../")])
def test_a_link_resolves_at_every_depth(client_as, path, root):
    director = client_as("admin")
    rid = published_report(director, slug="cds", title="Common Data Set")
    bite = {"id": None, "slug": "x", "title": "X", "created_at": "2026-09-30 00:00:00",
            "body": f"[CDS]({report_link(rid)})"}
    page = public_site.Page(path, "public/data_bite.html", {"page_title": "X", "bite": bite})
    assert anchors(content_body(page.render())) == [f"{root}reports/cds.html"]


# Unresolved site links are their text

def assert_plain_text(html: str, text: str = "the CDS") -> None:
    assert anchors(html) == [] and text in html, html


def test_a_link_to_a_draft_is_plain_text_until_it_is_published(client_as, client, tmp_path):
    director = client_as("admin")
    rid = create_report(director, slug="cds", title="Common Data Set")
    linking_bite(director, report_link(rid))

    assert_plain_text(public_body(client))
    site = exported(render_site(tmp_path / "site"))
    assert_plain_text(content_body(site["data-bites/fall-enrollment.html"].decode()))
    assert "reports/cds.html" not in site

    post_form(director, f"/admin/reports/{rid}/publish", {})
    site = exported(render_site(tmp_path / "site"))
    assert anchors(content_body(site["data-bites/fall-enrollment.html"].decode())) == [
        "../reports/cds.html"]


def test_a_link_to_an_unpublished_item_is_plain_text(client_as, client):
    analyst = client_as("editor")
    target = published_bite(analyst, slug="spring-survey", title="Spring survey")
    linking_bite(analyst, bite_link(target))
    post_form(analyst, f"/admin/data-bites/{target}/unpublish", {})
    assert_plain_text(public_body(client))


def test_a_link_to_a_deleted_report_never_reaches_a_new_one_with_its_id(client_as, client):
    director = client_as("admin")
    rid = published_report(director, slug="cds", title="Common Data Set")
    link = report_link(rid)
    linking_bite(director, link)
    assert post_form(director, f"/admin/reports/{rid}/delete", {}).status_code == 303

    # SQLite may give the new Report the deleted one's id.
    new = published_report(director, slug="cds", title="A different Report")
    assert new == rid
    assert_plain_text(public_body(client))


@pytest.mark.parametrize("target", ["report:" + "f" * 32, "data-bite:" + "0" * 32,
                                    "report:ABC", "report:"])
def test_a_link_to_nothing_is_plain_text(client_as, client, target):
    linking_bite(client_as("editor"), target)
    assert_plain_text(public_body(client))


# The link rule, for every other href

@pytest.mark.parametrize("href", ["https://www.kenyon.edu/ir", "mailto:ir@kenyon.edu",
                                  "HTTPS://example.test/"])
def test_https_and_mailto_links_are_kept(client_as, client, href):
    linking_bite(client_as("editor"), href)
    assert len(anchors(public_body(client))) == 1


@pytest.mark.parametrize("href", ["http://example.test", "javascript:alert(1)", "/admin",
                                  "/reports/cds.html", "reports/cds.html", "../reports/cds.html",
                                  "#top", "ftp://example.test/x", "//example.test/x",
                                  "data:text/html,x"])
def test_every_other_href_is_plain_text(client_as, client, href):
    """Typed into the Markdown fallback, which saves the body as posted."""
    linking_bite(client_as("editor"), href)
    assert_plain_text(public_body(client))


@pytest.mark.parametrize("html", ['<a href="/admin">the CDS</a>',
                                  '<a href="reports/cds.html">the CDS</a>',
                                  '<a href="http://example.test">the CDS</a>',
                                  '<a name="x">the CDS</a>'])
def test_raw_html_links_follow_the_same_rule(client_as, client, html):
    published_bite(client_as("editor"), body=f"See {html} for more.")
    assert_plain_text(public_body(client))


def test_a_raw_html_link_to_a_published_report_resolves_as_a_site_link(client_as, client):
    director = client_as("admin")
    rid = published_report(director, slug="cds", title="Common Data Set")
    published_bite(director, body=f'See <a href="{report_link(rid)}">the CDS</a>.')
    assert anchors(public_body(client)) == ["../reports/cds.html"]


# Images

@pytest.mark.parametrize("body", ["![Logo](https://example.test/logo.png)",
                                  "![Logo](../images/data-bites/x/logo.png)",
                                  '<img src="https://example.test/logo.png" alt="Logo">',
                                  '<img src="/images/logo.png" alt="Logo">',
                                  '<img alt="Logo">'])
def test_only_a_chart_image_renders_an_img(client_as, client, body):
    published_bite(client_as("editor"), body=f"Before {body} after")
    html = public_body(client)
    assert "<img" not in html and "Before" in html and "after" in html, html


# The Site preview

def test_the_site_preview_resolves_site_links_as_the_site_will(client_as):
    director = client_as("admin")
    published = published_report(director, slug="cds", title="Common Data Set")
    draft = create_report(director, slug="draft-cds", title="Draft CDS")
    bid = create_bite(director)
    body = f"[Published]({report_link(published)}) and [draft]({report_link(draft)})."

    html = content_body(preview(director, "data-bites", bid, title="T", slug="fall-enrollment",
                                body=body).text)
    assert anchors(html) == ["../reports/cds.html"]
    assert "draft" in html


# The crawler (T07, T08), under the restated rule

class Site:
    """Pages a crawl reads, by path, in place of the app."""

    def __init__(self, home: str, **pages: str) -> None:
        self.pages = {"/index.html": home, **{f"/{p.replace('_', '/', 1)}.html": html
                                              for p, html in pages.items()}}

    def get(self, path: str):
        class Response:
            status_code = 200 if path in self.pages else 404
            text = self.pages.get(path, "")
            content = text.encode()
        return Response()


def test_the_crawler_skips_external_links_but_follows_internal_ones():
    site = Site('<a href="https://www.kenyon.edu/">K</a> <a href="mailto:ir@kenyon.edu">M</a>'
                ' <a href="reports/cds.html">CDS</a>', reports_cds='<a href="../index.html">Home</a>')
    assert set(crawl(site)) == {"/index.html", "/reports/cds.html"}


@pytest.mark.parametrize("bad", ['<a href="/reports/cds.html">x</a>',
                                 '<a href="http://example.test/">x</a>',
                                 '<a href="ftp://example.test/">x</a>',
                                 '<a href="javascript:alert(1)">x</a>',
                                 '<img src="https://example.test/logo.png">',
                                 '<img src="/logo.png">',
                                 '<link rel="stylesheet" href="https://example.test/x.css">',
                                 '<script src="//example.test/x.js"></script>',
                                 '<a href="reports/missing.html">x</a>'])
def test_the_crawler_fails_on_a_bad_url(bad):
    with pytest.raises(AssertionError):
        crawl(Site(f"<p>{bad}</p>"))


def test_an_external_link_in_a_body_passes_the_crawl(client_as, client):
    linking_bite(client_as("editor"), "https://www.kenyon.edu/ir")
    assert BITE_PAGE in crawl(client)
