"""T11: Chart images on Reports (issue #13).

The checks on an upload itself (formats, size, count, names) are T10's shared
code, tested there; here, what a Report adds: the lockdown, the Report's
pages and export, and independence from its attached PDF.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import reports, settings
from app.publish import render_site
from tests.conftest import post_form, second_analyst
from tests.test_t04_reports import REPORT, create_report
from tests.test_t05_report_files import PDF, pdf, post_with_file, reports_file
from tests.test_t07_public_site import crawl, published_bite, published_report
from tests.test_t08_publish import exported
from tests.test_t09_tables import content_body
from tests.test_t06_admin_console import body_of, preview_of
from tests.test_t10_chart_images import CHART, WEBP, img_attributes, img_tags, png, png_bytes

PNG = png()[1]


def upload(c: TestClient, rid: str, file, *, with_csrf=True):
    return post_with_file(c, f"/admin/reports/{rid}/images", {}, file, with_csrf=with_csrf)


def delete_image(c: TestClient, rid: str, name: str, *, with_csrf=True):
    return post_form(c, f"/admin/reports/{rid}/images/{name}/delete", {}, with_csrf=with_csrf)


def stored(rid: str) -> list[str]:
    folder = settings.UPLOADS / "images" / "reports" / rid
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def publish(director: TestClient, rid: str) -> None:
    assert post_form(director, f"/admin/reports/{rid}/publish", {}).status_code == 303


def edit_report(c: TestClient, rid: str, file=None, **override):
    return post_with_file(c, f"/admin/reports/{rid}", {**REPORT, **override}, file)


# Who may add or delete a Report's images

def test_analyst_uploads_to_a_draft_report_and_the_edit_page_lists_it(client_as):
    analyst = client_as("editor")
    rid = create_report(analyst)

    response = upload(analyst, rid, png())
    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/reports/{rid}"
    assert "<code>fall-by-class.png</code>" in analyst.get(f"/admin/reports/{rid}").text
    assert stored(rid) == ["fall-by-class.png"]

    served = analyst.get(f"/admin/reports/{rid}/images/fall-by-class.png")
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"


def test_any_analyst_manages_images_on_a_draft_report_another_analyst_started(client_as):
    director = client_as("admin")
    riley = second_analyst(director)
    rid = create_report(client_as("editor"))

    assert upload(riley, rid, png("riley.png")).status_code == 303
    assert upload(riley, rid, png("drop.png")).status_code == 303
    assert delete_image(riley, rid, "drop.png").status_code == 303
    assert stored(rid) == ["riley.png"]


def test_the_director_manages_images_on_a_report_in_any_state(client_as):
    director = client_as("admin")
    draft = create_report(client_as("editor"))
    published = published_report(director, slug="cds")

    for rid in (draft, published):
        assert upload(director, rid, png("keep.png")).status_code == 303
        assert upload(director, rid, png("drop.png")).status_code == 303
        assert delete_image(director, rid, "drop.png").status_code == 303
        assert stored(rid) == ["keep.png"], rid


def test_once_published_an_analysts_upload_and_delete_are_rejected(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = create_report(analyst)
    # Allowed while the Report is a draft...
    assert upload(analyst, rid, png("before.png")).status_code == 303
    assert upload(analyst, rid, png("also.png")).status_code == 303
    assert delete_image(analyst, rid, "also.png").status_code == 303

    publish(director, rid)
    # ...and rejected server-side once it is published, whatever is sent.
    assert upload(analyst, rid, png("after.png")).status_code == 403
    assert upload(analyst, rid, png("before.png", png_bytes(b"\x00\x00\xff"))).status_code == 403
    assert upload(analyst, rid, ("chart.svg", b"<svg/>", "image/svg+xml")).status_code == 403
    assert delete_image(analyst, rid, "before.png").status_code == 403
    assert delete_image(analyst, rid, "no-such.png").status_code == 403
    assert stored(rid) == ["before.png"]
    assert analyst.get(f"/admin/reports/{rid}/images/before.png").content == PNG

    # Unpublished again, it is the Analyst's to change once more.
    assert post_form(director, f"/admin/reports/{rid}/unpublish", {}).status_code == 303
    assert delete_image(analyst, rid, "before.png").status_code == 303


def test_a_report_published_after_the_page_checked_still_rejects_an_analyst(client_as, monkeypatch):
    """The routes check the lockdown first, then the write checks it again in
    its own UPDATE, so a Report published in between is still locked."""
    director, analyst = client_as("admin"), client_as("editor")
    rid = create_report(analyst)
    upload(analyst, rid, png("before.png"))
    publish(director, rid)
    monkeypatch.setattr(reports, "can_edit", lambda report, user: True)  # it was a draft then

    assert upload(analyst, rid, png("after.png")).status_code == 403
    assert delete_image(analyst, rid, "before.png").status_code == 403
    assert stored(rid) == ["before.png"]
    assert upload(director, rid, png("director.png")).status_code == 303


def test_a_locked_report_shows_its_images_but_no_image_forms(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = create_report(analyst, body=CHART)
    upload(analyst, rid, png())
    publish(director, rid)

    page = analyst.get(f"/admin/reports/{rid}").text
    assert img_tags(preview_of(page)) == [
        '<img src="../images/reports/factbook/fall-by-class.png" alt="Fall enrollment by class">']
    assert f'action="/admin/reports/{rid}/images' not in page
    assert f'action="/admin/reports/{rid}/images' in director.get(f"/admin/reports/{rid}").text


def test_upload_checks_are_t10s(client_as):
    analyst = client_as("editor")
    rid = create_report(analyst)
    for file, message in [(("chart.svg", b"<svg/>", "image/svg+xml"), "Only PNG, JPEG, or WebP"),
                          (png(content=b"<html></html>"), "not a valid PNG"),
                          (("", b"", "application/octet-stream"), "Choose an image")]:
        response = upload(analyst, rid, file)
        assert response.status_code == 400 and message in response.text, file
    for i in range(10):
        upload(analyst, rid, png(f"chart-{i}.png"))
    response = upload(analyst, rid, png("chart-10.png"))
    assert response.status_code == 400 and "This Report already has 10 images" in response.text
    assert len(stored(rid)) == 10


def test_image_routes_404_for_a_missing_report_or_image(client_as):
    director = client_as("admin")
    rid = create_report(director)
    upload(director, rid, png())
    assert upload(director, "9999", png()).status_code == 404
    assert delete_image(director, "9999", "fall-by-class.png").status_code == 404
    assert director.get("/admin/reports/9999/images/fall-by-class.png").status_code == 404
    assert post_form(director, "/admin/reports/9999/preview", {"body": CHART}).status_code == 404
    for name in ("..%2F..%2Fcms.db", "FALL-BY-CLASS.png", "no-such.png"):
        assert director.get(f"/admin/reports/{rid}/images/{name}").status_code == 404, name
        assert delete_image(director, rid, name).status_code == 404, name
    assert stored(rid) == ["fall-by-class.png"]


def test_deleting_a_report_deletes_its_images_and_its_file(client_as):
    director = client_as("admin")
    rid = create_report(director)
    assert edit_report(director, rid, pdf()).status_code == 303
    upload(director, rid, png())

    assert post_form(director, f"/admin/reports/{rid}/delete", {}).status_code == 303
    assert not (settings.UPLOADS / "images" / "reports" / rid).exists()
    assert not reports_file(rid).exists()


def test_a_new_report_never_inherits_images_left_under_its_id(client_as, client):
    director = client_as("admin")
    first = create_report(director)
    leftover = settings.UPLOADS / "images" / "reports" / str(int(first) + 1)
    leftover.mkdir(parents=True)
    (leftover / "old-chart.png").write_bytes(PNG)

    rid = published_report(director, slug="cds", body="![Old](image:old-chart.png)")
    assert rid == str(int(first) + 1)
    assert stored(rid) == []
    assert client.get("/images/reports/cds/old-chart.png").status_code == 404


# The chart images and the attached PDF are independent

def test_images_and_the_attached_pdf_leave_each_other_untouched(client_as):
    analyst = client_as("editor")
    rid = create_report(analyst)
    assert edit_report(analyst, rid, pdf()).status_code == 303

    # Adding and removing an image leaves the PDF.
    upload(analyst, rid, png("keep.png"))
    upload(analyst, rid, png("drop.png"))
    delete_image(analyst, rid, "drop.png")
    assert reports_file(rid).read_bytes() == PDF
    assert "factbook-2026.pdf" in analyst.get(f"/admin/reports/{rid}").text

    # Replacing, then removing, the PDF leaves the images.
    revised = PDF.replace(b"%%EOF", b"% revised\n%%EOF")
    assert edit_report(analyst, rid, pdf("factbook-2027.pdf", revised)).status_code == 303
    assert reports_file(rid).read_bytes() == revised
    assert stored(rid) == ["keep.png"]
    assert post_form(analyst, f"/admin/reports/{rid}/file/delete", {}).status_code == 303
    assert not reports_file(rid).exists()
    assert stored(rid) == ["keep.png"]
    # Saving the body with no file chosen leaves both.
    assert edit_report(analyst, rid, body=CHART).status_code == 303
    assert stored(rid) == ["keep.png"]


def test_a_pdf_named_like_an_image_is_not_one_and_vice_versa(client_as):
    analyst = client_as("editor")
    rid = create_report(analyst)
    assert upload(analyst, rid, ("factbook.pdf", PDF, "application/pdf")).status_code == 400
    assert edit_report(analyst, rid, ("chart.png", PNG, "image/png")).status_code == 400
    assert stored(rid) == [] and not reports_file(rid).exists()


# Login and CSRF

def test_every_report_image_route_requires_login(client_as, client):
    director = client_as("admin")
    rid = create_report(director)
    upload(director, rid, png())

    for method, path in [("get", f"/admin/reports/{rid}/images/fall-by-class.png"),
                         ("post", f"/admin/reports/{rid}/images"),
                         ("post", f"/admin/reports/{rid}/images/fall-by-class.png/delete"),
                         ("post", f"/admin/reports/{rid}/preview")]:
        response = getattr(client, method)(path, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/login", path
    assert stored(rid) == ["fall-by-class.png"]


def test_report_image_forms_carry_csrf_and_a_stripped_post_is_rejected(client_as):
    director = client_as("admin")
    rid = create_report(director)
    upload(director, rid, png())

    page = director.get(f"/admin/reports/{rid}").text
    for action in (f"/admin/reports/{rid}/images", f"/admin/reports/{rid}/images/fall-by-class.png/delete"):
        form = re.search(rf'<form[^>]*action="{re.escape(action)}".*?</form>', page, re.S)
        assert form and 'name="csrf_token"' in form.group(0), action

    assert upload(director, rid, png("other.png"), with_csrf=False).status_code == 403
    assert delete_image(director, rid, "fall-by-class.png", with_csrf=False).status_code == 403
    assert stored(rid) == ["fall-by-class.png"]


# The image: reference, as for a Data Bite

def test_the_preview_shows_the_draft_image_from_its_preview_site(client_as, client):
    analyst = client_as("editor")
    rid = create_report(analyst, body=CHART)
    upload(analyst, rid, png())

    expected = '<img src="../images/reports/factbook/fall-by-class.png" alt="Fall enrollment by class">'
    preview = post_form(analyst, f"/admin/reports/{rid}/preview", {**REPORT, "body": CHART})
    assert preview.status_code == 200 and img_tags(body_of(preview.text)) == [expected]
    served = analyst.get(f"/admin/reports/{rid}/preview/images/reports/factbook/fall-by-class.png")
    assert served.status_code == 200 and served.content == PNG
    assert client.get("/images/reports/factbook/fall-by-class.png").status_code == 404
    page = analyst.get(f"/admin/reports/{rid}").text
    assert img_tags(preview_of(page)) == [expected]
    assert f'"/admin/reports/{rid}/preview"' in page


def test_the_public_page_and_the_export_show_the_image_relatively(client_as, client, tmp_path):
    director = client_as("admin")
    rid = published_report(director, body=CHART)
    upload(director, rid, png())

    expected = '<img src="../images/reports/factbook/fall-by-class.png" alt="Fall enrollment by class">'
    assert img_tags(content_body(client.get("/reports/factbook.html").text)) == [expected]
    served = client.get("/images/reports/factbook/fall-by-class.png")
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"

    site = exported(render_site(tmp_path / "site"))
    assert img_tags(site["reports/factbook.html"].decode()) == [expected]
    assert site["images/reports/factbook/fall-by-class.png"] == PNG


def test_an_unknown_name_renders_nothing(client_as, client):
    director = client_as("admin")
    body = "Before ![Missing chart](image:no-such.png) after"
    rid = published_report(director, body=body)
    upload(director, rid, png())

    for html in (body_of(post_form(director, f"/admin/reports/{rid}/preview",
                                   {**REPORT, "body": body}).text),
                 preview_of(director.get(f"/admin/reports/{rid}").text),
                 content_body(client.get("/reports/factbook.html").text)):
        assert "<img" not in html and "Missing chart" not in html, html
        assert "Before" in html and "after" in html


def test_script_in_the_description_is_inert(client_as, client):
    director = client_as("admin")
    body = '![x" onerror="alert(1)](image:fall-by-class.png) ![<script>alert(1)</script>](image:fall-by-class.png)'
    rid = published_report(director, body=body)
    upload(director, rid, png())

    for html in (content_body(client.get("/reports/factbook.html").text),
                 post_form(director, f"/admin/reports/{rid}/preview", {"body": body}).text):
        assert [set(attributes) for attributes in img_attributes(html)] == [{"src", "alt"}] * 2
        assert "<script" not in html


def test_the_edit_page_warns_of_an_empty_description_without_blocking_the_save(client_as):
    analyst = client_as("editor")
    rid = create_report(analyst)
    upload(analyst, rid, png())

    assert edit_report(analyst, rid, body="![](image:fall-by-class.png)").status_code == 303
    warning = re.search(r'<p class="content-image-warning"[^>]*>(.*?)</p>',
                        analyst.get(f"/admin/reports/{rid}").text, re.S)
    assert warning and "fall-by-class.png" in warning.group(1)


# The draft gate and the export

def test_a_draft_reports_images_are_never_public(client_as, client, tmp_path):
    director, analyst = client_as("admin"), client_as("editor")
    published_report(director)
    draft = create_report(analyst, slug="draft-cds", title="Draft CDS", body=CHART)
    upload(analyst, draft, png("unreleased-chart.png", png_bytes(b"\x12\x34\x56")))

    assert client.get("/images/reports/draft-cds/unreleased-chart.png").status_code == 404
    assert "draft-cds" not in b"".join(crawl(client).values()).decode(errors="replace")
    site = exported(render_site(tmp_path / "site"))
    assert not any("draft-cds" in path or "unreleased" in path for path in site)
    assert all(png_bytes(b"\x12\x34\x56") not in content for content in site.values())


def test_unpublishing_takes_the_images_down(client_as, client, tmp_path):
    director = client_as("admin")
    rid = published_report(director, body=CHART)
    upload(director, rid, png())
    out = render_site(tmp_path / "site")
    assert (out / "images/reports/factbook/fall-by-class.png").is_file()

    assert post_form(director, f"/admin/reports/{rid}/unpublish", {}).status_code == 303
    assert client.get("/images/reports/factbook/fall-by-class.png").status_code == 404
    assert not any(path.startswith("images/") for path in exported(render_site(out)))


def test_the_public_path_follows_the_slug(client_as, client):
    director = client_as("admin")
    rid = published_report(director, body=CHART)
    upload(director, rid, png())
    assert edit_report(director, rid, slug="factbook-2026", body=CHART).status_code == 303

    assert client.get("/images/reports/factbook/fall-by-class.png").status_code == 404
    assert client.get("/images/reports/factbook-2026/fall-by-class.png").content == PNG


def test_a_data_bite_and_a_report_with_one_slug_keep_their_images_apart(client_as, client):
    director = client_as("admin")
    bid = published_bite(director, slug="factbook", body=CHART)
    rid = published_report(director, body=CHART)
    post_with_file(director, f"/admin/data-bites/{bid}/images", {}, png(content=png_bytes(b"\x01\x01\x01")))
    upload(director, rid, png())

    assert client.get("/images/reports/factbook/fall-by-class.png").content == PNG
    assert client.get("/images/data-bites/factbook/fall-by-class.png").content == png_bytes(b"\x01\x01\x01")


def test_the_export_with_report_images_is_the_live_public_site(client_as, client, tmp_path):
    director, analyst = client_as("admin"), client_as("editor")
    rid = published_report(director, body=CHART + "\n\n![Spring](image:spring.webp)")
    assert edit_report(director, rid, pdf(), body=CHART + "\n\n![Spring](image:spring.webp)").status_code == 303
    upload(director, rid, png())
    upload(director, rid, ("spring.webp", WEBP, "image/webp"))
    upload(director, rid, png("not-referenced.png"))
    bid = published_bite(analyst, body=CHART)
    post_with_file(analyst, f"/admin/data-bites/{bid}/images", {}, png())
    draft = create_report(analyst, slug="draft-cds", body=CHART)
    upload(analyst, draft, png())

    site = exported(render_site(tmp_path / "site"))
    live = {path.removeprefix("/"): content for path, content in crawl(client).items()}
    assert {"images/reports/factbook/fall-by-class.png", "images/reports/factbook/spring.webp",
            "images/data-bites/fall-enrollment/fall-by-class.png", "reports/files/factbook.pdf"} <= live.keys()
    # An uploaded image the body doesn't place is still exported, as it is served.
    assert set(site) - set(live) == {"images/reports/factbook/not-referenced.png"}
    for path, content in live.items():
        assert site[path] == content, path
    assert client.get("/images/reports/factbook/not-referenced.png").content == \
        site["images/reports/factbook/not-referenced.png"]
