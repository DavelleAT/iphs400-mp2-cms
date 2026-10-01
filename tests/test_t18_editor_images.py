"""T18: Chart images in the Editor (issue #21).

The Editor's "Insert image" lists the item's Chart images, from the edit
page, and puts one in the body with a description; the server reads it back
as `![Description](image:<name>)` (app.markdown_form), as T10/T11 store it.
What the Editor does in the browser is checked by hand (the closing comment);
here, what the server gives it and what a post of its HTML saves.
"""
from __future__ import annotations

import json
import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from app.editor import tokenize
from app.markdown_form import to_markdown
from app.rendering import render_markdown
from tests.test_t03_data_bites import create_bite
from tests.test_t04_reports import create_report
from tests.test_t10_chart_images import CHART, img_tags, png
from tests.test_t10_chart_images import upload as upload_to_bite
from tests.test_t11_report_chart_images import upload as upload_to_report
from tests.test_t12_site_preview import preview
from tests.test_t13_editor_routes import edit_page, editor_content, save, stored

KINDS = [pytest.param("data-bites", create_bite, upload_to_bite, id="data-bite"),
         pytest.param("reports", create_report, upload_to_report, id="report")]


def body_images(page: str) -> list[dict] | None:
    """The Chart images the page's Editor may insert; None if it is given
    none to list, as on a create page."""
    found = re.findall(r"""<div class="admin-editor"[^>]*? data-images='([^']*)'""", page)
    return json.loads(unescape(found[0])) if found else None


def img(kind: str, item_id: str, name: str, alt: str) -> str:
    """A chart image as the Editor shows and posts it: from the admin route."""
    return f'<img src="/admin/{kind}/{item_id}/images/{name}" alt="{alt}">'


def module_for(kind: str):
    from app import data_bites, reports
    return data_bites if kind == "data-bites" else reports


@pytest.fixture
def analyst(client_as) -> TestClient:
    return client_as("editor")


# What the Editor is given.

@pytest.mark.parametrize("kind, create, upload", KINDS)
def test_the_edit_page_gives_the_editor_its_chart_images_by_name_and_admin_src(
        analyst, kind, create, upload):
    item_id = create(analyst)
    assert body_images(edit_page(analyst, kind, item_id)) == []

    upload(analyst, item_id, png("spring.png"))
    upload(analyst, item_id, png("fall-by-class.png"))
    images = body_images(edit_page(analyst, kind, item_id))
    assert images == [
        {"name": "fall-by-class.png", "src": f"/admin/{kind}/{item_id}/images/fall-by-class.png"},
        {"name": "spring.png", "src": f"/admin/{kind}/{item_id}/images/spring.png"}]
    # Each src is the thumbnail the Editor shows, served to a signed-in user.
    assert analyst.get(images[0]["src"]).content == png()[1]


@pytest.mark.parametrize("kind, create, upload", KINDS)
def test_a_create_page_gives_the_editor_no_images_to_list(analyst, kind, create, upload):
    page = analyst.get(f"/admin/{kind}").text
    assert 'class="admin-editor"' in page
    assert body_images(page) is None


@pytest.mark.parametrize("kind, create, upload", KINDS)
def test_the_copy_a_snippet_list_is_gone_but_each_image_can_still_be_deleted(
        analyst, kind, create, upload):
    item_id = create(analyst)
    upload(analyst, item_id, png())
    page = edit_page(analyst, kind, item_id)
    section = page[page.index('<section class="content-images"'):]
    assert "![Description](image:" not in page
    assert "fall-by-class.png" in section
    assert f'action="/admin/{kind}/{item_id}/images/fall-by-class.png/delete"' in section
    assert "Insert image" in section


# What an insert, a change, or a removal saves.

@pytest.mark.parametrize("kind, create, upload", KINDS)
def test_an_inserted_image_is_stored_as_its_image_reference(analyst, kind, create, upload):
    item_id = create(analyst, body="Enrollment by class:")
    upload(analyst, item_id, png())
    page = edit_page(analyst, kind, item_id)

    # As the Editor places it: a paragraph of its own after the cursor's.
    html = (editor_content(page)
            + f'<p>{img(kind, item_id, "fall-by-class.png", "Fall enrollment by class")}</p>'
            + "<p>Source: IR.</p>")
    assert save(analyst, kind, item_id, page, body_html=html, body_dirty="1").status_code == 303
    assert stored(module_for(kind), item_id)["body"] == (
        "Enrollment by class:\n\n![Fall enrollment by class](image:fall-by-class.png)\n\n"
        "Source: IR.\n")
    # And the Editor shows it again from its admin route, with its description.
    assert img(kind, item_id, "fall-by-class.png", "Fall enrollment by class") in editor_content(
        edit_page(analyst, kind, item_id))


