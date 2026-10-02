"""T23: Edit pages (issue #28, spec #25).

A Data Bite's or Report's edit page is two columns: the fields and the
Editor, then a Report's PDF and the chart images, beside a sticky Site
preview. A save bar pinned to the bottom holds the State badge, an "Unsaved
changes" marker, and Save, Publish or Unpublish, and Delete, each only where
the user may do it, and each posting with its CSRF token. A Report locked
for an Analyst keeps its read-only view.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import csrf_from, post_form
from tests.test_t03_data_bites import create_bite
from tests.test_t04_reports import create_report
from tests.test_t13_editor_routes import STALE, save

KINDS = [pytest.param("data-bites", create_bite, id="data-bite"),
         pytest.param("reports", create_report, id="report")]
ROOT = Path(__file__).resolve().parent.parent


def save_bar(page: str) -> str:
    match = re.search(r'<div class="bar-save" role="region" aria-label="Save">(.*?)</div></div>',
                      page, re.S)
    assert match, "no save bar"
    return match.group(1)


def form_with_id(page: str, form_id: str) -> str:
    match = re.search(rf'<form id="{form_id}"[^>]*>(.*?)</form>', page, re.S)
    assert match, f"no form #{form_id}"
    return match.group(0)


def bar_buttons(page: str) -> dict[str, str]:
    """The save bar's actions: each button or link's text, and what it does
    (the form it posts, or where it leads)."""
    bar = save_bar(page)
    actions = {}
    for attributes, label in re.findall(r"<button ([^>]*)>([^<]+)</button>", bar):
        owner = re.search(r'form="([^"]+)"', attributes)
        actions[label] = form_with_id(page, owner[1]) if owner else None
    for form in re.findall(r"<form [^>]*>.*?</form>", bar, re.S):
        actions[re.search(r">([^<]+)</button>", form)[1]] = form
    for href, label in re.findall(r'<a class="[^"]*" href="([^"]+)">([^<]+)</a>', bar):
        actions[label] = href
    return actions


def publish(director: TestClient, kind: str, item_id: str) -> None:
    assert post_form(director, f"/admin/{kind}/{item_id}/publish", {}).status_code == 303


# --- The layout --------------------------------------------------------------

@pytest.mark.parametrize("kind, create", KINDS)
def test_the_fields_and_editor_sit_beside_the_site_preview(client_as, kind, create):
    director = client_as("admin")
    page = director.get(f"/admin/{kind}/{create(director)}").text
    grid = page[page.index('<div class="grid-edit">'):]
    form_at = grid.index('<form id="form-item"')
    preview_at = grid.index('<section class="admin-site-preview preview-console"')
    assert form_at < grid.index('class="admin-editor"') < preview_at
    assert 'class="field-console field-console-title"' in page
    # The slug as the item's address on the site.
    folder = "data-bites" if kind == "data-bites" else "reports"
    assert re.search(rf'<div class="field-console-slug"><span>{folder}/</span><input type="text" '
                     r'id="slug" name="slug" value="[^"]*"[^>]*><span>\.html</span></div>', page)
    assert '<label for="slug">Address</label>' in page


def test_a_reports_pdf_and_chart_images_sit_below_the_editor(client_as):
    director = client_as("admin")
    page = director.get(f"/admin/reports/{create_report(director)}").text
    editor = page.index('class="admin-editor"')
    assert editor < page.index('type="file" name="file" accept="application/pdf')
    assert editor < page.index('<section class="content-images"') < page.index(
        '<section class="admin-site-preview')


# --- The save bar ------------------------------------------------------------

@pytest.mark.parametrize("kind, create", KINDS)
def test_every_save_bar_action_posts_with_its_csrf_token(client_as, kind, create):
    director = client_as("admin")
    item_id = create(director)
    page = director.get(f"/admin/{kind}/{item_id}").text
    actions = bar_buttons(page)
    assert set(actions) == {"Save changes", "Publish", "Delete"}
    token = csrf_from(page)
    for label in ("Save changes", "Publish"):
        assert 'method="post"' in actions[label], label
        assert f'name="csrf_token" value="{token}"' in actions[label], label
    assert f'action="/admin/{kind}/{item_id}"' in actions["Save changes"]
    assert f'action="/admin/{kind}/{item_id}/publish"' in actions["Publish"]
    # Delete opens the confirmation page, whose form posts with the token.
    assert actions["Delete"] == f"/admin/{kind}/{item_id}/delete"
    confirm = director.get(actions["Delete"]).text
    assert re.search(rf'<form class="actions-form" method="post" action="/admin/{kind}/{item_id}/delete">'
                     rf'\s*<input type="hidden" name="csrf_token" value="{token}">', confirm)


@pytest.mark.parametrize("kind, create", KINDS)
def test_publish_and_unpublish_from_the_save_bar_return_to_the_edit_page(client_as, kind, create):
    director = client_as("admin")
    item_id = create(director)
    edit = f"/admin/{kind}/{item_id}"
    for label, state in (("Publish", "Published"), ("Unpublish", "Draft")):
        form = bar_buttons(director.get(edit).text)[label]
        action = re.search(r'action="([^"]+)"', form)[1]
        fields = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', form))
        response = director.post(action, data=fields, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == edit
        bar = save_bar(director.get(edit).text)
        assert f'<span class="badge-state badge-state-{state.lower()}">{state}</span>' in bar


@pytest.mark.parametrize("kind, create", KINDS)
def test_a_save_bar_action_without_its_token_is_refused(client_as, kind, create):
    director = client_as("admin")
    item_id = create(director)
    for path in (f"/admin/{kind}/{item_id}", f"/admin/{kind}/{item_id}/publish"):
        response = post_form(director, path, {"title": "No token"}, with_csrf=False)
        assert response.status_code == 403, path


@pytest.mark.parametrize("kind, create", KINDS)
def test_save_from_the_save_bar_still_refuses_a_stale_form(client_as, kind, create):
    director = client_as("admin")
    item_id = create(director)
    edit = f"/admin/{kind}/{item_id}"
    tab_a, tab_b = director.get(edit).text, director.get(edit).text
    assert save(director, kind, item_id, tab_b, title="Saved in tab B").status_code == 303
    response = save(director, kind, item_id, tab_a, title="Saved in tab A")
    assert response.status_code == 409 and STALE in response.text
    # The refusal keeps the save bar, and its unsaved title is marked as such.
    assert "Save changes" in bar_buttons(response.text)
    assert '<span class="bar-save-dirty">Unsaved changes</span>' in save_bar(response.text)


def test_save_is_the_forms_first_submit_button_so_enter_saves(client_as):
    """The save bar sits after the fields but before the Site preview, whose
    "Open" also submits the item's form: the first submit button in the page
    that belongs to a form is the one Enter presses."""
    director = client_as("admin")
    page = director.get(f"/admin/data-bites/{create_bite(director)}").text
    owned = [m.start() for m in re.finditer(r'<button [^>]*type="submit"[^>]*form="form-item"'
                                            r'|<button [^>]*form="form-item"[^>]*type="submit"', page)]
    assert owned and page.index(">Save changes</button>") < page.index(">Open<")
    assert page.rfind("<button", 0, page.index(">Save changes</button>")) == owned[0]


def test_an_analyst_may_save_and_publish_a_data_bite_but_not_delete_it(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    item_id = create_bite(director)
    assert set(bar_buttons(analyst.get(f"/admin/data-bites/{item_id}").text)) == {
        "Save changes", "Publish"}


def test_an_analyst_may_save_a_draft_report_but_not_publish_or_delete_it(client_as):
    analyst = client_as("editor")
    item_id = create_report(analyst)
    assert set(bar_buttons(analyst.get(f"/admin/reports/{item_id}").text)) == {"Save changes"}


def test_a_locked_report_shows_an_analyst_no_save_bar_actions(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    item_id = create_report(analyst)
    publish(director, "reports", item_id)

    page = analyst.get(f"/admin/reports/{item_id}").text
    bar = save_bar(page)
    assert bar_buttons(page) == {}
    assert '<span class="badge-state badge-state-published">Published</span>' in bar
    assert "Only the Director can edit, unpublish, or delete a published Report." in page
    # The read-only view, in the new layout: no form to edit, the Site preview.
    assert 'name="title"' not in page and 'class="admin-editor"' not in page
    assert '<div class="grid-edit">' in page and "admin-site-preview-frame" in page
    assert "bar-save-dirty" not in page


# --- The "Unsaved changes" marker --------------------------------------------

@pytest.mark.parametrize("kind, create", KINDS)
def test_the_unsaved_marker_starts_hidden_on_a_saved_item(client_as, kind, create):
    director = client_as("admin")
    page = director.get(f"/admin/{kind}/{create(director)}").text
    assert '<span class="bar-save-dirty" hidden>Unsaved changes</span>' in save_bar(page)


def test_the_unsaved_marker_shows_after_a_refused_save_of_an_edited_body(client_as):
    director = client_as("admin")
    item_id = create_bite(director)
    page = director.get(f"/admin/data-bites/{item_id}").text
    response = save(director, "data-bites", item_id, page, slug="Not A Slug",
                    body_html="<p>Edited.</p>", body_dirty="1")
    assert response.status_code == 400
    assert '<span class="bar-save-dirty">Unsaved changes</span>' in save_bar(response.text)


@pytest.mark.parametrize("kind, create", KINDS)
def test_a_refused_save_of_only_a_field_is_unsaved_too(client_as, kind, create):
    """A refused save holds values that were never saved, whether or not the
    body changed: the marker shows, and the form tells the Editor, which warns
    before the page is left."""
    director = client_as("admin")
    item_id = create(director)
    page = director.get(f"/admin/{kind}/{item_id}").text
    response = save(director, kind, item_id, page, title="Retitled", slug="Not A Slug")
    assert response.status_code == 400
    assert '<span class="bar-save-dirty">Unsaved changes</span>' in save_bar(response.text)
    assert re.search(r'<form id="form-item"[^>]* data-unsaved="1"', response.text)
    # Opened afresh, nothing is unsaved.
    fresh = director.get(f"/admin/{kind}/{item_id}").text
    assert "data-unsaved" not in fresh and '<span class="bar-save-dirty" hidden>' in fresh


def test_the_marker_follows_the_editors_unsaved_state():
    """The Editor tells its form when it has unsaved changes (the only change
    to static/editor.js), and the save bar listens for it."""
    editor = (ROOT / "static/editor.js").read_text()
    bar = (ROOT / "templates/admin/_save_bar.html").read_text()
    assert 'new CustomEvent("admin-editor-unsaved")' in editor
    assert 'form.dataset.unsaved === "1"' in editor
    assert '"admin-editor-unsaved"' in bar


# --- The Editor and Chart builder, restyled ----------------------------------

def test_chart_cards_use_the_public_purples_and_greys():
    # The tokens are admin.css's; the Chart rules, editor.css's since T24.
    css = (ROOT / "static/admin.css").read_text() + (ROOT / "static/editor.css").read_text()
    for token in ("--color-chart-newest", "--color-chart-bright", "--color-chart-grey",
                  "--color-chart-neutral"):
        assert token in css, token
    for old in ("#3987e5", "#d95926", "#199e70", "#c98500"):
        assert old not in css, old
    assert ".chart-series-1, .chart-marker-1 { fill: var(--chart-1); }" in css
