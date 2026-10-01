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


# The home page

from tests.test_t03_data_bites import BITE  # noqa: E402
from tests.test_t07_public_site import published_bite, published_report  # noqa: E402
from tests.test_t16_charts import fence, source  # noqa: E402
from tests.conftest import backdate  # noqa: E402

CHART_BODY = ("Headcount by class.\n\n" + fence(source(title="Headcount by class"))
              + "\nMore prose.\n\n" + fence(source(title="A second chart")))


def section(page: str, heading: str) -> str:
    """A home section's HTML, from its heading to the next section."""
    start = page.index(f">{heading}</h2>")
    end = page.find('<section class="section-home"', start)
    return page[start:end if end != -1 else len(page)]


def test_the_home_page_shows_the_homepage_settings(client_as, client):
    director = client_as("admin")
    assert saved(director).status_code == 303
    page = client.get("/").text
    assert re.search(r'<h1 id="intro-home-title">Kenyon, by the numbers,\s*'
                     r'<span class="intro-home-accent">checked twice\.</span></h1>', page)
    assert '<p class="intro-home-lede">Enrollment and outcomes from the census.</p>' in page
    figures = re.findall(r"<div><dt>([^<]+)(?:<small>([^<]*)</small>)?</dt><dd>([^<]+)</dd></div>", page)
    assert figures == [("Students enrolled", "Fall 2026 census", "1,805"),
                       ("Student–faculty ratio", "", "10:1")]
    # Its intro is the page's description too.
    assert '<meta name="description" content="Enrollment and outcomes from the census.">' in page


def test_the_home_page_escapes_the_settings(client_as, client):
    director = client_as("admin")
    assert saved(director, headline="<i>Numbers</i>", figure_value_1="<b>1</b>").status_code == 303
    page = client.get("/").text
    assert "<i>Numbers</i>" not in page and "&lt;i&gt;Numbers&lt;/i&gt;" in page
    assert "<b>1</b>" not in page and "&lt;b&gt;1&lt;/b&gt;" in page


def test_no_key_figures_leaves_out_their_list(client_as, client):
    director = client_as("admin")
    blank = {f"figure_{part}_{n}": "" for part in ("value", "label", "note") for n in (1, 2)}
    assert saved(director, **blank).status_code == 303
    assert "figures-home" not in client.get("/").text


def test_the_home_sections_are_latest_reports_then_data_bites(client_as, client):
    director = client_as("admin")
    older = published_bite(director, slug="older", title="Older bite", summary="An older one.")
    backdate("data_bites", older)
    published_bite(director, summary="The newest one.")
    published_report(director, summary="What the Factbook covers.")
    page = client.get("/").text
    numbers = re.findall(r'<div class="section-head"><span class="text-mono">(\d\d)</span><h2 [^>]*>([^<]+)</h2>', page)
    assert numbers == [("01", "Latest"), ("02", "Reports"), ("03", "Data Bites")]

    latest = section(page, "Latest")
    assert BITE["title"] in latest and "The newest one." in latest
    assert 'href="data-bites/fall-enrollment.html"' in latest
    # The rest of the Data Bites, without the one featured above them.
    rest = section(page, "Data Bites")
    assert "Older bite" in rest and BITE["title"] not in rest
    assert "What the Factbook covers." in section(page, "Reports")


def test_the_latest_data_bite_shows_its_first_chart(client_as, client):
    published_bite(client_as("editor"), body=CHART_BODY, summary="With a chart.")
    latest = section(client.get("/").text, "Latest")
    assert latest.count('<figure class="chart-figure"') == 1
    assert "Headcount by class</figcaption>" in latest
    assert "A second chart" not in latest and "More prose." not in latest
    # The same Chart the Data Bite's page draws.
    page = client.get("/data-bites/fall-enrollment.html").text
    assert 'class="chart-svg"' in latest and "Headcount by class</figcaption>" in page


def test_the_latest_data_bite_without_a_chart_shows_its_title_summary_and_link(client_as, client):
    published_bite(client_as("editor"), summary="No chart here.")
    latest = section(client.get("/").text, "Latest")
    assert "chart-figure" not in latest and "No chart here." in latest
    assert BITE["title"] in latest and "Read the Data Bite" in latest
    # Its body isn't shown here, only its first Chart would be.
    assert "1,745" not in latest


def test_a_chart_inside_a_quote_is_not_cut_out_for_the_home_page(client_as, client):
    quoted = "> " + fence(source(title="Quoted chart")).replace("\n", "\n> ").rstrip("> ")
    published_bite(client_as("editor"), body="Intro.\n\n" + quoted)
    assert "chart-figure" not in section(client.get("/").text, "Latest")


def test_with_nothing_published_the_home_page_says_so(client):
    page = client.get("/").text
    assert "Nothing published yet." in page
    assert "No Reports published yet." in page
