"""T13: the Editor on the Data Bite and Report edit and create pages (issue
#16): the base version, untouched bodies, locked blocks, and the Markdown
fallback, through the routes."""
from __future__ import annotations

import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from app import data_bites, reports, users
from app.content import StaleItem, item_base
from tests.conftest import csrf_from, post_form
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import REPORT, create_report
from tests.test_t06_admin_console import site_preview_page
from tests.test_t09_tables import content_body
from tests.test_t13_editor import HOSTILE, LOCKED_BODY

KINDS = [pytest.param("data-bites", BITE, create_bite, data_bites, id="data-bite"),
         pytest.param("reports", REPORT, create_report, reports, id="report")]
STALE = "This item changed since you opened it. Reload to see the latest version."


def stored(module, item_id: str):
    return module.get(int(item_id))


def edit_page(c: TestClient, kind: str, item_id: str) -> str:
    response = c.get(f"/admin/{kind}/{item_id}")
    assert response.status_code == 200
    return response.text


def field(page: str, name: str) -> str:
    [value] = re.findall(rf'<input type="hidden" name="{name}" value="([^"]*)">', page)
    return unescape(value)


def textarea(page: str) -> str:
    [value] = re.findall(r'<textarea name="body"[^>]*>(.*?)</textarea>', page, re.S)
    return unescape(value)


def editor_content(page: str) -> str:
    """The Editor's HTML, which its script loads into the editable area."""
    [value] = re.findall(r'<template class="admin-editor-content">(.*?)</template>', page, re.S)
    return value


def save(c: TestClient, kind: str, item_id: str, page: str, **form):
    """POST the edit form as the Editor does, from `page` as opened: its base
    version, and the Editor's HTML untouched unless `form` says otherwise."""
    data = {"title": re.search(r'name="title" value="([^"]*)"', page)[1],
            "slug": re.search(r'name="slug" value="([^"]*)"', page)[1],
            "body": textarea(page), "item_base": field(page, "item_base"),
            "body_html": editor_content(page), "body_dirty": "0",
            "csrf_token": csrf_from(page), **form}
    return c.post(f"/admin/{kind}/{item_id}", data=data, follow_redirects=False)


@pytest.fixture
def director(client_as):
    return client_as("admin")


# The base version.

@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_the_edit_page_carries_the_base_version(director, kind, item, create, module):
    item_id = create(director)
    row = stored(module, item_id)
    page = edit_page(director, kind, item_id)
    assert field(page, "item_base") == item_base(row["title"], row["slug"], row["body"])
    assert editor_content(page).strip().startswith("<p>")


@pytest.mark.parametrize("change", [{"title": "Retitled by tab B"}, {"slug": "moved-by-tab-b"},
                                    {"body_html": "<p>Rewritten by tab B.</p>", "body_dirty": "1"}])
@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_a_save_from_a_stale_page_is_refused_and_writes_nothing(
        director, kind, item, create, module, change):
    item_id = create(director)
    tab_a = edit_page(director, kind, item_id)
    tab_b = edit_page(director, kind, item_id)
    assert save(director, kind, item_id, tab_b, **change).status_code == 303
    after_b = dict(stored(module, item_id))

    # Tab A saves its untouched body, and a new title.
    response = save(director, kind, item_id, tab_a, title="Tab A's title")
    assert response.status_code == 409
    assert STALE in response.text
    assert dict(stored(module, item_id)) == after_b
    # Tab A's unsaved title is still on screen, and saving again is refused.
    assert 'value="Tab A&#39;s title"' in response.text
    assert save(director, kind, item_id, response.text).status_code == 409


# Untouched and edited bodies.

@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_an_untouched_body_is_kept_byte_for_byte_whatever_html_is_posted(
        director, kind, item, create, module):
    body = "Soft\r\nwrapped   text *with* __odd__ spacing.\r\n\r\n* a list\r\n"
    item_id = create(director, body=body)
    page = edit_page(director, kind, item_id)
    assert save(director, kind, item_id, page, title="New title",
                body_html="<p>Something else entirely</p>").status_code == 303
    row = stored(module, item_id)
    assert row["body"] == body and row["title"] == "New title"


@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_an_edited_body_is_saved_in_standard_form(director, kind, item, create, module):
    item_id = create(director, body="Old  *body*\r\n\r\n* a list\r\n")
    page = edit_page(director, kind, item_id)
    html = editor_content(page).replace("Old", "New")
    assert save(director, kind, item_id, page, body_html=html, body_dirty="1").status_code == 303
    assert stored(module, item_id)["body"] == "New *body*\n\n- a list\n"


def test_the_editor_needs_the_base_version(director):
    item_id = create_bite(director)
    page = edit_page(director, "data-bites", item_id)
    assert save(director, "data-bites", item_id, page, item_base="",
                body_html="<p>x</p>", body_dirty="1").status_code == 400
    assert stored(data_bites, item_id)["body"] == BITE["body"]


# Locked blocks.

@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_a_locked_blocks_source_never_reaches_the_browser(director, kind, item, create, module):
    item_id = create(director, body=LOCKED_BODY)
    page = edit_page(director, kind, item_id)
    for source in ("```", "`inline code`", "<script>alert", "&lt;script&gt;alert('x')&lt;/script&gt;\n```"):
        assert source not in page, source
    assert textarea(page).splitlines()[2] == "locked-0"
    assert 'data-locked="locked-0"' in editor_content(page)
    assert "This part can&#39;t be edited here." in editor_content(page)
    # The Site preview shows the whole body, rendered.
    assert "<code>inline code</code>" in content_body(site_preview_page(page))


