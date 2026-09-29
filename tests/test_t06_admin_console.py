"""T06: Admin console — dashboard, filterable content list, Markdown preview
(issue #7)."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app import db
from tests.conftest import post_form


def create(c: TestClient, kind: str, slug: str, *, body: str = "Some **Markdown**.") -> str:
    """Create a draft of `kind` ("data-bites" or "reports"); its id."""
    response = post_form(c, f"/admin/{kind}", {"title": slug.title(), "slug": slug, "body": body})
    assert response.status_code == 303, response.text
    return re.search(rf'<tr id="[a-z-]+-(\d+)">\s*<td><a href="/admin/{kind}/\d+">'
                     rf'{slug.title()}</a>', c.get(f"/admin/{kind}").text).group(1)


def publish(director: TestClient, kind: str, item_id: str) -> None:
    assert post_form(director, f"/admin/{kind}/{item_id}/publish", {}).status_code == 303


def dashboard_counts(c: TestClient) -> dict[str, str]:
    """The dashboard's count cells, e.g. {"data-bite-draft": "2", ...}."""
    return dict(re.findall(r'<td id="count-([a-z-]+)">(?:<a [^>]+>)?(\d+)(?:</a>)?</td>',
                           c.get("/admin").text))


# --- Dashboard ---------------------------------------------------------------

def test_dashboard_starts_at_zero(client_as):
    assert dashboard_counts(client_as("editor")) == {
        "data-bite-draft": "0", "data-bite-published": "0", "data-bite-total": "0",
        "report-draft": "0", "report-published": "0", "report-total": "0",
    }


