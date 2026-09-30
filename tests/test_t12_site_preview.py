"""T12: Site preview (issue #15).

A Data Bite's or Report's Site preview is its public page, rendered by the
public templates as if it were published, with the form's unsaved edits and a
"Draft preview, not published" banner. It is served under the item's admin
path (e.g. /admin/data-bites/3/preview/), which is the preview's own copy of
the site: its links stay relative, as the export's, and a <base> places the
page at its path in that copy.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

import pytest
from fastapi.testclient import TestClient

from app import data_bites, reports, settings
from app.publish import render_site
from tests.conftest import csrf_from, post_form
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import REPORT, create_report, report_id
from tests.test_t05_report_files import PDF, pdf, post_with_file
from tests.test_t06_admin_console import PAYLOAD, assert_inert
from tests.test_t06_admin_console import site_preview_page as framed
from tests.test_t07_public_site import (DRAFT_LEAKS, a_site_with_drafts, crawl, nav,
                                        published_bite, published_report)
from tests.test_t08_publish import exported
from tests.test_t09_tables import content_body
from tests.test_t10_chart_images import CHART, img_tags, png
from tests.test_t10_chart_images import upload as upload_to_bite
from tests.test_t11_report_chart_images import upload as upload_to_report

BANNER = "Draft preview, not published"
KINDS = [pytest.param("data-bites", BITE, create_bite, published_bite, id="data-bite"),
         pytest.param("reports", REPORT, create_report, published_report, id="report")]


def preview(c: TestClient, kind: str, item_id: str | None = None, *, with_csrf=True, **form):
    """POST the edit form (or, with no item, the create form) to its Site preview."""
    path = f"/admin/{kind}/{item_id}/preview" if item_id else f"/admin/{kind}/preview"
    return post_form(c, path, form, with_csrf=with_csrf)


def base_of(page: str) -> str:
    [base] = re.findall(r'<base href="([^"]+)">', page)
    return base


def links(page: str) -> list[str]:
    """Every href and src on the page but its <base>'s."""
    return [link for tag, link in re.findall(r'<(\w+)[^>]*?(?:href|src)="([^"]+)"', page)
            if tag != "base"]


def without_preview_marks(page: str) -> str:
    """The page without its banner and <base>: what the export would write."""
    page = re.sub(r'\s*<base href="[^"]*">', "", page)
    return re.sub(r'\s*<p class="site-preview-banner"[^>]*>[^<]*</p>', "", page)


def stored_row(kind: str, item_id: str):
    return (data_bites if kind == "data-bites" else reports).get(int(item_id))


# The public page, as if published

@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_a_drafts_site_preview_is_its_public_page_with_the_unsaved_edits(
        client_as, kind, item, create, publish):
    analyst = client_as("editor")
    item_id = create(analyst)

    response = preview(analyst, kind, item_id, title="Unsaved title",
                       slug=item["slug"], body="Unsaved *body*")
    assert response.status_code == 200
    page = response.text
    assert f'<p class="site-preview-banner" role="note">{BANNER}</p>' in page
    assert '<link rel="stylesheet" href="../style.css">' in page
    assert "<h1>Unsaved title</h1>" in page
    assert content_body(page) == "<p>Unsaved <em>body</em></p>\n"
    assert base_of(page) == f"/admin/{kind}/{item_id}/preview/{kind}/{item['slug']}.html"
    # The admin console's own furniture stays out of it.
    assert "csrf_token" not in page and "/admin" not in without_preview_marks(page)


