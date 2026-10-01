"""T16: Chart rendering (issue #19). A body with an invalid Chart is refused
with a named error on every save path, the Editor's and the Markdown
fallback's, and a Chart saved from an edited body is in canonical form."""
from __future__ import annotations

import json
import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from app import data_bites, db, reports
from tests.conftest import csrf_from, post_form, stored_slugs
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import REPORT, create_report
from tests.test_t13_editor_routes import edit_page, field, save, textarea
from tests.test_t16_charts import CANONICAL, VIOLATIONS, fence, source

KINDS = [pytest.param("data-bites", BITE, create_bite, data_bites, id="data-bite"),
         pytest.param("reports", REPORT, create_report, reports, id="report")]


def error_of(response) -> str:
    """The refused form's page, as text a writer reads."""
    assert response.status_code == 400, response.status_code
    return unescape(response.text)


def store_body(module, item_id: str, body: str) -> None:
    """Write a body as it may have been stored under older rules, past
    every save path's checks."""
    table = {data_bites: "data_bites", reports: "reports"}[module]
    with db.connect() as conn:
        conn.execute(f"UPDATE {table} SET body = ? WHERE id = ?", (body, item_id))


def stored_body(module, item_id: str) -> str:
    return module.get(int(item_id))["body"]


def fallback_save(c: TestClient, kind: str, item_id: str, page: str, body: str):
    """POST the edit form as it is without the Editor's script: the
    textarea's Markdown, and no Editor HTML."""
    return c.post(f"/admin/{kind}/{item_id}", follow_redirects=False, data={
        "title": re.search(r'name="title" value="([^"]*)"', page)[1],
        "slug": re.search(r'name="slug" value="([^"]*)"', page)[1],
        "body": body, "item_base": field(page, "item_base"), "csrf_token": csrf_from(page)})


@pytest.fixture
def analyst(client_as):
    return client_as("editor")


# Refused on every save path.

@pytest.mark.parametrize("text, message", VIOLATIONS)
def test_the_markdown_fallback_refuses_each_invalid_chart_by_name(analyst, text, message):
    body = "Intro.\n\n" + fence(source()) + "\n" + fence(text)
    page = error_of(post_form(analyst, "/admin/data-bites", {**BITE, "body": body}))
    assert "Chart 2: " in page and message in page
    assert BITE["slug"] not in stored_slugs("data_bites")


@pytest.mark.parametrize("text, message", VIOLATIONS)
def test_the_editor_refuses_a_stored_invalid_chart_by_name(analyst, text, message):
    """A Chart stored under older rules reaches the Editor's save path as a
    locked block. Saving the item, untouched or not, names it."""
    item_id = create_bite(analyst)
    body = "Intro.\n\n" + fence(text)
    store_body(data_bites, item_id, body)
    page = edit_page(analyst, "data-bites", item_id)
    assert "Chart 1: " in error_of(save(analyst, "data-bites", item_id, page))
    edited = error_of(save(analyst, "data-bites", item_id, page, body_dirty="1",
                           body_html="<p>Intro, edited.</p>" + _locked(page)))
    assert "Chart 1: " in edited and message in edited
    assert stored_body(data_bites, item_id) == body


def _locked(page: str) -> str:
    """The locked block in the Editor's HTML, as the Editor posts it back."""
    [token] = re.findall(r'data-locked="(locked-\d+)"', page)
    return f'<div data-locked="{token}"></div>'


@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_both_kinds_refuse_an_invalid_chart_on_create_and_edit(client_as, kind, item, create,
                                                                module):
    director = client_as("admin")
    invalid = "Intro.\n\n" + fence(source(series=[{"name": "Fall 2025", "values": ["1"]}]))
    message = "Chart 1: series 'Fall 2025' has 1 values but 2 categories"
    assert message in error_of(post_form(director, f"/admin/{kind}", {**item, "body": invalid}))
    item_id = create(director)
    page = edit_page(director, kind, item_id)
    assert message in error_of(fallback_save(director, kind, item_id, page, invalid))
    assert stored_body(module, item_id) == item["body"]
    store_body(module, item_id, invalid)
    assert message in error_of(save(director, kind, item_id, edit_page(director, kind, item_id)))
    assert stored_body(module, item_id) == invalid


def test_removing_an_invalid_chart_in_the_editor_saves(analyst):
    item_id = create_bite(analyst)
    store_body(data_bites, item_id, "Intro.\n\n" + fence("{"))
    page = edit_page(analyst, "data-bites", item_id)
    response = save(analyst, "data-bites", item_id, page, body_dirty="1",
                    body_html="<p>Intro, edited.</p>")
    assert response.status_code == 303
    assert stored_body(data_bites, item_id) == "Intro, edited.\n"


def test_a_valid_chart_saves(analyst):
    body = "Intro.\n\n" + fence(source())
    assert post_form(analyst, "/admin/data-bites", {**BITE, "body": body}).status_code == 303


# The canonical form.

def _shuffled() -> str:
    data = json.loads(CANONICAL)
    return json.dumps(dict(reversed(list(data.items()))))


def test_a_chart_typed_in_the_fallback_is_saved_in_canonical_form(analyst):
    body = f"Intro.\r\n\r\n~~~chart\r\n{_shuffled()}\r\n~~~\r\n\r\nOutro.\r\n"
    item_id = create_bite(analyst, body=body)
    canonical = CANONICAL.replace("\n", "\r\n")
    assert stored_body(data_bites, item_id) == (
        f"Intro.\r\n\r\n```chart\r\n{canonical}```\r\n\r\nOutro.\r\n")


def test_saving_a_canonical_chart_again_changes_nothing(analyst):
    body = "Intro.\n\n" + fence(CANONICAL.removesuffix("\n"))
    item_id = create_bite(analyst, body=body)
    assert stored_body(data_bites, item_id) == body
    page = edit_page(analyst, "data-bites", item_id)
    assert fallback_save(analyst, "data-bites", item_id, page,
                         textarea(page) + "\nMore.\n").status_code == 303
    assert stored_body(data_bites, item_id) == body + "\nMore.\n"


def test_a_stored_chart_not_in_canonical_form_keeps_its_bytes_untouched(analyst):
    """Saved untouched, its bytes are the stored ones (ADR-005). Since T17 a
    valid Chart is a card, so an edit around it saves it in canonical form
    (test_t17_chart_cards.py)."""
    item_id = create_bite(analyst)
    chart = f"~~~chart\n{_shuffled()}\n~~~"
    store_body(data_bites, item_id, f"Intro.\n\n{chart}\n")
    page = edit_page(analyst, "data-bites", item_id)
    assert save(analyst, "data-bites", item_id, page).status_code == 303
    assert stored_body(data_bites, item_id) == f"Intro.\n\n{chart}\n"
