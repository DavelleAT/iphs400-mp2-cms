"""T03: Data Bites (issue #4)."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from tests.conftest import backdate, post_form, second_analyst, stored_id

BITE = {"title": "Fall enrollment snapshot", "slug": "fall-enrollment",
        "body": "Enrollment is **1,745** this fall."}


def bite_row(c: TestClient, slug: str) -> str:
    """This Data Bite's row of the admin list, as HTML."""
    item_id = stored_id("data_bites", slug)
    for row in c.get("/admin/data-bites").text.split("<tr")[1:]:
        if row.startswith(f' id="data-bite-{item_id}"'):
            return row
    raise AssertionError(f"{slug} is not listed")


def bite_id(c: TestClient, slug: str) -> str:
    return re.match(r' id="data-bite-(\d+)"', bite_row(c, slug)).group(1)


def create_bite(c: TestClient, **override) -> str:
    response = post_form(c, "/admin/data-bites", {**BITE, **override})
    assert response.status_code == 303, response.text
    # A create lands on the new item's edit page (T22).
    return response.headers["location"].removeprefix("/admin/data-bites/")


def test_analyst_creates_a_data_bite_as_a_draft(client_as):
    analyst = client_as("editor")
    response = post_form(analyst, "/admin/data-bites", BITE)
    assert response.status_code == 303
    # To the new Data Bite's edit page since T22 (spec #25), not the list.
    assert response.headers["location"] == f"/admin/data-bites/{stored_id('data_bites', BITE['slug'])}"

    row = bite_row(analyst, BITE["slug"])
    assert BITE["title"] in row and "Draft" in row


def test_analyst_publishes_and_unpublishes_a_data_bite(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)

    response = post_form(analyst, f"/admin/data-bites/{bid}/publish", {})
    assert response.status_code == 303
    assert "Published" in bite_row(analyst, BITE["slug"])

    response = post_form(analyst, f"/admin/data-bites/{bid}/unpublish", {})
    assert response.status_code == 303
    assert "Draft" in bite_row(analyst, BITE["slug"])