def test_a_data_bites_preview_has_its_date_line(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    created = stored_row("data-bites", bid)["created_at"][:10]
    page = preview(analyst, "data-bites", bid, **BITE).text
    assert f'<p class="data-bite-meta"><small><time datetime="{created}">{created}</time>' in page


@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_the_site_preview_is_the_page_the_export_will_write(
        client_as, tmp_path, kind, item, create, publish):
    director = client_as("admin")
    item_id = publish(director, body=CHART)
    upload = upload_to_bite if kind == "data-bites" else upload_to_report
    upload(director, item_id, png())
    if kind == "reports":
        assert post_with_file(director, f"/admin/reports/{item_id}", {**item, "body": CHART},
                              pdf()).status_code == 303
    published_report(director, slug="cds", title="Common Data Set 2025-26")

    page = preview(director, kind, item_id, **{**item, "body": CHART}).text
    site = exported(render_site(tmp_path / "site"))
    assert without_preview_marks(page) == site[f"{kind}/{item['slug']}.html"].decode()
    assert img_tags(page) == [f'<img src="../images/{kind}/{item["slug"]}/fall-by-class.png"'
                              ' alt="Fall enrollment by class">']


def test_a_reports_preview_links_its_attached_file(client_as):
    analyst = client_as("editor")
    assert post_with_file(analyst, "/admin/reports", REPORT, pdf()).status_code == 303
    rid = report_id(analyst, REPORT["slug"])
    page = preview(analyst, "reports", rid, **REPORT).text
    assert ('<a href="../reports/files/factbook.pdf" download="factbook-2026.pdf">'
            'Download factbook-2026.pdf</a>') in page


@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_every_link_in_the_preview_is_relative_and_reaches_the_preview_site(
        client_as, kind, item, create, publish):
    """Each link resolves, against the <base>, to a path the preview serves:
    the stylesheet and the item's own draft files from its preview site, and
    any other page by sending the browser to the published site."""
    director, analyst = client_as("admin"), client_as("editor")
    published_bite(director, slug="spring-survey", title="Spring survey")
    published_report(director, slug="cds", title="Common Data Set 2025-26")
    item_id = create(analyst, body=CHART)
    (upload_to_bite if kind == "data-bites" else upload_to_report)(analyst, item_id, png())
    if kind == "reports":
        post_with_file(analyst, f"/admin/reports/{item_id}", {**item, "body": CHART}, pdf())

    page = preview(analyst, kind, item_id, **{**item, "body": CHART}).text
    base = base_of(page)
    found = links(page)
    assert "../style.css" in found and "../index.html" in found
    assert f"../images/{kind}/{item['slug']}/fall-by-class.png" in found
    for link in found:
        assert not link.startswith("/") and "://" not in link, link
        url = urljoin(base, link)
        assert url.startswith(f"/admin/{kind}/{item_id}/preview/"), (link, url)
        response = analyst.get(url, follow_redirects=False)
        public = "/" + url.removeprefix(f"/admin/{kind}/{item_id}/preview/")
        if link == "../style.css":
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/css")
        elif "/images/" in url or "/files/" in url:
            # The draft's own files: shown here, though the public site 404s them.
            assert response.status_code == 200, url
            assert director.get(public).status_code == 404, public
        elif public == f"/{kind}/{item['slug']}.html":
            continue  # the draft's own page, in a draft Report's nav: not public
        else:
            assert (response.status_code, response.headers["location"]) == (303, public), url
            assert director.get(public).status_code == 200, public


def test_the_preview_site_never_redirects_off_the_site(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    for rest in ("/evil.test/x", "%2F%2Fevil.test", "%5Cevil.test", "\\\\evil.test"):
        response = analyst.get(f"/admin/data-bites/{bid}/preview/{rest}", follow_redirects=False)
        if response.status_code in (301, 302, 303, 307, 308):
            location = response.headers["location"]
            assert location.startswith("/") and location[1:2] not in ("/", "\\"), (rest, location)


# The nav: the previewed Report as if published, and no other draft

def test_a_draft_report_is_in_its_own_previews_nav_and_nowhere_else(client_as, client, tmp_path):
    director, analyst = client_as("admin"), client_as("editor")
    published_report(director)
    published_report(director, slug="cds", title="Common Data Set 2025-26")
    drafted = create_report(analyst, slug="survey-calendar", title="Survey Calendar")
    other = create_report(analyst, slug="unreleased-cds", title="Unreleased CDS")
    bid = create_bite(analyst)

    own = nav(preview(analyst, "reports", drafted, **{**REPORT, "slug": "survey-calendar",
                                                        "title": "Survey Calendar"}).text)
    # In title order, as the published nav is.
    assert own.index("Common Data Set") < own.index(REPORT["title"]) < own.index("Survey Calendar")
    assert 'href="../reports/survey-calendar.html"' in own
    assert "Unreleased CDS" not in own and "unreleased-cds" not in own

    for page in (preview(analyst, "reports", other, **REPORT).text,
                 preview(analyst, "data-bites", bid, **BITE).text):
        assert "Survey Calendar" not in nav(page) and "survey-calendar" not in nav(page)
    assert "Survey Calendar" not in framed(analyst.get(f"/admin/reports/{other}").text)
    # And the public site and the export never saw either.
    for content in [*crawl(client).values(), *exported(render_site(tmp_path / "site")).values()]:
        for leak in (b"Survey Calendar", b"survey-calendar", b"Unreleased CDS"):
            assert leak not in content, leak


def test_a_published_reports_preview_lists_it_once_under_its_unsaved_title(client_as):
    director = client_as("admin")
    rid = published_report(director)
    own = nav(preview(director, "reports", rid, **{**REPORT, "title": "Factbook 2027"}).text)
    assert own.count('href="../reports/factbook.html"') == 1
    assert "Factbook 2027" in own and REPORT["title"] not in own


@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_a_published_item_still_shows_the_banner(client_as, kind, item, create, publish):
    director = client_as("admin")
    item_id = publish(director)
    assert BANNER in preview(director, kind, item_id, **item).text
    assert BANNER in framed(director.get(f"/admin/{kind}/{item_id}").text)
    assert BANNER not in client_as("editor").get(f"/{kind}/{item['slug']}.html").text


# On the edit page

@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_the_edit_page_embeds_the_site_preview_beside_the_body(client_as, kind, item, create, publish):
    analyst = client_as("editor")
    item_id = create(analyst)
    page = analyst.get(f"/admin/{kind}/{item_id}").text

    shown = framed(page)
    assert BANNER in shown and base_of(shown).startswith(f"/admin/{kind}/{item_id}/preview/")
    assert '<link rel="stylesheet" href="../style.css">' in shown
    assert content_body(shown) == content_body(preview(analyst, kind, item_id, **item).text)
    # The old admin-styled preview is gone.
    assert "content-preview" not in page and "/admin/preview" not in page
    # Typing re-renders it; "Preview on site" posts the unsaved form to a new tab.
    assert f'"/admin/{kind}/{item_id}/preview"' in page
    assert re.search(rf'<button type="submit" formaction="/admin/{kind}/{item_id}/preview"'
                     r' formtarget="_blank" formnovalidate>Preview on site</button>', page)
    assert "Preview is not updating" in page
    for width in ("Desktop", "Phone"):
        assert re.search(rf'<button type="button"[^>]*data-width="{width.lower()}"[^>]*>{width}</button>', page)
    # "Save changes" stays the form's first submit button, so Enter saves.
    assert page.index(">Save changes</button>") < page.index(">Preview on site</button>")


def test_a_failed_save_previews_what_was_typed(client_as):
    analyst = client_as("editor")
    response = post_form(analyst, "/admin/data-bites",
                         {"title": "Kept", "slug": "Not a slug", "body": "Unsaved *work*"})
    assert response.status_code == 400
    shown = framed(response.text)
    assert "<h1>Kept</h1>" in shown and "<em>work</em>" in shown


def test_an_analyst_sees_a_locked_reports_saved_page_but_cannot_preview_edits(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = create_report(analyst, body=PAYLOAD)
    post_form(director, f"/admin/reports/{rid}/publish", {})

    page = analyst.get(f"/admin/reports/{rid}").text
    assert_inert(content_body(framed(page)))
    assert "Preview on site" not in page
    assert preview(analyst, "reports", rid, **REPORT).status_code == 403
    assert preview(director, "reports", rid, **REPORT).status_code == 200


# The create page

@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_the_create_page_has_a_site_preview_without_chart_images(client_as, kind, item, create, publish):
    analyst = client_as("editor")
    page = analyst.get(f"/admin/{kind}").text
    shown = framed(page)
    assert BANNER in shown and '<link rel="stylesheet" href="../style.css">' in shown
    assert base_of(shown).startswith(f"/admin/{kind}/preview/")
    assert re.search(rf'formaction="/admin/{kind}/preview" formtarget="_blank"', page)

    response = preview(analyst, kind, **{**item, "body": CHART})
    assert response.status_code == 200 and BANNER in response.text
    assert "<h1>" + item["title"] + "</h1>" in response.text
    assert img_tags(response.text) == [] and "Enrollment by class" in response.text
    base = base_of(response.text)
    stylesheet = analyst.get(urljoin(base, "../style.css"))
    assert stylesheet.status_code == 200 and stylesheet.headers["content-type"].startswith("text/css")
    assert (data_bites if kind == "data-bites" else reports).list_all() == []


def test_a_new_data_bite_is_dated_today(client_as):
    page = preview(client_as("editor"), "data-bites", **BITE).text
    assert re.search(r'<time datetime="\d{4}-\d\d-\d\d">', page)


# Safe: sanitized, saves nothing, publishes nothing

@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_a_script_payload_is_inert_in_the_site_preview(client_as, kind, item, create, publish):
    director = client_as("admin")
    item_id = create(director)
    assert_inert(content_body(preview(director, kind, item_id, **{**item, "body": PAYLOAD}).text))
    assert_inert(content_body(preview(director, kind, **{**item, "body": PAYLOAD}).text))
    title = preview(director, kind, item_id, **{**item, "title": "<script>alert(1)</script>"}).text
    assert "<script>" not in title


@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_previewing_saves_nothing_and_writes_nothing_to_site(
        client_as, monkeypatch, tmp_path, kind, item, create, publish):
    monkeypatch.setattr(settings, "SITE", tmp_path / "site")
    director = client_as("admin")
    item_id = publish(director)
    before = dict(stored_row(kind, item_id))

    form = {**item, "title": "Changed", "slug": "changed", "body": "Changed"}
    assert preview(director, kind, item_id, **form).status_code == 200
    assert preview(director, kind, **form).status_code == 200
    if kind == "reports":
        # "Preview on site" posts the whole form, a chosen file included.
        form["csrf_token"] = csrf_from(director.get("/admin").text)
        response = director.post(f"/admin/reports/{item_id}/preview", data=form,
                                 files={"file": ("new.pdf", PDF, "application/pdf")})
        assert response.status_code == 200 and "Changed" in response.text

    assert dict(stored_row(kind, item_id)) == before
    assert len((data_bites if kind == "data-bites" else reports).list_all()) == 1
    assert not settings.SITE.exists()


def test_no_draft_reaches_the_site_after_previews(client_as, client, tmp_path):
    director, analyst = client_as("admin"), client_as("editor")
    a_site_with_drafts(director, analyst)
    for bite in data_bites.list_all():
        preview(analyst, "data-bites", str(bite["id"]), title=bite["title"],
                slug=bite["slug"], body=bite["body"])
    for found in reports.list_all():
        preview(director, "reports", str(found["id"]), title=found["title"],
                slug=found["slug"], body=found["body"])

    for content in [*crawl(client).values(), *exported(render_site(tmp_path / "site")).values()]:
        for leak in DRAFT_LEAKS:
            assert leak not in content, leak


# Login, CSRF, and missing items

@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_preview_routes_require_login(client_as, client, kind, item, create, publish):
    item_id = create(client_as("admin"), body=CHART)
    for method, path in [("post", f"/admin/{kind}/preview"),
                         ("post", f"/admin/{kind}/{item_id}/preview"),
                         ("get", f"/admin/{kind}/preview/style.css"),
                         ("get", f"/admin/{kind}/{item_id}/preview/style.css"),
                         ("get", f"/admin/{kind}/{item_id}/preview/images/{kind}/"
                                 f"{item['slug']}/fall-by-class.png"),
                         ("get", f"/admin/{kind}/{item_id}/preview/index.html")]:
        response = (client.post(path, data={"body": "hi"}, follow_redirects=False)
                    if method == "post" else client.get(path, follow_redirects=False))
        assert (response.status_code, response.headers["location"]) == (303, "/login"), path


@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_preview_routes_require_a_csrf_token(client_as, kind, item, create, publish):
    director = client_as("admin")
    item_id = create(director)
    assert preview(director, kind, item_id, with_csrf=False, **item).status_code == 403
    assert preview(director, kind, with_csrf=False, **item).status_code == 403


@pytest.mark.parametrize("kind, item, create, publish", KINDS)
def test_previewing_a_missing_item_is_404(client_as, kind, item, create, publish):
    director = client_as("admin")
    assert preview(director, kind, "9999", **item).status_code == 404
    assert director.get(f"/admin/{kind}/9999/preview/style.css").status_code == 404
