"""T17: Chart builder (issue #20). In the Editor's body, a valid top-level
Chart is a card showing its drawn chart (app.editor), and the card is saved
as the canonical `chart` block (app.markdown_form). Anything else that looks
like a Chart stays a locked block."""
from __future__ import annotations

import json
import re
from html import escape, unescape

import pytest

from app import charts, data_bites
from app.content import ContentError
from app.editor import editor_html, tokenize
from app.markdown_form import to_markdown
from tests.test_t03_data_bites import create_bite
from tests.test_t13_editor_routes import edit_page, editor_content, save, textarea
from tests.test_t16_chart_saves import fallback_save, store_body, stored_body
from tests.test_t16_charts import CANONICAL, fence, series, source

CARD = re.compile(r'<div class="admin-editor-chart" data-chart="([^"]*)">')


def cards(html: str) -> list[str]:
    """Each card's Chart, as its data-chart holds it."""
    return [unescape(value) for value in CARD.findall(html)]


def card(text: str, content: str = "") -> str:
    """A card as the Editor posts it back."""
    return f'<div class="admin-editor-chart" data-chart="{escape(text)}">{content}</div>'


@pytest.fixture
def analyst(client_as):
    return client_as("editor")


# What the Editor shows.

def test_a_valid_chart_is_a_card_with_its_drawing_and_its_canonical_block():
    body = "Intro.\n\n" + fence(source()) + "\nOutro.\n"
    assert tokenize(body).locked == ()
    html = str(editor_html(tokenize(body).markdown, body, None))
    assert cards(html) == [charts.parse(source()).canonical()]
    assert 'class="chart-figure"' in html and "Fall enrollment by class" in html
    assert "data-locked" not in html and "```" not in html
    assert html.index("Intro.") < html.index("admin-editor-chart") < html.index("Outro.")


def test_each_of_several_charts_is_its_own_card_in_order():
    first, second = source(title="First"), source(title="Second", type="hbar")
    body = fence(first) + "\nBetween.\n\n" + fence(second)
    html = str(editor_html(body, body, None))
    assert [json.loads(chart)["title"] for chart in cards(html)] == ["First", "Second"]
    assert len(set(re.findall(r'id="(chart-[0-9a-f]{32}-\d+-title)"', html))) == 2


def test_a_chart_straight_after_a_paragraph_is_still_its_own_card():
    body = "Intro.\n" + fence(source())
    html = str(editor_html(body, body, None))
    assert len(cards(html)) == 1 and "<p>Intro.</p>" in html


@pytest.mark.parametrize("body", [
    fence(source(title="")),
    fence("{"),
    "> " + fence(source()).replace("\n", "\n> ").rstrip("> "),
    "- item\n\n  " + fence(source()).replace("\n", "\n  ").rstrip(" "),
])
def test_an_invalid_or_nested_chart_is_a_locked_block(body):
    assert len(tokenize(body).locked) == 1
    html = str(editor_html(tokenize(body).markdown, body, None))
    assert cards(html) == [] and "data-locked" in html


def test_writer_text_in_a_card_is_escaped():
    hostile = '"><script>alert(1)</script>'
    body = fence(source(title=hostile))
    html = str(editor_html(body, body, None))
    assert "<script>" not in html
    assert json.loads(cards(html)[0])["title"] == hostile


# What a card saves.

def test_a_card_is_saved_as_the_canonical_block():
    shuffled = json.dumps(dict(reversed(list(json.loads(CANONICAL).items()))))
    html = "<p>Intro.</p>" + card(shuffled, "<figure>drawn</figure>") + "<p>Outro.</p>"
    assert to_markdown(html) == f"Intro.\n\n```chart\n{CANONICAL}```\n\nOutro.\n"


def test_what_a_card_shows_is_never_saved():
    html = card(source(), "<p>Not saved</p><table><tr><td>9</td></tr></table>")
    assert "Not saved" not in to_markdown(html) and "| 9" not in to_markdown(html)


@pytest.mark.parametrize("html", [
    f"<ul><li>{card(source())}</li></ul>",
    f"<blockquote>{card(source())}</blockquote>",
    f"<p>Text {card(source())}</p>",
    f"<table><tr><td>{card(source())}</td></tr></table>",
])
def test_a_card_moved_into_another_block_is_refused(html):
    with pytest.raises(ContentError, match="A Chart was moved into"):
        to_markdown(html)