def test_analyst_cannot_delete_a_data_bite(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    response = post_form(analyst, f"/admin/data-bites/{bid}/delete", {})
    assert response.status_code == 403
    assert BITE["title"] in bite_row(analyst, BITE["slug"])
    # And the UI doesn't offer it.
    assert "/delete" not in analyst.get("/admin/data-bites").text


def test_director_deletes_a_data_bite(client_as):
    analyst, director = client_as("editor"), client_as("admin")
    bid = create_bite(analyst)
    response = post_form(director, f"/admin/data-bites/{bid}/delete", {})
    assert response.status_code == 303
    assert f'id="data-bite-{bid}"' not in director.get("/admin/data-bites").text
    assert post_form(director, f"/admin/data-bites/{bid}/delete", {}).status_code == 404


def test_duplicate_slug_is_rejected_with_a_validation_error(client_as):
    analyst = client_as("editor")
    create_bite(analyst)
    response = post_form(analyst, "/admin/data-bites",
                         {**BITE, "title": "A different title"})
    assert response.status_code == 400
    assert f"already uses the slug {BITE['slug']}" in response.text
    assert "A different title" not in bite_row(analyst, BITE["slug"])
    assert analyst.get("/admin/data-bites").text.count('id="data-bite-') == 1


def test_any_analyst_edits_any_data_bite_and_author_and_created_at_are_kept(client_as):
    riley = second_analyst(client_as("admin"))
    bid = create_bite(riley)
    backdate("data_bites", bid)

    analyst = client_as("editor")  # a different Analyst from the author
    edit_page = analyst.get(f"/admin/data-bites/{bid}")
    assert edit_page.status_code == 200 and BITE["body"] in edit_page.text

    edited = {"title": "Fall enrollment (official)", "slug": "fall-enrollment-official",
              "body": "Official count: **1,751**."}
    response = post_form(analyst, f"/admin/data-bites/{bid}", edited)
    assert response.status_code == 303

    page = analyst.get(f"/admin/data-bites/{bid}").text
    assert edited["title"] in page and edited["body"] in page
    assert "Created 2026-01-05 09:00:00 by Riley Intern" in page
    updated = re.search(r"Last updated ([\d:\- ]+)", page).group(1)
    assert updated != "2026-01-05 09:00:00"
    assert "Riley Intern" in bite_row(analyst, edited["slug"])


def test_editing_to_another_data_bites_slug_is_rejected(client_as):
    analyst = client_as("editor")
    create_bite(analyst)
    other = create_bite(analyst, slug="spring-survey", title="Spring survey")
    response = post_form(analyst, f"/admin/data-bites/{other}",
                         {**BITE, "slug": BITE["slug"], "title": "Spring survey"})
    assert response.status_code == 400
    assert f"already uses the slug {BITE['slug']}" in response.text
    assert bite_id(analyst, "spring-survey") == other


def test_a_draft_data_bite_is_never_shown_publicly(client_as, client):
    analyst = client_as("editor")
    published = create_bite(analyst, slug="published-bite", title="Published bite")
    post_form(analyst, f"/admin/data-bites/{published}/publish", {})
    create_bite(analyst, slug="draft-bite", title="Unreleased draft")

    home = client.get("/").text
    assert "Published bite" in home
    assert "Unreleased draft" not in home and "draft-bite" not in home

    post_form(analyst, f"/admin/data-bites/{published}/unpublish", {})
    assert "Published bite" not in client.get("/").text


# Every Data Bite route. {id} is filled with an existing Data Bite's id.
ROUTES = [
    ("GET", "/admin/data-bites", {}),
    ("POST", "/admin/data-bites", {**BITE, "slug": "new-slug"}),
    ("GET", "/admin/data-bites/{id}", {}),
    ("POST", "/admin/data-bites/{id}", {**BITE, "title": "Changed title"}),
    ("POST", "/admin/data-bites/{id}/publish", {}),
    ("POST", "/admin/data-bites/{id}/unpublish", {}),
    ("POST", "/admin/data-bites/{id}/delete", {}),
]
POST_ROUTES = [r for r in ROUTES if r[0] == "POST"]


@pytest.fixture
def existing_bite(client_as):
    return create_bite(client_as("editor"))


def assert_unchanged(c: TestClient):
    """The Data Bite from `existing_bite` is still the only one, still a draft,
    with its original title."""
    listing = c.get("/admin/data-bites").text
    assert listing.count('id="data-bite-') == 1
    row = bite_row(c, BITE["slug"])
    assert BITE["title"] in row and "Draft" in row


@pytest.mark.parametrize("method, path, data", ROUTES)
def test_anonymous_visitor_is_redirected_from_every_data_bite_route(
        client, client_as, existing_bite, method, path, data):
    response = client.request(method, path.format(id=existing_bite),
                              data=data or None, follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].endswith("/login")
    assert_unchanged(client_as("admin"))


@pytest.mark.parametrize("method, path, data", POST_ROUTES)
def test_data_bite_posts_without_csrf_token_are_rejected(
        client_as, existing_bite, method, path, data):
    director = client_as("admin")
    director.get("/admin")  # the session has a token; the POST just omits it
    response = post_form(director, path.format(id=existing_bite), data, with_csrf=False)
    assert response.status_code == 403
    assert_unchanged(director)


def test_every_signed_in_user_sees_the_data_bites_link(client_as):
    for role in ("admin", "editor"):
        assert 'href="/admin/data-bites"' in client_as(role).get("/admin").text


def test_missing_data_bite_is_404(client_as):
    analyst = client_as("editor")
    assert analyst.get("/admin/data-bites/999").status_code == 404
    assert post_form(analyst, "/admin/data-bites/999/publish", {}).status_code == 404
    assert post_form(analyst, "/admin/data-bites/999", BITE).status_code == 404