def test_a_descriptions_escaped_characters_reach_the_alt_and_lock_nothing():
    """to_markdown escapes them; markdown-it leaves an escape in an image's
    description as its own token, which the alt dropped and the Editor
    locked the paragraph for."""
    body = to_markdown('<p><img src="S" alt="Fall [2025] *by* class &amp; year"></p>',
                       {"S": "a.png"}.get)
    assert body == "![Fall \\[2025\\] \\*by\\* class \\& year](image:a.png)\n"
    assert tokenize(body).locked == ()
    assert 'alt="Fall [2025] *by* class &amp; year"' in str(render_markdown(body, lambda n: n))
    assert 'alt="A &amp; B"' in str(render_markdown("![A &amp; B](image:a.png)", lambda n: n))


@pytest.mark.parametrize("kind, create, upload", KINDS)
def test_a_description_with_markdown_characters_is_kept_as_typed(analyst, kind, create, upload):
    item_id = create(analyst)
    upload(analyst, item_id, png())
    page = edit_page(analyst, kind, item_id)
    alt = "Fall [2025] enrollment *by* class &amp; year"
    html = f'<p>{img(kind, item_id, "fall-by-class.png", alt)}</p>'
    save(analyst, kind, item_id, page, body_html=html, body_dirty="1")

    page = edit_page(analyst, kind, item_id)
    assert img(kind, item_id, "fall-by-class.png", alt) in editor_content(page)


@pytest.mark.parametrize("kind, create, upload", KINDS)
def test_changing_a_description_or_removing_an_image_changes_only_that(
        analyst, kind, create, upload):
    item_id = create(analyst, body=CHART)
    upload(analyst, item_id, png())
    page = edit_page(analyst, kind, item_id)
    shown = editor_content(page)
    old = img(kind, item_id, "fall-by-class.png", "Fall enrollment by class")
    assert old in shown

    changed = shown.replace(old, img(kind, item_id, "fall-by-class.png", "Students by class, fall 2026"))
    assert save(analyst, kind, item_id, page, body_html=changed, body_dirty="1").status_code == 303
    assert stored(module_for(kind), item_id)["body"] == (
        "Enrollment by class:\n\n![Students by class, fall 2026](image:fall-by-class.png)\n")

    page = edit_page(analyst, kind, item_id)
    removed = re.sub(r"<p><img [^>]*></p>", "", editor_content(page))
    assert save(analyst, kind, item_id, page, body_html=removed, body_dirty="1").status_code == 303
    assert stored(module_for(kind), item_id)["body"] == "Enrollment by class:\n"


@pytest.mark.parametrize("kind, create, upload", KINDS)
def test_an_image_from_anywhere_else_is_left_out(analyst, kind, create, upload):
    item_id = create(analyst)
    other = create(analyst, slug="other-item")
    upload(analyst, other, png())
    page = edit_page(analyst, kind, item_id)
    html = (f'<p>Before {img(kind, other, "fall-by-class.png", "Another item")} after'
            '<img src="https://example.test/chart.png" alt="Hot-linked"></p>')
    save(analyst, kind, item_id, page, body_html=html, body_dirty="1")
    assert stored(module_for(kind), item_id)["body"] == "Before  after\n"


# The description: required in the Editor, only warned of by the server.

@pytest.mark.parametrize("kind, create, upload", KINDS)
def test_an_image_with_no_description_saves_and_is_warned_of(analyst, kind, create, upload):
    item_id = create(analyst)
    upload(analyst, item_id, png())
    page = edit_page(analyst, kind, item_id)
    html = f'<p>{img(kind, item_id, "fall-by-class.png", "")}</p>'
    assert save(analyst, kind, item_id, page, body_html=html, body_dirty="1").status_code == 303
    assert stored(module_for(kind), item_id)["body"] == "![](image:fall-by-class.png)\n"

    page = edit_page(analyst, kind, item_id)
    warning = re.search(r'<p class="content-image-warning"[^>]*>(.*?)</p>', page, re.S)
    assert warning and "fall-by-class.png" in warning[1]
    # It tells the writer how to fix it in the Editor, not in Markdown.
    assert "![" not in warning[1]


# The Site preview.

@pytest.mark.parametrize("kind, create, upload", KINDS)
def test_an_inserted_image_shows_in_the_site_preview_before_it_is_saved(
        analyst, kind, create, upload):
    item_id = create(analyst)
    upload(analyst, item_id, png())
    before = stored(module_for(kind), item_id)["body"]
    page = edit_page(analyst, kind, item_id)
    html = f'<p>{img(kind, item_id, "fall-by-class.png", "Fall enrollment by class")}</p>'
    shown = preview(analyst, kind, item_id, title="Fall", body="", body_html=html,
                    body_dirty="1", item_base=re.search(r'name="item_base" value="([^"]*)"', page)[1])
    assert shown.status_code == 200
    [tag] = img_tags(shown.text)
    assert re.fullmatch(r'<img src="\.\./images/[a-z-]+/[a-z-]+/fall-by-class\.png" '
                        r'alt="Fall enrollment by class">', tag), tag
    assert stored(module_for(kind), item_id)["body"] == before