@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_locked_blocks_survive_an_edit_around_them(director, kind, item, create, module):
    item_id = create(director, body=LOCKED_BODY)
    page = edit_page(director, kind, item_id)
    html = re.sub(r'(data-locked="locked-\d+">).*?</div></div>', r"\1</div>",
                  editor_content(page), flags=re.S).replace("Middle", "Edited")
    assert save(director, kind, item_id, page, body_html=html, body_dirty="1").status_code == 303
    body = stored(module, item_id)["body"]
    assert "```\r\n<script>alert('x')</script>\r\n```" in body
    assert "Outro with `inline code`, kept." in body and "Edited paragraph." in body


@pytest.mark.parametrize("html", ['<div data-locked="locked-5"></div>',
                                  '<div data-locked="locked-0"></div>' * 2,
                                  '<div data-locked="locked-0"><p>forged</p></div>'])
def test_an_unknown_duplicated_or_forged_token_refuses_the_save(director, html):
    item_id = create_bite(director, body=LOCKED_BODY)
    page = edit_page(director, "data-bites", item_id)
    response = save(director, "data-bites", item_id, page, title="Changed",
                    body_html="<p>Intro.</p>" + html, body_dirty="1")
    assert response.status_code == 400
    # The Editor opens on the writer's edit, or if the Editor didn't make
    # it, on the stored body again: never on nothing.
    assert "<p>Intro" in editor_content(response.text)
    assert dict(stored(data_bites, item_id))["title"] == BITE["title"]
    assert stored(data_bites, item_id)["body"] == LOCKED_BODY


# The Markdown fallback: no script, so no body_html.

@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_the_fallback_textarea_saves_markdown_and_keeps_locked_blocks(
        director, kind, item, create, module):
    item_id = create(director, body=LOCKED_BODY)
    page = edit_page(director, kind, item_id)
    body = textarea(page).replace("Middle", "Edited")
    response = post_form(director, f"/admin/{kind}/{item_id}",
                         {"title": "T", "slug": "s", "body": body,
                          "item_base": field(page, "item_base")})
    assert response.status_code == 303
    assert stored(module, item_id)["body"] == LOCKED_BODY.replace("Middle", "Edited")


# Creating, previewing, and hostile HTML.

@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_the_create_page_saves_the_editors_html(director, kind, item, create, module):
    page = director.get(f"/admin/{kind}").text
    assert editor_content(page).strip() == ""
    response = director.post(f"/admin/{kind}", data={
        "title": "New", "slug": "new", "body": "", "body_html": "<p>Made in the <b>Editor</b></p>",
        "body_dirty": "1", "csrf_token": csrf_from(page)}, follow_redirects=False)
    assert response.status_code == 303
    [row] = [row for row in module.list_all() if row["slug"] == "new"]
    assert row["body"] == "Made in the **Editor**\n"


@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_the_site_preview_follows_the_editor(director, kind, item, create, module):
    item_id = create(director, body=LOCKED_BODY)
    page = edit_page(director, kind, item_id)
    html = re.sub(r'(data-locked="locked-\d+">).*?</div></div>', r"\1</div>",
                  editor_content(page), flags=re.S).replace("Middle", "Previewed")
    preview = post_form(director, f"/admin/{kind}/{item_id}/preview",
                        {"title": "T", "body": "", "body_html": html, "body_dirty": "1"})
    body = content_body(preview.text)
    assert "Previewed paragraph." in body and "<code>inline code</code>" in body
    untouched = post_form(director, f"/admin/{kind}/{item_id}/preview",
                          {"title": "T", "body": "", "body_html": "<p>x</p>", "body_dirty": "0"})
    assert "Middle paragraph." in content_body(untouched.text)
    new = post_form(director, f"/admin/{kind}/preview",
                    {"title": "T", "body": "", "body_html": "<h2>Fresh</h2>", "body_dirty": "1"})
    assert "<h2>Fresh</h2>" in content_body(new.text)


def test_hostile_editor_html_is_inert_on_the_public_page(director, client):
    item_id = create_bite(director)
    page = edit_page(director, "data-bites", item_id)
    assert save(director, "data-bites", item_id, page, body_html=HOSTILE,
                body_dirty="1").status_code == 303
    post_form(director, f"/admin/data-bites/{item_id}/publish", {})
    body = content_body(client.get(f"/data-bites/{BITE['slug']}.html").text)
    for bad in ("<script", "alert(", "onerror", "onclick", "style=", "javascript:", 'href="/'):
        assert bad not in body, bad


def test_the_editor_script_is_served_to_signed_in_users_only(director, client):
    assert director.get("/admin/editor.js").headers["content-type"].startswith("text/javascript")
    assert client.get("/admin/editor.js", follow_redirects=False).status_code == 303


@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_the_write_itself_checks_the_base_version(director, kind, item, create, module):
    """The save a route has checked is checked again where it is written, so
    one landing in between is not overwritten."""
    item_id = create(director)
    row = stored(module, item_id)
    base = item_base(row["title"], row["slug"], row["body"])
    extra = {"user": director_row()} if module is reports else {}
    module.update(int(item_id), "Landed in between", row["slug"], row["body"], **extra)
    with pytest.raises(StaleItem):
        module.update(int(item_id), "Stale", "stale", "Stale.", base=base, **extra)
    assert stored(module, item_id)["title"] == "Landed in between"


def director_row():
    return next(user for user in users.list_users() if user["role"] == "admin")
