"""T24: Dashboard (issue #29, spec #25).

The Console's home page shows each person what needs their attention: four
counts, each linking to its filtered list; "Waiting for you", draft Reports
for the Director and an Analyst's own drafts; the 8 most recently changed
items; and side panels for the public site and, for the Director, the
Homepage settings. All of it is derived from what is stored.
"""
from __future__ import annotations

import re
from datetime import date

from fastapi.testclient import TestClient

from app import db
from app.publish import render_site
from tests.conftest import post_form, second_analyst
from tests.test_t22_lists import create


def section(page: str, title_id: str) -> str:
    match = re.search(rf'<section class="section-console" aria-labelledby="{title_id}">(.*?)</section>',
                      page, re.S)
    assert match, f"no section #{title_id}"
    return match.group(1)


def listed(page: str, title_id: str, list_key: str) -> list[str]:
    """A section's items, top to bottom, as "<type key>-<id>"."""
    return re.findall(rf'<li id="{list_key}-([a-z-]+-\d+)"', section(page, title_id))


def waiting(c: TestClient) -> list[str]:
    return listed(c.get("/admin").text, "waiting-title", "waiting")


def recent(c: TestClient) -> list[str]:
    return listed(c.get("/admin").text, "recent-title", "recent")


def item(page: str, list_key: str, key: str) -> str:
    match = re.search(rf'<li id="{list_key}-{key}">(.*?)</li>', page, re.S)
    assert match, f"{list_key}-{key} is not listed"
    return match.group(1)


def set_updated(table: str, item_id: str, stamp: str) -> None:
    """Setup only: when an item was last updated."""
    with db.connect() as conn:
        conn.execute(f"UPDATE {table} SET updated_at = ? WHERE id = ?", (stamp, item_id))


def publish(c: TestClient, kind: str, item_id: str) -> None:
    assert post_form(c, f"/admin/{kind}/{item_id}/publish", {}).status_code == 303


# --- The head ------------------------------------------------------------------

def test_the_head_has_today_the_role_and_both_new_buttons(client_as):
    today = date.today().isoformat()  # the office's day, where the Console runs
    for role, label in (("admin", "Director"), ("editor", "Analyst")):
        page = client_as(role).get("/admin").text
        head = re.search(r'<div class="head-page">(.*?)</div>\s*<dl class="figures-console">',
                         page, re.S).group(1)
        assert "<h1>Dashboard</h1>" in head
        assert f'<dt>Today</dt><dd class="text-mono"><time datetime="{today}">{today}</time></dd>' in head
        assert f"<dt>Signed in as</dt><dd>{label}</dd>" in head
        assert '<a class="button-secondary" href="/admin/reports/new">New Report</a>' in head
        assert '<a class="button-primary" href="/admin/data-bites/new">New Data Bite</a>' in head


# --- The counts ----------------------------------------------------------------

def counts(c: TestClient) -> dict[str, tuple[str, str, str]]:
    """Each count as {id: (href, label, number)}."""
    return {key: (href, label, number) for key, href, label, number in re.findall(
        r'<div id="count-([a-z-]+)"><dt><a href="([^"]+)">([^<]+)</a></dt>'
        r'<dd class="text-mono">(\d+)</dd></div>', c.get("/admin").text)}


