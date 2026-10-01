"""T04: Reports, draft/publish lockdown (issue #5)."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from tests.conftest import backdate, post_form, second_analyst, stored_id, stored_slugs
from tests.test_t06_admin_console import preview_of

REPORT = {"title": "Factbook 2026", "slug": "factbook",
          "body": "Admissions, enrollment, and **program** statistics."}


def report_row(c: TestClient, slug: str) -> str:
    """This Report's row of the admin list, as HTML."""
    item_id = stored_id("reports", slug)
    for row in c.get("/admin/reports").text.split("<tr")[1:]:
        if row.startswith(f' id="report-{item_id}"'):
            return row
    raise AssertionError(f"{slug} is not listed")


def report_id(c: TestClient, slug: str) -> str:
    return re.match(r' id="report-(\d+)"', report_row(c, slug)).group(1)


def create_report(c: TestClient, **override) -> str:
    response = post_form(c, "/admin/reports", {**REPORT, **override})
    assert response.status_code == 303, response.text
    # A create lands on the new item's edit page (T22).
    return response.headers["location"].removeprefix("/admin/reports/")


def published_report(director: TestClient, analyst: TestClient) -> str:
    """An Analyst-drafted Report that the Director has published."""
    rid = create_report(analyst)
    assert post_form(director, f"/admin/reports/{rid}/publish", {}).status_code == 303
    return rid


def test_analyst_creates_a_draft_report(client_as):
    analyst = client_as("editor")
    response = post_form(analyst, "/admin/reports", REPORT)
    assert response.status_code == 303
    # To the new Report's edit page since T22 (spec #25), not the list.
    assert response.headers["location"] == f"/admin/reports/{stored_id('reports', REPORT['slug'])}"
    row = report_row(analyst, REPORT["slug"])
    assert REPORT["title"] in row and "Draft" in row


def test_a_report_requires_a_markdown_body(client_as):
    analyst = client_as("editor")
    response = post_form(analyst, "/admin/reports", {**REPORT, "body": "   "})
    assert response.status_code == 400
    assert "Enter a body." in response.text
    assert REPORT["slug"] not in stored_slugs("reports")


def test_any_analyst_edits_any_draft_report_and_author_and_created_at_are_kept(client_as):
    riley = second_analyst(client_as("admin"))
    rid = create_report(riley)
    backdate("reports", rid)

    analyst = client_as("editor")  # not the author
    edited = {"title": "Factbook 2026 (draft 2)", "slug": "factbook",
              "body": "Now with *diversity* tables."}
    response = post_form(analyst, f"/admin/reports/{rid}", edited)
    assert response.status_code == 303

    page = analyst.get(f"/admin/reports/{rid}").text
    assert edited["title"] in page and edited["body"] in page
    assert "Created 2026-01-05 09:00:00 by Riley Intern" in page
    updated = re.search(r"Last updated ([\d:\- ]+)", page).group(1)
    assert updated != "2026-01-05 09:00:00"


def test_analyst_cannot_publish_a_report(client_as):
    analyst = client_as("editor")
    rid = create_report(analyst)
    assert post_form(analyst, f"/admin/reports/{rid}/publish", {}).status_code == 403
    assert "Draft" in report_row(analyst, REPORT["slug"])
    assert "/publish" not in analyst.get("/admin/reports").text


def test_analyst_cannot_delete_a_draft_report(client_as):
    analyst = client_as("editor")
    rid = create_report(analyst)
    assert post_form(analyst, f"/admin/reports/{rid}/delete", {}).status_code == 403
    assert REPORT["title"] in report_row(analyst, REPORT["slug"])
    assert "/delete" not in analyst.get("/admin/reports").text


