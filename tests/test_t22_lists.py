"""T22: Lists and create pages (issue #27, spec #25).

The Data Bites, Reports, and All content lists are one `table-items` table:
each item's title with its Summary, a state badge, its author, when it was
last updated (ISO), and the actions the user may take. The two type lists
filter by state with `?status=`. Creating an item has its own page, and a
create lands on the new item's edit page.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import db
from tests.conftest import post_form
from tests.test_t03_data_bites import BITE
from tests.test_t04_reports import REPORT

LISTS = {"data-bites": ("data-bite", BITE), "reports": ("report", REPORT)}


def create(c: TestClient, kind: str, slug: str, **fields) -> str:
    _, item = LISTS[kind]
    response = post_form(c, f"/admin/{kind}", {**item, "slug": slug, "title": slug.title(),
                                               **fields})
    assert response.status_code == 303, response.text
    return response.headers["location"].rsplit("/", 1)[1]


def published_and_draft(kind: str, director: TestClient) -> tuple[str, str]:
    live, draft = create(director, kind, "live"), create(director, kind, "draft")
    assert post_form(director, f"/admin/{kind}/{live}/publish", {}).status_code == 303
    return live, draft


def row_ids(html: str, key: str) -> list[str]:
    return re.findall(rf'<tr id="{key}-(\d+)"', html)


def row(html: str, key: str, item_id: str) -> str:
    match = re.search(rf'<tr id="{key}-{item_id}" role="row">(.*?)</tr>', html, re.S)
    assert match, f"{key}-{item_id} is not listed"
    return match.group(1)


def filters(html: str) -> list[tuple[str, str, str, bool]]:
    """The filter links as (href, label, count, current)."""
    match = re.search(r'<nav class="filters-console" aria-label="Filter by state">(.*?)</nav>',
                      html, re.S)
    assert match, "no state filters"
    return [(href, label, count, bool(current)) for href, current, label, count in re.findall(
        r'<a href="([^"]+)"( aria-current="page")?>([^<]+)<span class="text-mono">(\d+)</span></a>',
        match.group(1))]


# --- The table ---------------------------------------------------------------

@pytest.mark.parametrize("kind", LISTS)
def test_each_row_has_the_title_summary_state_author_and_iso_date(client_as, kind):
    key, _ = LISTS[kind]
    director = client_as("admin")
    item_id = create(director, kind, "fall", summary="Headcount on the census date.")
    with db.connect() as conn:  # setup: a known update time
        conn.execute(f"UPDATE {kind.replace('-', '_')} SET updated_at = '2026-09-30 14:05:00'")

    cells = row(director.get(f"/admin/{kind}").text, key, item_id)
    assert (f'<th role="rowheader" scope="row" class="table-items-title"><a href="/admin/{kind}/{item_id}">Fall</a>'
            '<p>Headcount on the census date.</p></th>') in cells
    assert '<span class="badge-state badge-state-draft">Draft</span>' in cells
    assert "<td role=\"cell\">admin</td>" in cells  # the seeded Director's name
    assert ('<td role="cell" class="text-mono"><time datetime="2026-09-30T14:05:00">2026-09-30</time></td>'
            in cells)


@pytest.mark.parametrize("kind", LISTS)
def test_a_row_without_a_summary_shows_nothing_in_its_place(client_as, kind):
    key, _ = LISTS[kind]
    director = client_as("admin")
    item_id = create(director, kind, "fall")
    cells = row(director.get(f"/admin/{kind}").text, key, item_id)
    assert f'<a href="/admin/{kind}/{item_id}">Fall</a></th>' in cells


@pytest.mark.parametrize("kind", LISTS)
def test_a_published_row_has_the_published_badge(client_as, kind):
    key, _ = LISTS[kind]
    director = client_as("admin")
    live, _ = published_and_draft(kind, director)
    cells = row(director.get(f"/admin/{kind}").text, key, live)
    assert '<span class="badge-state badge-state-published">Published</span>' in cells


@pytest.mark.parametrize("kind", LISTS)
def test_the_directors_row_actions_are_edit_unpublish_or_publish_and_delete(client_as, kind):
    key, _ = LISTS[kind]
    director = client_as("admin")
    live, draft = published_and_draft(kind, director)
    page = director.get(f"/admin/{kind}").text
    for item_id, action in ((live, "unpublish"), (draft, "publish")):
        cells = row(page, key, item_id)
        assert f'<a class="button-quiet" href="/admin/{kind}/{item_id}">Edit</a>' in cells
        form = re.search(rf'<form method="post" action="/admin/{kind}/{item_id}/{action}">(.*?)</form>',
                         cells, re.S)
        assert form and 'name="csrf_token"' in form.group(1), action
        assert f'href="/admin/{kind}/{item_id}/delete"' in cells


def test_an_analyst_publishes_data_bites_but_deletes_nothing(client_as):
    analyst = client_as("editor")
    bid = create(analyst, "data-bites", "fall")
    cells = row(analyst.get("/admin/data-bites").text, "data-bite", bid)
    assert f'action="/admin/data-bites/{bid}/publish"' in cells
    assert "/delete" not in cells


def test_an_analyst_may_not_publish_a_report_and_views_a_published_one(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    live, draft = published_and_draft("reports", director)
    page = analyst.get("/admin/reports").text
    assert "/publish" not in page and "/unpublish" not in page and "/delete" not in page
    # A published Report is locked for an Analyst: its page is read-only.
    assert f'<a class="button-quiet" href="/admin/reports/{draft}">Edit</a>' in row(page, "report", draft)
    assert f'<a class="button-quiet" href="/admin/reports/{live}">View</a>' in row(page, "report", live)


@pytest.mark.parametrize("kind", LISTS)
def test_the_row_links_are_the_routes(client_as, kind):
    """Each row's links lead where the routes say, whichever type it is."""
    key, _ = LISTS[kind]
    director = client_as("admin")
    item_id = create(director, kind, "fall")
    cells = row(director.get(f"/admin/{kind}").text, key, item_id)
    assert set(re.findall(r'(?:href|action)="([^"]+)"', cells)) == {
        f"/admin/{kind}/{item_id}", f"/admin/{kind}/{item_id}/publish",
        f"/admin/{kind}/{item_id}/delete"}
    for path in (f"/admin/{kind}/{item_id}", f"/admin/{kind}/{item_id}/delete"):
        assert director.get(path).status_code == 200, path