def test_four_counts_each_linking_to_its_filtered_list(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    for slug in ("a", "b"):
        create(analyst, "data-bites", slug)
    publish(analyst, "data-bites", create(analyst, "data-bites", "c"))
    create(analyst, "reports", "draft-report")
    for slug in ("live-1", "live-2"):
        publish(director, "reports", create(director, "reports", slug))

    assert counts(analyst) == counts(director) == {
        "data-bite-published": ("/admin/data-bites?status=published", "Data Bites published", "1"),
        "data-bite-draft": ("/admin/data-bites?status=draft", "Data Bite drafts", "2"),
        "report-published": ("/admin/reports?status=published", "Reports published", "2"),
        "report-draft": ("/admin/reports?status=draft", "Report drafts", "1"),
    }


def test_each_count_matches_the_list_it_links_to(client_as):
    director = client_as("admin")
    publish(director, "reports", create(director, "reports", "live"))
    create(director, "reports", "draft")
    for href, _, number in counts(director).values():
        assert len(re.findall(r'<tr id="[a-z-]+-\d+" role="row">', director.get(href).text)) == int(number)


# --- 01 Waiting for you ----------------------------------------------------------

def test_the_director_waits_on_draft_reports_and_not_published_ones(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    by_analyst = create(analyst, "reports", "cds")
    by_director = create(director, "reports", "factbook")
    publish(director, "reports", create(analyst, "reports", "live"))
    create(analyst, "data-bites", "bite-draft")  # a Data Bite isn't the Director's to publish

    assert sorted(waiting(director)) == sorted([f"report-{by_analyst}", f"report-{by_director}"])


def test_the_directors_draft_reports_are_oldest_update_first(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    newer, older = create(analyst, "reports", "newer"), create(analyst, "reports", "older")
    set_updated("reports", newer, "2026-09-30 12:00:00")
    set_updated("reports", older, "2026-09-01 12:00:00")
    assert waiting(director) == [f"report-{older}", f"report-{newer}"]


def test_each_waiting_report_has_review_and_who_drafted_it(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = create(analyst, "reports", "cds")
    set_updated("reports", rid, "2026-09-14 10:00:00")
    row = item(director.get("/admin").text, "waiting", f"report-{rid}")
    assert f'<a href="/admin/reports/{rid}">Cds</a>' in row
    assert '<span class="badge-state badge-state-draft">Draft</span>' in row
    assert f'<a class="button-secondary" href="/admin/reports/{rid}">Review</a>' in row
    assert ('Drafted by editor (Analyst) · updated '
            '<time class="text-mono" datetime="2026-09-14T10:00:00">2026-09-14</time>') in row


def test_the_directors_own_draft_report_says_drafted_by_you(client_as):
    director = client_as("admin")
    rid = create(director, "reports", "fact-sheet")
    assert "Drafted by you · updated" in item(director.get("/admin").text, "waiting", f"report-{rid}")


def test_an_analyst_waits_on_their_own_drafts_of_both_kinds(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    riley = second_analyst(director)
    bite, report = create(analyst, "data-bites", "mine"), create(analyst, "reports", "my-report")
    set_updated("data_bites", bite, "2026-09-01 12:00:00")
    set_updated("reports", report, "2026-09-20 12:00:00")
    publish(analyst, "data-bites", create(analyst, "data-bites", "mine-live"))
    create(riley, "data-bites", "rileys")
    create(riley, "reports", "rileys-report")
    create(director, "reports", "directors")

    # Most recently updated first: where they left off.
    assert waiting(analyst) == [f"report-{report}", f"data-bite-{bite}"]
    assert len(waiting(riley)) == 2 and f"data-bite-{bite}" not in waiting(riley)


def test_each_of_an_analysts_drafts_has_edit_and_its_kind(client_as):
    analyst = client_as("editor")
    bite = create(analyst, "data-bites", "mine")
    row = item(analyst.get("/admin").text, "waiting", f"data-bite-{bite}")
    assert f'<a class="button-secondary" href="/admin/data-bites/{bite}">Edit</a>' in row
    assert "Data Bite · updated" in row


def test_waiting_says_so_when_it_is_empty(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    publish(director, "reports", create(director, "reports", "live"))
    assert "No draft Reports are waiting." in section(director.get("/admin").text, "waiting-title")
    assert "You have no drafts." in section(analyst.get("/admin").text, "waiting-title")
    assert waiting(director) == waiting(analyst) == []


def test_waiting_says_what_only_the_director_can_do(client_as):
    page = client_as("admin").get("/admin").text
    assert "Only the Director can publish a Report" in section(page, "waiting-title")


# --- 02 Recently changed -----------------------------------------------------------

def test_recently_changed_is_the_8_newest_of_both_kinds(client_as):
    director = client_as("admin")
    ids = []
    for n in range(10):
        kind, table = (("reports", "reports") if n % 2 else ("data-bites", "data_bites"))
        item_id = create(director, kind, f"item-{n}")
        set_updated(table, item_id, f"2026-09-{n + 10:02d} 12:00:00")
        ids.append(("report-" if n % 2 else "data-bite-") + item_id)
    assert recent(director) == list(reversed(ids))[:8]


def test_each_recent_item_has_its_state_date_kind_and_author(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    bite = create(analyst, "data-bites", "fall")
    publish(analyst, "data-bites", bite)
    set_updated("data_bites", bite, "2026-09-12 08:30:00")
    row = item(director.get("/admin").text, "recent", f"data-bite-{bite}")
    assert f'<a href="/admin/data-bites/{bite}">Fall</a>' in row
    assert '<span class="badge-state badge-state-published">Published</span>' in row
    assert '<time class="text-mono" datetime="2026-09-12T08:30:00">2026-09-12</time>' in row
    assert "Data Bite · editor" in row


def test_recently_changed_links_to_all_content(client_as):
    page = client_as("editor").get("/admin").text
    assert 'href="/admin/content">All content</a>' in section(page, "recent-title")


def test_recently_changed_says_so_when_there_is_nothing(client_as):
    assert "Nothing yet." in section(client_as("editor").get("/admin").text, "recent-title")


# --- The side panels -----------------------------------------------------------------

def panel(page: str, title: str) -> str | None:
    match = re.search(rf'<div class="panel-console"><h2>{title}</h2>(.*?)</div>', page, re.S)
    return match and match.group(1)


def test_the_public_site_panel_says_when_publishing_reaches_it(client_as):
    for role in ("admin", "editor"):
        site = panel(client_as(role).get("/admin").text, "The public site")
        assert site and "<code>uv run cms publish</code>" in site
        assert '<a href="/index.html">View the site ↗</a>' in site


def test_only_the_director_has_the_homepage_panel_with_when_it_was_saved(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    with db.connect() as conn:  # setup: settings saved, so no longer the sample
        conn.execute("UPDATE homepage SET headline = 'Our numbers,',"
                     " updated_at = '2026-09-28 16:00:00'")
    homepage = panel(director.get("/admin").text, "Homepage")
    assert homepage and 'Last saved <time class="text-mono" datetime="2026-09-28T16:00:00">2026-09-28</time>' in homepage
    assert '<a class="button-secondary" href="/admin/homepage">Edit homepage</a>' in homepage
    assert panel(analyst.get("/admin").text, "Homepage") is None


def test_the_homepage_panel_says_when_the_settings_were_never_saved(client_as):
    # A new site's settings are the seeded sample: their time is the seed's,
    # not a save's.
    homepage = panel(client_as("admin").get("/admin").text, "Homepage")
    assert homepage and "Not saved yet: still the sample a new site starts with." in homepage
    assert "Last saved" not in homepage


# --- Nothing leaks -----------------------------------------------------------------

def test_nothing_from_the_dashboard_reaches_the_public_site(client_as, tmp_path):
    director, analyst = client_as("admin"), client_as("editor")
    create(analyst, "reports", "unreleased-cds", title="Unreleased CDS draft")
    publish(director, "reports", create(director, "reports", "factbook"))
    site = render_site(tmp_path / "site")
    for path in site.rglob("*.html"):
        text = path.read_text()
        assert "Waiting for you" not in text and "Unreleased CDS draft" not in text, path