@pytest.mark.parametrize("text, message", [
    ("{", "Chart 2: its data can't be read"),
    (source(title=""), "Chart 2: the title must be"),
    ('{"title": "```\\n# Injected"}', "Chart 2: "),
])
def test_a_card_whose_chart_is_invalid_is_refused_by_its_place(text, message):
    html = card(source()) + "<p>Between.</p>" + card(text)
    with pytest.raises(ContentError, match=re.escape(message)):
        to_markdown(html)


# Through the edit form.

def test_a_round_trip_through_the_editor_saves_the_canonical_block(analyst):
    body = "Intro.\n\n" + fence(CANONICAL.removesuffix("\n"))
    item_id = create_bite(analyst, body=body)
    page = edit_page(analyst, "data-bites", item_id)
    edited = editor_content(page).replace("Intro.", "Intro, edited.")
    assert save(analyst, "data-bites", item_id, page, body_dirty="1",
                body_html=edited).status_code == 303
    assert stored_body(data_bites, item_id) == body.replace("Intro.", "Intro, edited.")


def test_an_untouched_body_with_a_card_keeps_its_bytes(analyst):
    body = "Intro.\n\n~~~chart\n" + source() + "\n~~~\n"
    item_id = create_bite(analyst)
    store_body(data_bites, item_id, body)
    page = edit_page(analyst, "data-bites", item_id)
    assert save(analyst, "data-bites", item_id, page).status_code == 303
    assert stored_body(data_bites, item_id) == body


@pytest.mark.parametrize("path", ["editor", "fallback"])
def test_an_edit_around_a_stored_chart_saves_it_in_canonical_form(analyst, path):
    item_id = create_bite(analyst)
    store_body(data_bites, item_id, "Intro.\n\n~~~chart\n" + source() + "\n~~~\n")
    page = edit_page(analyst, "data-bites", item_id)
    if path == "editor":
        response = save(analyst, "data-bites", item_id, page, body_dirty="1",
                        body_html=editor_content(page).replace("Intro.", "Intro, edited."))
    else:
        assert source() in textarea(page)
        response = fallback_save(analyst, "data-bites", item_id, page,
                                 textarea(page).replace("Intro.", "Intro, edited."))
    assert response.status_code == 303
    canonical = charts.parse(source()).canonical()
    assert stored_body(data_bites, item_id) == f"Intro, edited.\n\n```chart\n{canonical}```\n"


def test_a_chart_inserted_by_the_builder_is_saved(analyst):
    item_id = create_bite(analyst)
    page = edit_page(analyst, "data-bites", item_id)
    chart = charts.parse(source(series=[series("1", "<10")])).canonical()
    response = save(analyst, "data-bites", item_id, page, body_dirty="1",
                    body_html=f"<p>Intro.</p>{card(chart)}<p></p>")
    assert response.status_code == 303
    assert stored_body(data_bites, item_id) == f"Intro.\n\n```chart\n{chart}```\n"


def test_removing_a_card_removes_its_chart(analyst):
    item_id = create_bite(analyst, body="Intro.\n\n" + fence(source()))
    page = edit_page(analyst, "data-bites", item_id)
    edited = re.sub(r'<div class="admin-editor-chart".*', "", editor_content(page), flags=re.S)
    assert save(analyst, "data-bites", item_id, page, body_dirty="1",
                body_html=edited).status_code == 303
    assert stored_body(data_bites, item_id) == "Intro.\n"


def test_an_invalid_card_refuses_the_save_and_names_the_chart(analyst):
    item_id = create_bite(analyst, body="Intro.\n")
    page = edit_page(analyst, "data-bites", item_id)
    response = save(analyst, "data-bites", item_id, page, body_dirty="1",
                    body_html="<p>Intro.</p>" + card(source(series=[series("1", "abc")])))
    assert response.status_code == 400
    assert "Chart 1: series 'Fall 2025', 'Senior': 'abc' isn" in unescape(response.text)
    assert stored_body(data_bites, item_id) == "Intro.\n"


def test_the_site_preview_draws_a_card(analyst):
    from tests.conftest import csrf_from
    item_id = create_bite(analyst, body="Intro.\n")
    page = edit_page(analyst, "data-bites", item_id)
    response = analyst.post(f"/admin/data-bites/{item_id}/preview", data={
        "title": "T", "body": "", "body_dirty": "1", "csrf_token": csrf_from(page),
        "body_html": "<p>Intro.</p>" + card(source())})
    assert response.status_code == 200
    assert 'class="chart-figure"' in response.text and "data-chart" not in response.text
