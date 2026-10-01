"""T20: Summaries (issue #24, spec #22).

Every Data Bite and Report may carry a Summary: plain text, trimmed, at most
200 characters, escaped like the title. It shows under the item's title, in
the public lists, and in the page's description and link-preview tags.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import content, data_bites, reports
from app.content import ContentError, SUMMARY_MAX
from tests.conftest import post_form
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import REPORT, create_report
from tests.test_t07_public_site import published_bite, published_report
from tests.test_t12_site_preview import preview

SUMMARY = "Headcount by class on the census date. The first-year class grew."
KINDS = [("data-bites", BITE, create_bite, data_bites),
         ("reports", REPORT, create_report, reports)]


def meta(page: str, attribute: str, name: str) -> str | None:
    found = re.findall(rf'<meta {attribute}="{re.escape(name)}" content="([^"]*)">', page)
    assert len(found) <= 1, found
    return found[0] if found else None


# The rule

def test_a_summary_is_trimmed_and_optional():
    assert content.validate_summary("  " + SUMMARY + "\n") == SUMMARY
    assert content.validate_summary("") == ""
    assert content.validate_summary("   ") == ""


def test_a_summary_of_200_characters_is_kept_and_201_refused():
    assert SUMMARY_MAX == 200
    assert content.validate_summary("é" * 200) == "é" * 200  # characters, not bytes
    with pytest.raises(ContentError) as refused:
        content.validate_summary("x" * 201)
    assert refused.value.field == "summary"
    assert "200" in str(refused.value)


def test_a_summary_is_one_paragraph_of_plain_text():
    # A line break is kept as a space: it's one or two sentences, not Markdown.
    assert content.validate_summary("One line.\r\nTwo lines.") == "One line. Two lines."


# The edit forms

@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_a_summary_is_saved_from_the_create_and_edit_forms(client_as, kind, item, create, module):
    director = client_as("admin")
    item_id = create(director, summary="  First version.  ")
    assert module.get(int(item_id))["summary"] == "First version."

    form = director.get(f"/admin/{kind}/{item_id}").text
    assert re.search(r'<textarea[^>]*name="summary"[^>]*>First version\.</textarea>', form)
    assert 'data-summary-max="200"' in form

    response = post_form(director, f"/admin/{kind}/{item_id}", {**item, "summary": SUMMARY})
    assert response.status_code == 303
    assert module.get(int(item_id))["summary"] == SUMMARY


@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_a_long_summary_is_refused_by_the_field_and_kept_in_it(client_as, kind, item, create, module):
    director = client_as("admin")
    item_id = create(director, summary="Kept.")
    too_long = "y" * 201

    response = post_form(director, f"/admin/{kind}/{item_id}", {**item, "summary": too_long})
    assert response.status_code == 400
    assert module.get(int(item_id))["summary"] == "Kept."
    # The message sits by the field, which keeps what was typed.
    assert re.search(r'id="summary-error"[^>]*>[^<]*200 characters', response.text)
    assert re.search(r'name="summary"[^>]*aria-describedby="[^"]*summary-error', response.text)
    assert f">{too_long}</textarea>" in response.text

    response = post_form(director, f"/admin/{kind}", {**item, "slug": "other", "summary": too_long})
    assert response.status_code == 400 and 'id="summary-error"' in response.text


def test_an_item_saved_from_an_older_form_with_another_summary_is_stale(client_as):
    director = client_as("admin")
    bite = create_bite(director, summary="Old.")
    base = re.search(r'name="item_base" value="([^"]+)"',
                     director.get(f"/admin/data-bites/{bite}").text).group(1)
    assert post_form(director, f"/admin/data-bites/{bite}",
                     {**BITE, "summary": "New.", "item_base": base}).status_code == 303
    stale = post_form(director, f"/admin/data-bites/{bite}",
                      {**BITE, "summary": "Older tab.", "item_base": base})
    assert stale.status_code == 409
    assert data_bites.get(int(bite))["summary"] == "New."


# The public site

def test_the_summary_shows_under_the_title_and_in_the_lists(client_as, client):
    director = client_as("admin")
    published_bite(director, summary=SUMMARY)
    published_report(director, summary="Admissions and enrollment, each term.")

    for path in ["/data-bites/fall-enrollment.html", "/data-bites/index.html", "/"]:
        assert SUMMARY in client.get(path).text, path
    for path in ["/reports/factbook.html", "/reports/index.html", "/"]:
        assert "Admissions and enrollment, each term." in client.get(path).text, path

    page = client.get("/data-bites/fall-enrollment.html").text
    assert page.index(BITE["title"]) < page.index(f'<p class="summary-item">{SUMMARY}</p>')


def test_an_item_without_a_summary_shows_nothing_in_its_place(client_as, client):
    published_bite(client_as("editor"))
    page = client.get("/data-bites/fall-enrollment.html").text
    assert "summary-item" not in page
    assert meta(page, "name", "description") is None
    assert meta(page, "property", "og:description") is None
    assert meta(page, "property", "og:title") == BITE["title"]


def test_a_summary_is_escaped_everywhere_it_shows(client_as, client):
    published_bite(client_as("editor"), summary='<script>alert(1)</script> & "quotes"')
    for path in ["/data-bites/fall-enrollment.html", "/data-bites/index.html", "/"]:
        page = client.get(path).text
        assert "<script>alert(1)" not in page, path
        assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; " in page, path
    page = client.get("/data-bites/fall-enrollment.html").text
    assert meta(page, "name", "description") == (
        "&lt;script&gt;alert(1)&lt;/script&gt; &amp; &#34;quotes&#34;")


@pytest.mark.parametrize("path, og_type", [("/data-bites/fall-enrollment.html", "article"),
                                           ("/reports/factbook.html", "article"),
                                           ("/reports/index.html", "website")])
def test_an_item_page_has_its_description_and_link_preview_tags(client_as, client, path, og_type):
    director = client_as("admin")
    published_bite(director, summary=SUMMARY)
    published_report(director, summary=SUMMARY)
    page = client.get(path).text
    assert meta(page, "property", "og:type") == og_type
    if og_type == "article":
        assert meta(page, "name", "description") == SUMMARY
        assert meta(page, "property", "og:description") == SUMMARY
        assert meta(page, "property", "og:title") in (BITE["title"], REPORT["title"])
    # Absolute URLs only; the site links relatively, so these are left out.
    assert meta(page, "property", "og:url") is None and meta(page, "property", "og:image") is None


@pytest.mark.parametrize("kind", ["data-bites", "reports"])
def test_the_site_preview_shows_the_unsaved_summary(client_as, kind):
    director = client_as("admin")
    page = preview(director, kind, title="Draft title", body="Body.", summary="Typed, not saved.")
    assert page.status_code == 200
    assert '<p class="summary-item">Typed, not saved.</p>' in page.text
    assert meta(page.text, "name", "description") == "Typed, not saved."