def test_dashboard_counts_each_type_by_status(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    for slug in ("a", "b", "c"):
        create(analyst, "data-bites", slug)
    publish(analyst, "data-bites", create(analyst, "data-bites", "d"))
    create(analyst, "reports", "factbook")
    publish(director, "reports", create(analyst, "reports", "cds"))
    publish(director, "reports", create(director, "reports", "survey-calendar"))

    expected = {
        "data-bite-draft": "3", "data-bite-published": "1", "data-bite-total": "4",
        "report-draft": "1", "report-published": "2", "report-total": "3",
    }
    assert dashboard_counts(analyst) == expected
    assert dashboard_counts(director) == expected


def test_dashboard_counts_follow_unpublish_and_delete(client_as):
    director = client_as("admin")
    bite = create(director, "data-bites", "a")
    publish(director, "data-bites", bite)
    report = create(director, "reports", "factbook")
    publish(director, "reports", report)

    assert post_form(director, f"/admin/data-bites/{bite}/unpublish", {}).status_code == 303
    assert post_form(director, f"/admin/reports/{report}/delete", {}).status_code == 303

    counts = dashboard_counts(director)
    assert (counts["data-bite-draft"], counts["data-bite-published"]) == ("1", "0")
    assert counts["report-total"] == "0"


def test_dashboard_uses_the_glossary_labels(client_as):
    page = client_as("editor").get("/admin").text
    for label in ("Data Bites", "Reports", "Draft", "Published"):
        assert label in page


# --- Content list ------------------------------------------------------------

def listed(c: TestClient, query: str = "") -> list[tuple[str, str, str]]:
    """The content list's rows as (type, title, status), top to bottom."""
    response = c.get(f"/admin/content{query}")
    assert response.status_code == 200, response.text
    return re.findall(r'<tr class="content-row">\s*<td>([^<]+)</td>\s*<td><a href="[^"]+">'
                      r'([^<]+)</a></td>.*?<td>(Draft|Published)</td>', response.text, re.S)


def mixed_content(director: TestClient, analyst: TestClient) -> None:
    """Two Data Bites and two Reports, one of each published."""
    create(analyst, "data-bites", "bite-draft")
    publish(analyst, "data-bites", create(analyst, "data-bites", "bite-live"))
    create(analyst, "reports", "report-draft")
    publish(director, "reports", create(analyst, "reports", "report-live"))


def test_content_list_shows_both_types_newest_first(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    mixed_content(director, analyst)
    with db.connect() as conn:  # setup: make "bite-draft" the most recently updated
        conn.execute("UPDATE data_bites SET updated_at = '2999-01-01 00:00:00'"
                     " WHERE slug = 'bite-draft'")

    rows = listed(analyst)
    assert rows[0] == ("Data Bite", "Bite-Draft", "Draft")
    assert sorted(rows) == [
        ("Data Bite", "Bite-Draft", "Draft"), ("Data Bite", "Bite-Live", "Published"),
        ("Report", "Report-Draft", "Draft"), ("Report", "Report-Live", "Published"),
    ]


def test_content_list_filters_by_type(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    mixed_content(director, analyst)
    assert {r[:2] for r in listed(analyst, "?type=report")} == {
        ("Report", "Report-Draft"), ("Report", "Report-Live")}
    assert {r[:2] for r in listed(analyst, "?type=data-bite")} == {
        ("Data Bite", "Bite-Draft"), ("Data Bite", "Bite-Live")}


def test_content_list_filters_by_status(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    mixed_content(director, analyst)
    assert sorted(listed(analyst, "?status=draft")) == [
        ("Data Bite", "Bite-Draft", "Draft"), ("Report", "Report-Draft", "Draft")]
    assert sorted(listed(analyst, "?status=published")) == [
        ("Data Bite", "Bite-Live", "Published"), ("Report", "Report-Live", "Published")]


def test_content_list_filters_combine(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    mixed_content(director, analyst)
    assert listed(director, "?type=report&status=published") == [
        ("Report", "Report-Live", "Published")]
    # The filter form's "All" options submit empty values.
    assert len(listed(director, "?type=&status=")) == 4


def test_content_list_links_each_item_to_its_edit_page(client_as):
    analyst = client_as("editor")
    rid = create(analyst, "reports", "factbook")
    page = analyst.get("/admin/content").text
    assert f'<a href="/admin/reports/{rid}">Factbook</a>' in page


def test_content_list_keeps_the_chosen_filters_selected(client_as):
    page = client_as("editor").get("/admin/content?type=report&status=draft").text
    assert re.search(r'<option value="report" selected>', page)
    assert re.search(r'<option value="draft" selected>', page)


def test_content_list_says_when_nothing_matches(client_as):
    analyst = client_as("editor")
    create(analyst, "data-bites", "only-a-draft")
    page = analyst.get("/admin/content?status=published").text
    assert "Nothing matches" in page and "content-row" not in page


def test_content_list_rejects_an_unknown_filter_value(client_as):
    analyst = client_as("editor")
    assert analyst.get("/admin/content?type=page").status_code == 422
    assert analyst.get("/admin/content?status=live").status_code == 422


def test_dashboard_counts_link_to_the_filtered_list(client_as):
    page = client_as("editor").get("/admin").text
    assert 'href="/admin/content?type=report&amp;status=draft"' in page


# --- Markdown preview ---------------------------------------------------------

PAYLOAD = ('<script>alert("owned")</script>\n\n'
           '<img src="chart.png" onerror="alert(1)">\n\n'
           '<a href="javascript:alert(2)">raw link</a> and [md link](javascript:alert(3))\n\n'
           'Retention is **92%**.')


def preview_of(html: str) -> str:
    """The inside of the page's preview area."""
    match = re.search(r'<div class="content-preview"[^>]*>(.*?)</div><!-- /content-preview -->',
                      html, re.S)
    assert match, "no preview on the page"
    return match.group(1)


def assert_inert(preview: str) -> None:
    assert "<script" not in preview and "owned" not in preview
    assert "onerror" not in preview
    assert 'href="javascript' not in preview
    assert '<img src="chart.png">' in preview  # sanitized, not thrown away
    assert "<strong>92%</strong>" in preview   # and the Markdown still renders


def preview(c: TestClient, body: str, *, with_csrf: bool = True):
    return post_form(c, "/admin/preview", {"body": body}, with_csrf=with_csrf)


def test_editing_a_data_bite_shows_its_rendered_markdown(client_as):
    analyst = client_as("editor")
    bid = create(analyst, "data-bites", "retention", body="# Retention\n\n- first-year: **92%**")
    shown = preview_of(analyst.get(f"/admin/data-bites/{bid}").text)
    assert "<h1>Retention</h1>" in shown
    assert "<li>first-year: <strong>92%</strong></li>" in shown


def test_editing_a_report_shows_its_rendered_markdown(client_as):
    analyst = client_as("editor")
    rid = create(analyst, "reports", "factbook", body="Enrollment by *class year*.")
    shown = preview_of(analyst.get(f"/admin/reports/{rid}").text)
    assert "<p>Enrollment by <em>class year</em>.</p>" in shown


def test_the_new_item_forms_have_a_preview_too(client_as):
    analyst = client_as("editor")
    for path in ("/admin/data-bites", "/admin/reports"):
        assert preview_of(analyst.get(path).text).strip() == ""


def test_the_preview_follows_the_text_as_it_is_typed(client_as):
    response = preview(client_as("editor"), "Draft *two*")
    assert response.status_code == 200
    assert response.text.strip() == "<p>Draft <em>two</em></p>"
    # Nothing was saved: previewing is not creating.
    assert client_as("editor").get("/admin/content").text.count("content-row") == 0


def test_a_failed_save_previews_what_was_typed(client_as):
    analyst = client_as("editor")
    response = post_form(analyst, "/admin/data-bites",
                         {"title": "", "slug": "x", "body": "Unsaved *work*"})
    assert response.status_code == 400
    assert "<em>work</em>" in preview_of(response.text)


def test_a_script_payload_is_inert_in_the_data_bite_preview(client_as):
    analyst = client_as("editor")
    bid = create(analyst, "data-bites", "payload", body=PAYLOAD)
    assert_inert(preview_of(analyst.get(f"/admin/data-bites/{bid}").text))


def test_a_script_payload_is_inert_in_the_report_preview(client_as):
    director = client_as("admin")
    rid = create(director, "reports", "payload", body=PAYLOAD)
    assert_inert(preview_of(director.get(f"/admin/reports/{rid}").text))


def test_a_script_payload_is_inert_in_the_live_preview(client_as):
    assert_inert(preview(client_as("editor"), PAYLOAD).text)


def test_the_body_is_stored_raw(client_as):
    """Sanitizing happens when rendering; the saved Markdown is untouched."""
    analyst = client_as("editor")
    bid = create(analyst, "data-bites", "payload", body=PAYLOAD)
    with db.connect() as conn:
        stored = conn.execute("SELECT body FROM data_bites WHERE id = ?", (bid,)).fetchone()[0]
    assert stored == PAYLOAD


def test_an_analyst_sees_a_locked_report_rendered(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = create(analyst, "reports", "factbook", body=PAYLOAD)
    publish(director, "reports", rid)
    page = analyst.get(f"/admin/reports/{rid}").text
    assert 'action="/admin/reports/' + rid + '"' not in page  # still read-only
    assert_inert(preview_of(page))


def test_the_live_preview_needs_a_csrf_token(client_as):
    assert preview(client_as("editor"), "hi", with_csrf=False).status_code == 403


# --- Anonymous visitors ---------------------------------------------------------

def test_anonymous_visitors_are_sent_to_login(client):
    for path in ("/admin", "/admin/content", "/admin/content?type=report&status=draft",
                 "/admin/data-bites", "/admin/data-bites/1", "/admin/reports", "/admin/reports/1"):
        response = client.get(path, follow_redirects=False)
        assert (response.status_code, response.headers["location"]) == (303, "/login"), path
    response = client.post("/admin/preview", data={"body": "hi"}, follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/login")