def test_published_report_is_locked_against_analyst_edit_unpublish_and_delete(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = published_report(director, analyst)

    edit = post_form(analyst, f"/admin/reports/{rid}",
                     {**REPORT, "title": "Tampered", "body": "Tampered."})
    assert edit.status_code == 403
    assert post_form(analyst, f"/admin/reports/{rid}/unpublish", {}).status_code == 403
    assert post_form(analyst, f"/admin/reports/{rid}/delete", {}).status_code == 403

    row = report_row(director, REPORT["slug"])
    assert REPORT["title"] in row and "Published" in row
    assert "Tampered" not in director.get(f"/admin/reports/{rid}").text


def test_invalid_edit_to_a_published_report_is_still_403_for_an_analyst(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = published_report(director, analyst)
    for bad in ({"body": "  "}, {"slug": "Not A Slug"}, {"title": ""}):
        response = post_form(analyst, f"/admin/reports/{rid}", {**REPORT, **bad})
        assert response.status_code == 403, bad


def test_analyst_sees_a_published_report_read_only(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = published_report(director, analyst)
    page = analyst.get(f"/admin/reports/{rid}")
    assert page.status_code == 200
    # Shown rendered, in its Site preview (T06, T12), not as raw Markdown.
    assert "<p>Admissions, enrollment, and <strong>program</strong> statistics.</p>" in \
        preview_of(page.text)
    assert f'action="/admin/reports/{rid}"' not in page.text
    assert "Only the Director" in page.text


def test_director_publishes_edits_unpublishes_and_deletes_a_report(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = published_report(director, analyst)
    assert "Published" in report_row(director, REPORT["slug"])

    edited = {**REPORT, "title": "Factbook 2026 (corrected)"}
    assert post_form(director, f"/admin/reports/{rid}", edited).status_code == 303
    row = report_row(director, REPORT["slug"])
    assert edited["title"] in row and "Published" in row

    assert post_form(director, f"/admin/reports/{rid}/unpublish", {}).status_code == 303
    assert "Draft" in report_row(director, REPORT["slug"])

    # Back in draft, an Analyst can work on it again.
    assert post_form(analyst, f"/admin/reports/{rid}", REPORT).status_code == 303

    assert post_form(director, f"/admin/reports/{rid}/delete", {}).status_code == 303
    assert f'id="report-{rid}"' not in director.get("/admin/reports").text
    assert post_form(director, f"/admin/reports/{rid}/delete", {}).status_code == 404


def test_director_deletes_a_published_report(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = published_report(director, analyst)
    assert post_form(director, f"/admin/reports/{rid}/delete", {}).status_code == 303
    assert f'id="report-{rid}"' not in director.get("/admin/reports").text


def test_duplicate_report_slug_is_rejected_with_a_validation_error(client_as):
    analyst = client_as("editor")
    create_report(analyst)
    response = post_form(analyst, "/admin/reports", {**REPORT, "title": "Another"})
    assert response.status_code == 400
    assert f"Another Report already uses the slug {REPORT['slug']}" in response.text
    assert analyst.get("/admin/reports").text.count('id="report-') == 1


def test_editing_to_another_reports_slug_is_rejected(client_as):
    analyst = client_as("editor")
    create_report(analyst)
    other = create_report(analyst, slug="common-data-set", title="Common Data Set")
    response = post_form(analyst, f"/admin/reports/{other}",
                         {**REPORT, "title": "Common Data Set"})
    assert response.status_code == 400
    assert f"already uses the slug {REPORT['slug']}" in response.text
    assert report_id(analyst, "common-data-set") == other


def test_a_data_bite_may_share_a_slug_with_a_report(client_as):
    analyst = client_as("editor")
    create_report(analyst)
    bite = {"title": "Factbook is out", "slug": REPORT["slug"], "body": "See the Factbook."}
    assert post_form(analyst, "/admin/data-bites", bite).status_code == 303
    bid = stored_id("data_bites", REPORT["slug"])
    assert f'id="data-bite-{bid}"' in analyst.get("/admin/data-bites").text
    assert REPORT["title"] in report_row(analyst, REPORT["slug"])


def test_a_draft_report_is_never_shown_publicly(client_as, client):
    director, analyst = client_as("admin"), client_as("editor")
    rid = published_report(director, analyst)
    create_report(analyst, slug="cds-2027", title="Unreleased CDS")

    home = client.get("/").text
    assert REPORT["title"] in home
    assert "Unreleased CDS" not in home and "cds-2027" not in home

    post_form(director, f"/admin/reports/{rid}/unpublish", {})
    assert REPORT["title"] not in client.get("/").text


# Every Report route. {id} is filled with an existing draft Report's id.
ROUTES = [
    ("GET", "/admin/reports", {}),
    ("POST", "/admin/reports", {**REPORT, "slug": "new-slug"}),
    ("GET", "/admin/reports/{id}", {}),
    ("POST", "/admin/reports/{id}", {**REPORT, "title": "Changed title"}),
    ("POST", "/admin/reports/{id}/publish", {}),
    ("POST", "/admin/reports/{id}/unpublish", {}),
    ("POST", "/admin/reports/{id}/delete", {}),
]
POST_ROUTES = [r for r in ROUTES if r[0] == "POST"]


@pytest.fixture
def existing_report(client_as):
    return create_report(client_as("editor"))


def assert_unchanged(c: TestClient):
    """The Report from `existing_report` is still the only one, still a draft,
    with its original title."""
    assert c.get("/admin/reports").text.count('id="report-') == 1
    row = report_row(c, REPORT["slug"])
    assert REPORT["title"] in row and "Draft" in row


@pytest.mark.parametrize("method, path, data", ROUTES)
def test_anonymous_visitor_is_redirected_from_every_report_route(
        client, client_as, existing_report, method, path, data):
    response = client.request(method, path.format(id=existing_report),
                              data=data or None, follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].endswith("/login")
    assert_unchanged(client_as("admin"))


@pytest.mark.parametrize("method, path, data", POST_ROUTES)
def test_report_posts_without_csrf_token_are_rejected(
        client_as, existing_report, method, path, data):
    director = client_as("admin")
    director.get("/admin")  # the session has a token; the POST just omits it
    response = post_form(director, path.format(id=existing_report), data, with_csrf=False)
    assert response.status_code == 403
    assert_unchanged(director)


def test_every_signed_in_user_sees_the_reports_link(client_as):
    for role in ("admin", "editor"):
        assert 'href="/admin/reports"' in client_as(role).get("/admin").text


def test_missing_report_is_404(client_as):
    director = client_as("admin")
    assert director.get("/admin/reports/999").status_code == 404
    assert post_form(director, "/admin/reports/999", REPORT).status_code == 404
    assert post_form(director, "/admin/reports/999/publish", {}).status_code == 404
