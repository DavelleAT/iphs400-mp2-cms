"""T20: Homepage settings (issue #24, spec #22).

The Director edits the homepage's headline, its accent, its intro, and up to
four Key figures at /admin/homepage. They are settings, not content: no
Draft, and they reach the site at the next `cms publish`.
"""
from __future__ import annotations

import re

import pytest
from markupsafe import escape

from app import homepage
from tests.conftest import post_form

SETTINGS = {"headline": "Kenyon, by the numbers,", "headline_accent": "checked twice.",
            "intro": "Enrollment and outcomes from the census.",
            "figure_value_1": "1,805", "figure_label_1": "Students enrolled",
            "figure_note_1": "Fall 2026 census",
            "figure_value_2": "10:1", "figure_label_2": "Student–faculty ratio",
            "figure_note_2": ""}


def saved(director, **override):
    return post_form(director, "/admin/homepage", {**SETTINGS, **override})


# Who may edit it

def test_a_fresh_site_has_the_sample_homepage():
    settings = homepage.get()
    assert settings.headline and settings.intro
    assert len(settings.key_figures) == 4
    assert all(figure.value and figure.label for figure in settings.key_figures)


def test_the_director_sees_the_homepage_settings_and_a_link_to_them(client_as):
    director = client_as("admin")
    assert 'href="/admin/homepage"' in director.get("/admin").text
    page = director.get("/admin/homepage")
    assert page.status_code == 200
    assert 'name="csrf_token"' in page.text
    assert f'value="{escape(homepage.get().headline)}"' in page.text
    # Four rows of Key figure fields, filled from the settings.
    assert len(re.findall(r'name="figure_value_\d"', page.text)) == homepage.FIGURES_MAX


def test_an_analyst_gets_403_and_no_link(client_as):
    analyst = client_as("editor")
    assert 'href="/admin/homepage"' not in analyst.get("/admin").text
    assert analyst.get("/admin/homepage").status_code == 403
    before = homepage.get()
    assert saved(analyst).status_code == 403
    assert homepage.get() == before


def test_a_save_without_its_csrf_token_is_refused(client_as):
    director = client_as("admin")
    before = homepage.get()
    response = post_form(director, "/admin/homepage", SETTINGS, with_csrf=False)
    assert response.status_code == 403
    assert homepage.get() == before


def test_signed_out_is_sent_to_login(client):
    response = client.get("/admin/homepage", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"


# Saving

def test_the_director_saves_the_homepage(client_as):
    director = client_as("admin")
    response = saved(director, headline="  Kenyon, by the numbers,  ")
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/homepage"
    assert "Homepage saved." in director.get("/admin/homepage").text

    settings = homepage.get()
    assert settings.headline == "Kenyon, by the numbers,"
    assert settings.headline_accent == "checked twice."
    assert [(f.value, f.label, f.note) for f in settings.key_figures] == [
        ("1,805", "Students enrolled", "Fall 2026 census"),
        ("10:1", "Student–faculty ratio", "")]


def test_blank_key_figure_rows_are_dropped_and_the_rest_close_up(client_as):
    director = client_as("admin")
    response = saved(director, figure_value_1="", figure_label_1="", figure_note_1="",
                     figure_value_3="87%", figure_label_3="Six-year graduation")
    assert response.status_code == 303
    assert [f.value for f in homepage.get().key_figures] == ["10:1", "87%"]


def test_the_homepage_may_have_no_key_figures(client_as):
    director = client_as("admin")
    blank = {f"figure_{part}_{n}": "" for part in ("value", "label", "note") for n in (1, 2)}
    assert saved(director, **blank).status_code == 303
    assert homepage.get().key_figures == ()


@pytest.mark.parametrize("override, field", [
    ({"headline": "   "}, "headline"),
    ({"headline": "x" * (homepage.LIMITS["headline"] + 1)}, "headline"),
    ({"headline_accent": "x" * (homepage.LIMITS["headline_accent"] + 1)}, "headline_accent"),
    ({"intro": "x" * (homepage.LIMITS["intro"] + 1)}, "intro"),
    ({"figure_value_2": "x" * (homepage.LIMITS["value"] + 1)}, "figure_value_2"),
    ({"figure_label_1": "x" * (homepage.LIMITS["label"] + 1)}, "figure_label_1"),
    ({"figure_note_1": "x" * (homepage.LIMITS["note"] + 1)}, "figure_note_1"),
    # Half a Key figure: a number with nothing to say what it counts.
    ({"figure_label_2": ""}, "figure_label_2"),
    ({"figure_value_2": ""}, "figure_value_2"),
])
def test_a_field_over_its_limit_or_missing_is_refused_by_the_field(client_as, override, field):
    director = client_as("admin")
    before = homepage.get()
    response = saved(director, **override)
    assert response.status_code == 400
    assert homepage.get() == before
    # The message sits by its field, and what was typed is kept.
    assert re.search(rf'name="{field}"[^>]*aria-invalid="true"[^>]*aria-describedby="{field}-error"',
                     response.text), field
    assert f'id="{field}-error"' in response.text
    assert 'value="Kenyon, by the numbers,"' in response.text or field == "headline"


def test_settings_are_plain_text_and_escaped_on_the_form(client_as):
    director = client_as("admin")
    assert saved(director, headline='<b>Bold</b> "claims"').status_code == 303
    assert homepage.get().headline == '<b>Bold</b> "claims"'
    page = director.get("/admin/homepage").text
    assert "<b>Bold</b>" not in page and "&lt;b&gt;Bold&lt;/b&gt;" in page
