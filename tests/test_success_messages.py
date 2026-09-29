"""Confirmations: every successful state-changing admin action says so on the
page it redirects to, once, in a role="status" message."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.publish import render_site
from tests.conftest import DEMO_USERS, post_form, user_id
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import REPORT, create_report, report_id
from tests.test_t05_report_files import pdf, post_with_file
from tests.test_t08_publish import exported
from tests.test_t10_chart_images import delete_image, png, upload

LIVE_NOTE = " The public site updates at the next cms publish."


def confirmations(html: str) -> list[str]:
    return re.findall(r'<p class="admin-confirmation" role="status">([^<]*)</p>', html)


def assert_confirmed(c: TestClient, response, message: str) -> None:
    """The action redirected, the page it redirected to shows `message` once,
    and reloading that page shows nothing: the message is spent."""
    assert response.status_code == 303, response.text
    page = response.headers["location"]
    assert confirmations(c.get(page).text) == [message]
    assert confirmations(c.get(page).text) == []


# --- Data Bites -------------------------------------------------------------

def test_creating_a_data_bite_is_confirmed(client_as):
    analyst = client_as("editor")
    response = post_form(analyst, "/admin/data-bites", BITE)
    assert_confirmed(analyst, response, "Data Bite created as a Draft.")


def test_saving_a_data_bite_is_confirmed(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    response = post_form(analyst, f"/admin/data-bites/{bid}", {**BITE, "title": "New title"})
    assert_confirmed(analyst, response, "Data Bite saved.")


def test_publishing_and_unpublishing_a_data_bite_are_confirmed(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    response = post_form(analyst, f"/admin/data-bites/{bid}/publish", {})
    assert_confirmed(analyst, response, "Data Bite published." + LIVE_NOTE)
    response = post_form(analyst, f"/admin/data-bites/{bid}/unpublish", {})
    assert_confirmed(analyst, response, "Data Bite moved back to Draft." + LIVE_NOTE)


def test_deleting_a_data_bite_is_confirmed(client_as):
    director = client_as("admin")
    bid = create_bite(director)
    response = post_form(director, f"/admin/data-bites/{bid}/delete", {})
    assert_confirmed(director, response, "Data Bite deleted.")


def test_uploading_and_deleting_a_data_bite_chart_image_are_confirmed(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    assert_confirmed(analyst, upload(analyst, bid, png()), "Chart image uploaded.")
    response = delete_image(analyst, bid, "fall-by-class.png")
    assert_confirmed(analyst, response, "Chart image deleted.")


# --- Reports ----------------------------------------------------------------

def test_creating_a_report_is_confirmed(client_as):
    analyst = client_as("editor")
    response = post_with_file(analyst, "/admin/reports", REPORT)
    assert_confirmed(analyst, response, "Report created as a Draft.")


def test_creating_a_report_with_a_pdf_is_confirmed(client_as):
    analyst = client_as("editor")
    response = post_with_file(analyst, "/admin/reports", REPORT, pdf())
    assert_confirmed(analyst, response, "Report created as a Draft, with its attached file.")


def test_saving_a_report_is_confirmed_with_or_without_a_new_pdf(client_as):
    analyst = client_as("editor")
    rid = create_report(analyst)
    response = post_with_file(analyst, f"/admin/reports/{rid}", REPORT)
    assert_confirmed(analyst, response, "Report saved.")
    response = post_with_file(analyst, f"/admin/reports/{rid}", REPORT, pdf())
    assert_confirmed(analyst, response, "Report saved, with its new attached file.")


def test_removing_a_reports_pdf_is_confirmed(client_as):
    analyst = client_as("editor")
    assert post_with_file(analyst, "/admin/reports", REPORT, pdf()).status_code == 303
    rid = report_id(analyst, REPORT["slug"])
    response = post_form(analyst, f"/admin/reports/{rid}/file/delete", {})
    assert_confirmed(analyst, response, "Attached file removed.")


def test_publishing_unpublishing_and_deleting_a_report_are_confirmed(client_as):
    director = client_as("admin")
    rid = create_report(director)
    response = post_form(director, f"/admin/reports/{rid}/publish", {})
    assert_confirmed(director, response, "Report published." + LIVE_NOTE)
    response = post_form(director, f"/admin/reports/{rid}/unpublish", {})
    assert_confirmed(director, response, "Report moved back to Draft." + LIVE_NOTE)
    response = post_form(director, f"/admin/reports/{rid}/delete", {})
    assert_confirmed(director, response, "Report deleted.")


def test_uploading_and_deleting_a_report_chart_image_are_confirmed(client_as):
    analyst = client_as("editor")
    rid = create_report(analyst)
    response = post_with_file(analyst, f"/admin/reports/{rid}/images", {}, png())
    assert_confirmed(analyst, response, "Chart image uploaded.")
    response = post_form(analyst, f"/admin/reports/{rid}/images/fall-by-class.png/delete", {})
    assert_confirmed(analyst, response, "Chart image deleted.")


# --- Users ------------------------------------------------------------------

NEW_USER = {"name": "Riley Intern", "email": "riley@example.test",
            "password": "a-long-enough-password", "role": "editor"}


def test_creating_a_user_is_confirmed_without_their_email_or_password(client_as):
    director = client_as("admin")
    response = post_form(director, "/admin/users", NEW_USER)
    assert_confirmed(director, response, "User created.")


def test_changing_a_role_and_deactivating_are_confirmed(client_as):
    director = client_as("admin")
    analyst = user_id(director, DEMO_USERS["editor"]["email"])
    response = post_form(director, f"/admin/users/{analyst}/role", {"role": "admin"})
    assert_confirmed(director, response, "Role changed.")
    response = post_form(director, f"/admin/users/{analyst}/deactivate", {})
    assert_confirmed(director, response, "User deactivated.")


# --- Only success is confirmed ----------------------------------------------

def test_a_rejected_form_is_not_confirmed(client_as):
    analyst = client_as("editor")
    response = post_form(analyst, "/admin/data-bites", {**BITE, "title": ""})
    assert response.status_code == 400
    assert confirmations(response.text) == []
    assert confirmations(analyst.get("/admin/data-bites").text) == []


def test_a_post_without_its_csrf_token_is_refused_and_not_confirmed(client_as):
    analyst = client_as("editor")
    response = post_form(analyst, "/admin/data-bites", BITE, with_csrf=False)
    assert response.status_code == 403
    assert confirmations(analyst.get("/admin/data-bites").text) == []


@pytest.mark.parametrize("path", ["/admin/data-bites/{id}/delete", "/admin/reports/{id}/publish"])
def test_an_analyst_refused_a_director_action_is_not_confirmed(client_as, path):
    analyst = client_as("editor")
    item = create_bite(analyst) if "data-bites" in path else create_report(analyst)
    response = post_form(analyst, path.format(id=item), {})
    assert response.status_code == 403
    assert confirmations(analyst.get("/admin").text) == []


def test_confirmations_never_reach_the_public_site(client_as, client, tmp_path):
    director = client_as("admin")
    bid = create_bite(director)
    assert post_form(director, f"/admin/data-bites/{bid}/publish", {}).status_code == 303
    # The message is still waiting: the public preview neither shows nor spends it.
    assert confirmations(director.get("/").text) == []
    assert confirmations(director.get("/admin/data-bites").text) != []

    out = render_site(tmp_path / "site")
    pages = {name: html for name, html in exported(out).items() if name.endswith(".html")}
    assert pages
    for name, html in pages.items():
        assert confirmations(html.decode()) == [], name