def test_the_table_keeps_its_roles_when_its_rows_stack(client_as):
    analyst = client_as("editor")
    bid = create(analyst, "data-bites", "fall")
    page = analyst.get("/admin/data-bites").text
    assert '<table class="table-items table-items-stack" role="table">' in page
    assert page.count('role="columnheader"') == 5
    cells = row(page, "data-bite", bid)
    assert '<th role="rowheader" scope="row"' in cells and cells.count('role="cell"') == 4


# --- Filters -----------------------------------------------------------------

@pytest.mark.parametrize("kind", LISTS)
def test_each_filter_shows_only_its_state(client_as, kind):
    key, _ = LISTS[kind]
    director = client_as("admin")
    live, draft = published_and_draft(kind, director)

    def listed(query: str) -> set[str]:
        response = director.get(f"/admin/{kind}{query}")
        assert response.status_code == 200
        return set(row_ids(response.text, key))

    assert listed("") == listed("?status=") == {live, draft}
    assert listed("?status=published") == {live}
    assert listed("?status=draft") == {draft}


@pytest.mark.parametrize("kind", LISTS)
def test_the_filters_show_their_counts_and_mark_the_current_one(client_as, kind):
    director = client_as("admin")
    published_and_draft(kind, director)
    create(director, kind, "another-draft")
    assert filters(director.get(f"/admin/{kind}?status=draft").text) == [
        (f"/admin/{kind}", "All", "3", False),
        (f"/admin/{kind}?status=published", "Published", "1", False),
        (f"/admin/{kind}?status=draft", "Drafts", "2", True),
    ]
    assert [current for *_, current in filters(director.get(f"/admin/{kind}").text)] == [
        True, False, False]


