"""T20: Site search (issue #24, spec #22).

Static: `cms publish` writes search-index.json (published items only) and
search.html, and search.js searches the index in the browser. Without
JavaScript, search.html lists every published item. The app serves all
three, so search works in local preview too.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from app import public_site, settings
from app.publish import render_site
from tests.conftest import post_form
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import create_report
from tests.test_t07_public_site import published_bite, published_report
from tests.test_t08_publish import exported
from tests.test_t19_look_and_feel import PUBLIC_PAGES

DRAFT_TITLE = "Unreleased census count"


def a_searchable_site(director) -> None:
    published_bite(director, summary="Headcount by class on the census date.")
    published_report(director, summary="Admissions, enrollment, and programs.")
    create_bite(director, slug="unreleased", title=DRAFT_TITLE, summary="Not yet final.")
    create_report(director, slug="cds", title="Draft CDS", summary="Draft summary words.")


# The index

def test_the_index_holds_published_items_only(client_as, client):
    a_searchable_site(client_as("admin"))
    response = client.get("/search-index.json")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["x-content-type-options"] == "nosniff"
    index = response.json()
    assert index == [
        {"kind": "Report", "title": "Factbook 2026", "summary": "Admissions, enrollment, and programs.",
         "date": index[0]["date"], "path": "reports/factbook.html"},
        {"kind": "Data Bite", "title": BITE["title"],
         "summary": "Headcount by class on the census date.",
         "date": index[1]["date"], "path": "data-bites/fall-enrollment.html"}]
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\d", item["date"]) for item in index)
    for draft_word in (DRAFT_TITLE, "Not yet final", "Draft CDS", "Draft summary"):
        assert draft_word not in response.text


def test_every_path_in_the_index_is_a_page_of_the_site(client_as, client):
    a_searchable_site(client_as("admin"))
    for item in client.get("/search-index.json").json():
        assert not item["path"].startswith("/")
        assert client.get("/" + item["path"]).status_code == 200


def test_unpublishing_takes_an_item_out_of_the_index(client_as, client):
    director = client_as("admin")
    bite = published_bite(director)
    assert post_form(director, f"/admin/data-bites/{bite}/unpublish", {}).status_code == 303
    assert client.get("/search-index.json").json() == []


# search.html

def test_search_html_lists_every_published_item_without_javascript(client_as, client):
    a_searchable_site(client_as("admin"))
    page = client.get("/search.html").text
    results = re.findall(r'<li><a href="([^"]+)">([^<]+)</a>', page)
    assert results == [("reports/factbook.html", "Factbook 2026"),
                       ("data-bites/fall-enrollment.html", BITE["title"])]
    assert "Headcount by class on the census date." in page
    assert DRAFT_TITLE not in page and "Draft CDS" not in page
    assert '<script src="search.js" defer></script>' in page


def test_search_html_with_nothing_published(client):
    page = client.get("/search.html")
    assert page.status_code == 200 and "Nothing is published yet." in page.text


def test_the_script_is_served_as_javascript(client):
    response = client.get("/search.js")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.text == (settings.STATIC / "search.js").read_text()


def test_publish_writes_the_index_the_page_and_the_script(client_as, tmp_path):
    director = client_as("admin")
    a_searchable_site(director)
    site = exported(render_site(tmp_path / "site"))
    assert json.loads(site["search-index.json"]) == public_site.search_index()
    assert site["search.js"] == (settings.STATIC / "search.js").read_bytes()
    for name in ("search-index.json", "search.html"):
        text = site[name].decode()
        assert DRAFT_TITLE not in text and "Draft CDS" not in text, name
        assert "Factbook 2026" in text, name


# The header form

@pytest.mark.parametrize("path", PUBLIC_PAGES + ["/search.html"])
def test_every_page_has_the_search_form(client_as, client, path):
    a_searchable_site(client_as("admin"))
    page = client.get(path).text
    root = "../" * path.removeprefix("/").count("/")
    form = re.search(r'<form class="search-site" role="search" action="([^"]+)" method="get">(.*?)</form>',
                     page, re.S)
    assert form, path
    assert form.group(1) == f"{root}search.html"
    assert re.search(r'<label [^>]*for="search-site-q"', form.group(2))
    assert re.search(r'<input [^>]*id="search-site-q"[^>]*name="q"', form.group(2))


# search.js's matching, run in Node where there is one (no dependency).

INDEX = [
    {"kind": "Report", "title": "Factbook", "summary": "Retention and enrollment, each term.",
     "date": "2026-09-29", "path": "reports/factbook.html"},
    {"kind": "Data Bite", "title": "First-year retention holds", "summary": "The class returned.",
     "date": "2026-09-12", "path": "data-bites/retention.html"},
    {"kind": "Data Bite", "title": "Résumé workshop survey", "summary": "Career office results.",
     "date": "2026-08-01", "path": "data-bites/resume.html"},
]


def search(query: str) -> list[str]:
    script = (f"const {{searchItems}} = require({json.dumps(str(settings.STATIC / 'search.js'))});"
              f"console.log(JSON.stringify(searchItems({json.dumps(INDEX)}, {json.dumps(query)})"
              ".map(item => item.title)));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node isn't installed")
@pytest.mark.parametrize("query, titles", [
    # A title match ranks above a match in a summary alone.
    ("retention", ["First-year retention holds", "Factbook"]),
    ("RETENTION", ["First-year retention holds", "Factbook"]),
    # Accents are ignored both ways.
    ("resume", ["Résumé workshop survey"]),
    ("Résumé", ["Résumé workshop survey"]),
    # In a summary only.
    ("career", ["Résumé workshop survey"]),
    # Every word must match, in the title or the summary.
    ("factbook enrollment", ["Factbook"]),
    ("factbook career", []),
    ("no such thing", []),
    ("   ", []),
])
def test_search_js_matches_and_ranks(query, titles):
    assert search(query) == titles
