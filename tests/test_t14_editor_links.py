"""T14: site links in the Editor (issue #17): what the edit and create pages
give its link dialog's picker and markers, and what an Editor save keeps."""
from __future__ import annotations

import json
import re
from html import unescape

import pytest
from fastapi.testclient import TestClient

from app import data_bites, reports
from tests.conftest import post_form
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import REPORT, create_report
from tests.test_t07_public_site import published_bite, published_report
from tests.test_t13_editor_routes import KINDS, edit_page, editor_content, save
from tests.test_t14_links import bite_link, report_link


def data(page: str, name: str):
    """The Editor wrapper's `data-<name>` JSON."""
    [value] = re.findall(rf"<div class=\"admin-editor\"[^>]*\bdata-{name}='([^']*)'", page)
    return json.loads(unescape(value))


@pytest.fixture
def director(client_as):
    return client_as("admin")


def a_site(director: TestClient) -> dict[str, str]:
    """A published and a draft Report and Data Bite, by name."""
    return {"published report": published_report(director, slug="cds", title="Common Data Set"),
            "draft report": create_report(director, slug="draft-cds", title="Draft CDS"),
            "published bite": published_bite(director, slug="spring", title="Spring survey"),
            "draft bite": create_bite(director, slug="unreleased", title="Unreleased count")}


# The create forms are on their own pages since T22.
@pytest.mark.parametrize("path", ["/admin/data-bites/new", "/admin/reports/new",
                                  "/admin/data-bites/{bite}", "/admin/reports/{report}"])
def test_the_picker_lists_every_report_and_data_bite_marking_drafts(director, path):
    site = a_site(director)
    page = director.get(path.format(bite=site["draft bite"],
                                    report=site["draft report"])).text
    assert data(page, "site-items") == [
        {"href": report_link(site["published report"]), "title": "Common Data Set",
         "kind": "Report", "draft": False},
        {"href": report_link(site["draft report"]), "title": "Draft CDS",
         "kind": "Report", "draft": True},
        {"href": bite_link(site["published bite"]), "title": "Spring survey",
         "kind": "Data Bite", "draft": False},
        {"href": bite_link(site["draft bite"]), "title": "Unreleased count",
         "kind": "Data Bite", "draft": True},
    ]


def test_the_picker_escapes_titles(director):
    create_report(director, slug="x", title="</div><script>alert(1)</script> 'q'")
    page = director.get("/admin/reports/new").text
    assert "<script>alert(1)" not in page
    assert data(page, "site-items")[0]["title"] == "</div><script>alert(1)</script> 'q'"


def test_the_edit_page_names_each_unresolvable_links_state(director):
    site = a_site(director)
    doomed = create_report(director, slug="doomed", title="Doomed")
    deleted = report_link(doomed)
    assert post_form(director, f"/admin/reports/{doomed}/delete", {}).status_code == 303
    unknown = "data-bite:" + "e" * 32
    body = " ".join(f"[{n}]({link})" for n, link in enumerate([
        report_link(site["published report"]), report_link(site["draft report"]),
        deleted, unknown]))
    bid = create_bite(director, slug="linking", body=body)

    page = edit_page(director, "data-bites", bid)
    assert data(page, "link-states") == {report_link(site["draft report"]): "draft",
                                         deleted: "deleted", unknown: "unknown"}
    # Each is a link in the Editor, where the writer can see and fix it.
    content = editor_content(page)
    for link in (report_link(site["published report"]), deleted, unknown):
        assert f'href="{link}"' in content
    assert "admin-editor-locked" not in content


@pytest.mark.parametrize("kind, item, create, module", KINDS)
def test_an_editor_save_keeps_a_site_link(director, kind, item, create, module):
    rid = create_report(director, slug="cds", title="Common Data Set")
    item_id = create(director, slug="linking")
    page = edit_page(director, kind, item_id)
    html = f'<p>See <a href="{report_link(rid)}">the CDS</a>.</p>'
    assert save(director, kind, item_id, page, body_html=html,
                body_dirty="1").status_code == 303
    assert module.get(int(item_id))["body"] == f"See [the CDS]({report_link(rid)}).\n"


@pytest.mark.parametrize("href", ["http://example.test", "/reports/cds.html",
                                  "reports/cds.html", "report:not-a-ref",
                                  "report:" + "A" * 32])
def test_an_editor_save_drops_any_other_link(director, href):
    bid = create_bite(director, slug="linking")
    page = edit_page(director, "data-bites", bid)
    assert save(director, "data-bites", bid, page, body_html=f'<p><a href="{href}">x</a></p>',
                body_dirty="1").status_code == 303
    assert data_bites.get(int(bid))["body"] == "x\n"


# Deleting an item says what links to it.

DELETE_KINDS = [pytest.param("data-bites", create_bite, bite_link, id="data-bite"),
                pytest.param("reports", create_report, report_link, id="report")]


def delete_page(c: TestClient, kind: str, item_id: str):
    return c.get(f"/admin/{kind}/{item_id}/delete")


@pytest.mark.parametrize("kind, create, link", DELETE_KINDS)
def test_deleting_lists_the_items_that_link_to_it_and_still_deletes(
        director, client, kind, create, link):
    target = create(director, slug="target", title="The target")
    reference = link(target)
    create_bite(director, slug="a", title="Links from a Data Bite", body=f"[x]({reference})")
    create_report(director, slug="b", title="Links from a Report", body=f"[y]({reference})")
    create_bite(director, slug="c", title="Links elsewhere", body="[z](https://example.test)")

    page = delete_page(director, kind, target)
    assert page.status_code == 200
    assert "The target" in page.text
    assert "Links from a Data Bite" in page.text and "Links from a Report" in page.text
    assert "Links elsewhere" not in page.text
    assert f'action="/admin/{kind}/{target}/delete"' in page.text

    assert post_form(director, f"/admin/{kind}/{target}/delete", {}).status_code == 303
    assert (data_bites if kind == "data-bites" else reports).get(int(target)) is None
    assert {row["slug"] for row in data_bites.list_all()} == {"a", "c"}


@pytest.mark.parametrize("kind, create, link", DELETE_KINDS)
def test_deleting_an_item_nothing_links_to_says_so(director, kind, create, link):
    target = create(director, slug="target")
    page = delete_page(director, kind, target).text
    assert "No other Report or Data Bite links to it." in page


@pytest.mark.parametrize("kind, create, link", DELETE_KINDS)
def test_the_list_pages_delete_opens_the_confirmation(director, kind, create, link):
    target = create(director, slug="target")
    assert f'href="/admin/{kind}/{target}/delete"' in director.get(f"/admin/{kind}").text


@pytest.mark.parametrize("kind, create, link", DELETE_KINDS)
def test_only_the_director_sees_the_confirmation(client_as, client, kind, create, link):
    target = create(client_as("admin"), slug="target")
    assert delete_page(client_as("editor"), kind, target).status_code == 403
    anonymous = client.get(f"/admin/{kind}/{target}/delete", follow_redirects=False)
    assert anonymous.status_code in (302, 303) and "/login" in anonymous.headers["location"]
    assert delete_page(client_as("admin"), kind, "999").status_code == 404