@pytest.mark.parametrize("kind", LISTS)
def test_publishing_from_a_filtered_list_returns_to_that_filter(client_as, kind):
    key, _ = LISTS[kind]
    director = client_as("admin")
    live, draft = published_and_draft(kind, director)
    cells = row(director.get(f"/admin/{kind}?status=draft").text, key, draft)
    assert f'action="/admin/{kind}/{draft}/publish?status=draft"' in cells
    response = post_form(director, f"/admin/{kind}/{draft}/publish?status=draft", {})
    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/{kind}?status=draft"
    # Unfiltered, it returns to the whole list; a bad filter changes nothing.
    response = post_form(director, f"/admin/{kind}/{live}/unpublish", {})
    assert response.headers["location"] == f"/admin/{kind}"
    assert post_form(director, f"/admin/{kind}/{draft}/unpublish?status=x", {}).status_code == 400
    assert row(director.get(f"/admin/{kind}").text, key, draft).count("badge-state-published") == 1


@pytest.mark.parametrize("path", ["/admin/data-bites", "/admin/reports", "/admin/content"])
@pytest.mark.parametrize("status", ["live", "Draft", "pending"])
def test_an_unknown_status_is_a_400(client_as, path, status):
    assert client_as("editor").get(f"{path}?status={status}").status_code == 400


def test_an_unknown_type_on_all_content_is_a_400(client_as):
    assert client_as("editor").get("/admin/content?type=page").status_code == 400


@pytest.mark.parametrize("kind", LISTS)
def test_an_empty_filter_says_so(client_as, kind):
    director = client_as("admin")
    create(director, kind, "only-a-draft")
    page = director.get(f"/admin/{kind}?status=published").text
    noun = "Data Bite" if kind == "data-bites" else "Report"
    assert f"No {noun} is Published yet." in page and "<tbody>" not in page


# --- Create pages ------------------------------------------------------------

@pytest.mark.parametrize("kind", LISTS)
def test_the_list_no_longer_holds_the_create_form(client_as, kind):
    page = client_as("editor").get(f"/admin/{kind}").text
    assert 'name="title"' not in page and "admin-editor" not in page
    noun = "Data Bite" if kind == "data-bites" else "Report"
    assert f'<a class="button-primary" href="/admin/{kind}/new">New {noun}</a>' in page


@pytest.mark.parametrize("kind", LISTS)
def test_the_new_page_renders_the_create_form(client_as, kind):
    response = client_as("editor").get(f"/admin/{kind}/new")
    assert response.status_code == 200
    page = response.text
    form = re.search(rf'<form class="admin-content-editing" method="post" action="/admin/{kind}"'
                     r'[^>]*>(.*?)</form>', page, re.S)
    assert form, "no create form posting to the list"
    for name in ("csrf_token", "title", "summary", "slug", "body"):
        assert f'name="{name}"' in form.group(1), name
    assert ('type="file"' in form.group(1)) == (kind == "reports")
    assert "admin-site-preview" in page and "editor.js" in page


@pytest.mark.parametrize("kind", LISTS)
def test_a_create_redirects_to_the_new_items_edit_page(client_as, kind):
    key, item = LISTS[kind]
    analyst = client_as("editor")
    response = post_form(analyst, f"/admin/{kind}", item)
    assert response.status_code == 303
    item_id = response.headers["location"].removeprefix(f"/admin/{kind}/")
    assert item_id.isdigit()
    assert row_ids(analyst.get(f"/admin/{kind}").text, key) == [item_id]
    edit = analyst.get(response.headers["location"])
    assert edit.status_code == 200 and item["title"] in edit.text


@pytest.mark.parametrize("kind, field, sent, message", [
    ("data-bites", "title", {"title": " "}, "Enter a title."),
    ("data-bites", "slug", {"slug": "Not A Slug"}, "Slugs use lowercase"),
    ("data-bites", "body", {"body": " "}, "Enter a body."),
    ("reports", "slug", {"slug": "index"}, "is reserved"),
    ("reports", "summary", {"summary": "x" * 201}, "Keep the summary to"),
])
def test_a_refused_create_rerenders_the_new_page_with_the_error_by_its_field(
        client_as, kind, field, sent, message):
    key, item = LISTS[kind]
    analyst = client_as("editor")
    response = post_form(analyst, f"/admin/{kind}", {**item, **sent})
    assert response.status_code == 400
    page = response.text
    error = re.search(rf'<small id="{field}-error" class="admin-field-error" role="alert">([^<]+)<',
                      page)
    assert error and message in error.group(1)
    control = re.search(rf'<(?:input|textarea)[^>]*name="{field}"[^>]*>', page)
    assert control and 'aria-invalid="true"' in control.group(0)
    assert re.search(rf'aria-describedby="[^"]*\b{field}-error"', control.group(0))
    assert '<p class="alert-console" role="alert">' not in page  # it's by the field, not above
    assert "<h1>New " in page  # the /new page, not the list
    assert row_ids(analyst.get(f"/admin/{kind}").text, key) == []


def test_a_duplicate_slug_is_shown_by_the_slug(client_as):
    analyst = client_as("editor")
    create(analyst, "data-bites", "fall")
    response = post_form(analyst, "/admin/data-bites", {**BITE, "slug": "fall"})
    assert response.status_code == 400
    assert re.search(r'<small id="slug-error" class="admin-field-error" role="alert">'
                     r'Another Data Bite already uses the slug fall.<', response.text)


def test_a_refused_pdf_is_shown_by_the_file_field(client_as):
    analyst = client_as("editor")
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', analyst.get("/admin").text).group(1)
    response = analyst.post("/admin/reports", data={**REPORT, "csrf_token": csrf},
                            files={"file": ("x.pdf", b"not a pdf", "application/pdf")},
                            follow_redirects=False)
    assert response.status_code == 400
    assert re.search(r'<small id="file-error" class="admin-field-error" role="alert">'
                     r'That file is not a valid PDF.<', response.text)


@pytest.mark.parametrize("kind", LISTS)
def test_the_new_page_marks_its_section_in_the_nav(client_as, kind):
    label = "Data Bites" if kind == "data-bites" else "Reports"
    page = client_as("editor").get(f"/admin/{kind}/new").text
    assert re.search(rf'aria-current="page"><span class="text-mono">\d\d</span>{label}<', page)


# --- All content -------------------------------------------------------------

def test_all_content_uses_the_same_table(client_as):
    director = client_as("admin")
    bid = create(director, "data-bites", "fall", summary="A bite.")
    rid = create(director, "reports", "factbook")
    page = director.get("/admin/content").text
    assert '<table class="table-items table-items-stack" role="table">' in page
    bite = row(page, "data-bite", bid)
    assert '<p>A bite.</p>' in bite and "badge-state-draft" in bite
    assert f'action="/admin/data-bites/{bid}/publish"' in bite
    assert f'href="/admin/reports/{rid}/delete"' in row(page, "report", rid)


def test_the_lists_stack_on_a_phone(client_as):
    analyst = client_as("editor")
    create(analyst, "data-bites", "fall"), create(analyst, "reports", "factbook")
    for path in ("/admin/data-bites", "/admin/reports", "/admin/content"):
        assert '<table class="table-items table-items-stack" role="table">' in analyst.get(path).text
