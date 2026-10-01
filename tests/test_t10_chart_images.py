"""T10: Chart images on Data Bites (issue #12)."""
from __future__ import annotations

import re
import struct
import zlib
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient

from app import chart_images, settings
from app.publish import render_site
from tests.conftest import csrf_from, post_form, second_analyst
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t06_admin_console import body_of, preview_of
from tests.test_t07_public_site import crawl, published_bite
from tests.test_t08_publish import exported
from tests.test_t09_tables import content_body


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png_bytes(pixel: bytes = b"\xff\x00\x00", *, text: bytes = b"") -> bytes:
    """A real 1x1 PNG of one RGB pixel, with an optional tEXt chunk to pad it."""
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + (_chunk(b"tEXt", b"Comment\x00" + text) if text else b"")
            + _chunk(b"IDAT", zlib.compress(b"\x00" + pixel))
            + _chunk(b"IEND", b""))


# A real PNG, and minimal JPEG and WebP files with the right signatures.
PNG = png_bytes()
JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + b"\x00" * 32 + b"\xff\xd9"
_VP8L = b"VP8L" + struct.pack("<I", 5) + b"\x2f\x00\x00\x00\x00" + b"\x00"
WEBP = b"RIFF" + struct.pack("<I", 4 + len(_VP8L)) + b"WEBP" + _VP8L


def png(name: str = "fall-by-class.png", content: bytes = PNG, declared: str = "image/png"):
    return (name, content, declared)


def upload(c: TestClient, bid: str, file, *, with_csrf=True):
    data = {"csrf_token": csrf_from(c.get("/admin").text)} if with_csrf else {}
    return c.post(f"/admin/data-bites/{bid}/images", data=data,
                  files={"file": file}, follow_redirects=False)


def delete_image(c: TestClient, bid: str, name: str, *, with_csrf=True):
    return post_form(c, f"/admin/data-bites/{bid}/images/{name}/delete", {},
                     with_csrf=with_csrf)


def stored(bid: str) -> list[str]:
    folder = settings.UPLOADS / "images" / "data-bites" / bid
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def edit_bite(c: TestClient, bid: str, **override):
    return post_form(c, f"/admin/data-bites/{bid}", {**BITE, **override})


# Uploading, listing, replacing, deleting

def test_analyst_uploads_an_image_and_the_edit_page_lists_it(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)

    response = upload(analyst, bid, png())
    assert response.status_code == 303
    assert response.headers["location"] == f"/admin/data-bites/{bid}"
    page = analyst.get(f"/admin/data-bites/{bid}").text
    # Listed by name for "Insert image" (T18), which replaced T10's snippet.
    assert "<code>fall-by-class.png</code>" in page
    assert stored(bid) == ["fall-by-class.png"]

    served = analyst.get(f"/admin/data-bites/{bid}/images/fall-by-class.png")
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"


def test_any_analyst_or_the_director_uploads_to_any_data_bite_draft_or_published(client_as):
    director = client_as("admin")
    riley = second_analyst(director)
    draft = create_bite(client_as("editor"))
    published = published_bite(client_as("editor"), slug="spring-survey")

    for c, bid in ((riley, draft), (riley, published), (director, draft), (director, published)):
        name = f"chart-{len(stored(bid))}.png"
        assert upload(c, bid, png(name)).status_code == 303
        assert name in stored(bid)


@pytest.mark.parametrize("file, declared, extension", [
    (JPEG, "image/jpeg", "jpg"), (JPEG, "image/jpeg", "jpeg"), (WEBP, "image/webp", "webp")])
def test_jpeg_and_webp_are_accepted_and_served_as_their_type(client_as, file, declared, extension):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    assert upload(analyst, bid, (f"chart.{extension}", file, declared)).status_code == 303

    served = analyst.get(f"/admin/data-bites/{bid}/images/chart.{extension}")
    assert served.content == file and served.headers["content-type"] == declared


NOT_IMAGES = [
    pytest.param(("chart.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
                  "image/svg+xml"), "Only PNG, JPEG, or WebP", id="svg"),
    pytest.param(png(content=b"<svg onload=alert(1)></svg>"), "not a valid PNG", id="svg-named-png"),
    pytest.param(png(content=b"<html><script>alert(1)</script></html>"), "not a valid PNG", id="html-named-png"),
    pytest.param(png(content=PNG[:len(PNG) // 2]), "not a valid PNG", id="truncated-png"),
    pytest.param(png(content=b""), "not a valid PNG", id="empty"),
    pytest.param(png(content=JPEG), "not a valid PNG", id="jpeg-named-png"),
    pytest.param(("chart.jpg", PNG, "image/jpeg"), "not a valid JPEG", id="png-named-jpg"),
    pytest.param(("chart.webp", WEBP[:-4], "image/webp"), "not a valid WebP", id="truncated-webp"),
    pytest.param(png(declared="image/jpeg"), "Only PNG, JPEG, or WebP", id="declared-mismatch"),
    pytest.param(png(declared="text/html"), "Only PNG, JPEG, or WebP", id="declared-html"),
    pytest.param(png("chart.gif"), "Only PNG, JPEG, or WebP", id="gif-extension"),
    pytest.param(png("chart"), "Only PNG, JPEG, or WebP", id="no-extension"),
]


@pytest.mark.parametrize("file, message", NOT_IMAGES)
def test_anything_but_a_real_png_jpeg_or_webp_is_rejected(client_as, file, message):
    analyst = client_as("editor")
    bid = create_bite(analyst)

    response = upload(analyst, bid, file)
    assert response.status_code == 400
    assert message in response.text
    assert stored(bid) == []


def test_choosing_no_file_is_a_clear_error(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    response = upload(analyst, bid, ("", b"", "application/octet-stream"))
    assert response.status_code == 400 and "Choose an image" in response.text


def test_an_image_over_5_mb_is_rejected(client_as, monkeypatch):
    assert chart_images.MAX_BYTES == 5 * chart_images.MIB
    monkeypatch.setattr(chart_images, "MAX_BYTES", chart_images.MIB)  # 1 MB, to keep the test fast
    analyst = client_as("editor")
    bid = create_bite(analyst)

    padding = chart_images.MIB - len(PNG) - 20  # tEXt chunk and keyword overhead
    fits = png_bytes(text=b"x" * padding)
    assert len(fits) <= chart_images.MIB
    too_big = png_bytes(text=b"x" * (padding + 1024))  # a real PNG, just too big
    response = upload(analyst, bid, png(content=too_big))
    assert response.status_code == 400
    assert "That image is over the 1 MB limit." in response.text
    assert stored(bid) == []
    assert upload(analyst, bid, png(content=fits)).status_code == 303


def test_an_eleventh_image_is_rejected_but_replacing_one_is_not(client_as):
    assert chart_images.MAX_PER_ITEM == 10
    analyst = client_as("editor")
    bid = create_bite(analyst)
    for i in range(10):
        assert upload(analyst, bid, png(f"chart-{i}.png")).status_code == 303

    response = upload(analyst, bid, png("chart-10.png"))
    assert response.status_code == 400
    assert "already has 10 images" in response.text
    assert len(stored(bid)) == 10
    # Same name: a replacement, not an eleventh.
    assert upload(analyst, bid, png("chart-3.png")).status_code == 303


@pytest.mark.parametrize("uploaded_name, name", [
    ("../../../etc/cron.d/evil.png", "evil.png"),
    ("..\\..\\Windows\\evil.png", "evil.png"),
    ("Fall by Class (2026).PNG", "fall-by-class-2026.png"),
    ("<img src=x onerror=alert(1)>.png", "img-src-x-onerror-alert-1.png"),
    ("Données.png", "donnees.png"),
    ("..png", "chart.png"),
])
def test_the_filename_is_sanitized_before_it_names_anything(client_as, uploaded_name, name):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    assert upload(analyst, bid, png(uploaded_name)).status_code == 303

    assert stored(bid) == [name]
    assert f"<code>{name}</code>" in analyst.get(f"/admin/data-bites/{bid}").text
    files = [p for p in settings.UPLOADS.parent.rglob("*") if p.is_file() and p.suffix == ".png"]
    assert files == [settings.UPLOADS / "images" / "data-bites" / bid / name]


def test_uploading_a_name_the_data_bite_has_replaces_that_image(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    assert upload(analyst, bid, png("chart.png")).status_code == 303
    assert upload(analyst, bid, ("chart.webp", WEBP, "image/webp")).status_code == 303

    revised = png_bytes(b"\x00\x00\xff")
    assert upload(analyst, bid, png("Chart.PNG", revised)).status_code == 303
    assert stored(bid) == ["chart.png", "chart.webp"]
    assert analyst.get(f"/admin/data-bites/{bid}/images/chart.png").content == revised


def test_an_image_can_be_deleted(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    upload(analyst, bid, png("keep.png"))
    upload(analyst, bid, png("drop.png"))

    response = delete_image(analyst, bid, "drop.png")
    assert response.status_code == 303
    assert stored(bid) == ["keep.png"]
    assert "image:drop.png" not in analyst.get(f"/admin/data-bites/{bid}").text
    assert analyst.get(f"/admin/data-bites/{bid}/images/drop.png").status_code == 404
    assert delete_image(analyst, bid, "drop.png").status_code == 404


def test_image_routes_404_for_a_missing_data_bite_or_a_bad_name(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    upload(analyst, bid, png())
    assert upload(analyst, "9999", png()).status_code == 404
    assert analyst.get("/admin/data-bites/9999/images/fall-by-class.png").status_code == 404
    for name in ("..%2F..%2Fcms.db", "%2E%2E", "FALL-BY-CLASS.png", "fall-by-class.svg"):
        assert analyst.get(f"/admin/data-bites/{bid}/images/{name}").status_code == 404, name
        assert delete_image(analyst, bid, name).status_code == 404, name
    assert stored(bid) == ["fall-by-class.png"]


def test_deleting_a_data_bite_deletes_its_images(client_as):
    director = client_as("admin")
    bid = create_bite(director)
    upload(director, bid, png())
    assert post_form(director, f"/admin/data-bites/{bid}/delete", {}).status_code == 303
    assert not (settings.UPLOADS / "images" / "data-bites" / bid).exists()


# Login and CSRF

def test_every_image_route_requires_login(client_as, client):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    upload(analyst, bid, png())

    for method, path in [("get", f"/admin/data-bites/{bid}/images/fall-by-class.png"),
                         ("post", f"/admin/data-bites/{bid}/images"),
                         ("post", f"/admin/data-bites/{bid}/images/fall-by-class.png/delete"),
                         ("post", f"/admin/data-bites/{bid}/preview")]:
        response = getattr(client, method)(path, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/login", path
    assert stored(bid) == ["fall-by-class.png"]


def test_image_forms_carry_csrf_and_a_stripped_post_is_rejected(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    upload(analyst, bid, png())

    page = analyst.get(f"/admin/data-bites/{bid}").text
    for action in (f"/admin/data-bites/{bid}/images", f"/admin/data-bites/{bid}/images/fall-by-class.png/delete"):
        form = re.search(rf'<form[^>]*action="{re.escape(action)}".*?</form>', page, re.S)
        assert form and 'name="csrf_token"' in form.group(0), action

    assert upload(analyst, bid, png("other.png"), with_csrf=False).status_code == 403
    assert delete_image(analyst, bid, "fall-by-class.png", with_csrf=False).status_code == 403
    assert stored(bid) == ["fall-by-class.png"]


# The image: reference

CHART = "Enrollment by class:\n\n![Fall enrollment by class](image:fall-by-class.png)"


def img_tags(html: str) -> list[str]:
    return re.findall(r"<img[^>]*>", html)


def img_attributes(html: str) -> list[dict[str, str | None]]:
    """Each <img>'s attributes, as a browser would parse them."""
    found = []

    class Parser(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "img":
                found.append(dict(attrs))

    Parser().feed(html)
    return found


def test_the_preview_shows_the_draft_image_from_its_preview_site(client_as, client):
    analyst = client_as("editor")
    bid = create_bite(analyst, body=CHART)
    upload(analyst, bid, png())

    # As the published page will (T12): relative, under the preview's <base>.
    expected = '<img src="../images/data-bites/fall-enrollment/fall-by-class.png" alt="Fall enrollment by class">'
    preview = post_form(analyst, f"/admin/data-bites/{bid}/preview", {**BITE, "body": CHART})
    assert preview.status_code == 200 and img_tags(body_of(preview.text)) == [expected]
    served = analyst.get(f"/admin/data-bites/{bid}/preview/images/data-bites/fall-enrollment/fall-by-class.png")
    assert served.status_code == 200 and served.content == PNG
    assert client.get("/images/data-bites/fall-enrollment/fall-by-class.png").status_code == 404
    # The edit page's first render, and its live preview posts to the item's own preview.
    page = analyst.get(f"/admin/data-bites/{bid}").text
    assert img_tags(preview_of(page)) == [expected]
    assert f'"/admin/data-bites/{bid}/preview"' in page


def test_the_public_page_and_the_export_show_the_image_relatively(client_as, client, tmp_path):
    analyst = client_as("editor")
    bid = published_bite(analyst, body=CHART)
    upload(analyst, bid, png())

    expected = '<img src="../images/data-bites/fall-enrollment/fall-by-class.png" alt="Fall enrollment by class">'
    assert img_tags(content_body(client.get("/data-bites/fall-enrollment.html").text)) == [expected]
    served = client.get("/images/data-bites/fall-enrollment/fall-by-class.png")
    assert served.status_code == 200 and served.content == PNG
    assert served.headers["content-type"] == "image/png"
    assert served.headers["x-content-type-options"] == "nosniff"

    site = exported(render_site(tmp_path / "site"))
    assert img_tags(site["data-bites/fall-enrollment.html"].decode()) == [expected]
    assert site["images/data-bites/fall-enrollment/fall-by-class.png"] == PNG


def test_an_unknown_name_renders_nothing(client_as, client):
    analyst = client_as("editor")
    body = "Before ![Missing chart](image:no-such.png) after"
    bid = published_bite(analyst, body=body)
    upload(analyst, bid, png())

    for html in (body_of(post_form(analyst, f"/admin/data-bites/{bid}/preview",
                                   {**BITE, "body": body}).text),
                 preview_of(analyst.get(f"/admin/data-bites/{bid}").text),
                 content_body(client.get("/data-bites/fall-enrollment.html").text)):
        assert "<img" not in html and "no-such" not in html and "Missing chart" not in html, html
        assert "Before" in html and "after" in html
    # The create form's preview knows no item, so no image: resolves.
    assert "<img" not in post_form(analyst, "/admin/data-bites/preview", {**BITE, "body": CHART}).text


def test_other_image_urls_render_nothing(client_as, client):
    """Only a chart image renders an <img> (T14): a hot-linked one would sit
    outside the draft gate this ADR exists for."""
    body = 'A ![Logo](https://example.test/logo.png) ![x](javascript:alert(1)) B'
    published_bite(client_as("editor"), body=body)
    html = content_body(client.get("/data-bites/fall-enrollment.html").text)
    assert img_attributes(html) == []
    # markdown-it never takes javascript: for an image: it stays inert text.
    assert "example.test" not in html and 'src="javascript' not in html and "A" in html


@pytest.mark.parametrize("alt", ['<script>alert(1)</script>', 'x" onerror="alert(1)',
                                 "x\" onerror='alert(1)'"])
def test_script_in_the_description_is_inert(client_as, client, alt):
    analyst = client_as("editor")
    body = f"![{alt}](image:fall-by-class.png)"
    bid = published_bite(analyst, body=body)
    upload(analyst, bid, png())

    for html in (content_body(client.get("/data-bites/fall-enrollment.html").text),
                 post_form(analyst, f"/admin/data-bites/{bid}/preview", {"body": body}).text):
        [attributes] = img_attributes(html)
        assert set(attributes) == {"src", "alt"}, attributes
        assert "<script" not in html


def test_the_edit_page_warns_of_an_empty_description_without_blocking_the_save(client_as):
    analyst = client_as("editor")
    bid = create_bite(analyst)
    upload(analyst, bid, png())

    response = edit_bite(analyst, bid, body="![](image:fall-by-class.png)\n\n![ ](image:other.png)")
    assert response.status_code == 303
    page = analyst.get(f"/admin/data-bites/{bid}").text
    warning = re.search(r'<p class="content-image-warning"[^>]*>(.*?)</p>', page, re.S)
    assert warning, "no warning"
    assert "fall-by-class.png" in warning.group(1) and "other.png" in warning.group(1)

    edit_bite(analyst, bid, body=CHART)
    assert "content-image-warning" not in analyst.get(f"/admin/data-bites/{bid}").text


# The draft gate and the export

def test_a_drafts_images_are_never_public(client_as, client, tmp_path):
    analyst = client_as("editor")
    published_bite(analyst)
    draft = create_bite(analyst, slug="unreleased-bite", title="Unreleased", body=CHART)
    upload(analyst, draft, png("unreleased-chart.png"))

    assert client.get("/images/data-bites/unreleased-bite/unreleased-chart.png").status_code == 404
    site = exported(render_site(tmp_path / "site"))
    assert not any("unreleased" in path for path in site)
    assert all(PNG not in content for content in site.values())


def test_unpublishing_takes_the_images_down(client_as, client, tmp_path):
    analyst = client_as("editor")
    bid = published_bite(analyst, body=CHART)
    upload(analyst, bid, png())
    out = render_site(tmp_path / "site")
    assert (out / "images/data-bites/fall-enrollment/fall-by-class.png").is_file()

    post_form(analyst, f"/admin/data-bites/{bid}/unpublish", {})
    assert client.get("/images/data-bites/fall-enrollment/fall-by-class.png").status_code == 404
    site = exported(render_site(out))
    assert not any(path.startswith("images/") for path in site)


def test_the_public_path_follows_the_slug(client_as, client):
    analyst = client_as("editor")
    bid = published_bite(analyst, body=CHART)
    upload(analyst, bid, png())
    edit_bite(analyst, bid, slug="fall-2026", body=CHART)

    assert client.get("/images/data-bites/fall-enrollment/fall-by-class.png").status_code == 404
    assert client.get("/images/data-bites/fall-2026/fall-by-class.png").content == PNG
    assert 'src="../images/data-bites/fall-2026/fall-by-class.png"' in \
        client.get("/data-bites/fall-2026.html").text


def test_the_export_with_images_is_the_live_public_site(client_as, client, tmp_path):
    analyst = client_as("editor")
    bid = published_bite(analyst, body=CHART + "\n\n![Spring](image:spring.webp)")
    upload(analyst, bid, png())
    upload(analyst, bid, ("spring.webp", WEBP, "image/webp"))
    upload(analyst, bid, png("not-referenced.png"))
    draft = create_bite(analyst, slug="unreleased-bite", body=CHART)
    upload(analyst, draft, png())

    site = exported(render_site(tmp_path / "site"))
    live = {path.removeprefix("/"): content for path, content in crawl(client).items()}
    # An uploaded image the body doesn't place is still exported, as it is served.
    assert live.keys() <= site.keys()
    assert set(site) - set(live) == {"images/data-bites/fall-enrollment/not-referenced.png"}
    assert "images/data-bites/fall-enrollment/spring.webp" in live
    for path, content in live.items():
        assert site[path] == content, path
    assert client.get("/images/data-bites/fall-enrollment/not-referenced.png").content == \
        site["images/data-bites/fall-enrollment/not-referenced.png"]


def test_only_uploaded_images_in_the_folder_count(client_as, client, tmp_path):
    """A half-written upload (.part) or any stray file is never listed, served,
    or exported."""
    analyst = client_as("editor")
    bid = published_bite(analyst)
    upload(analyst, bid, png())
    folder = settings.UPLOADS / "images" / "data-bites" / bid
    for stray in ("tmpab12.part", "notes.txt", "Upper.png", ".DS_Store"):
        (folder / stray).write_bytes(PNG)

    assert "tmpab12" not in analyst.get(f"/admin/data-bites/{bid}").text
    for stray in ("tmpab12.part", "notes.txt", "Upper.png"):
        assert client.get(f"/images/data-bites/fall-enrollment/{stray}").status_code == 404
    site = exported(render_site(tmp_path / "site"))
    assert [p for p in site if p.startswith("images/")] == ["images/data-bites/fall-enrollment/fall-by-class.png"]


def test_a_new_data_bite_never_inherits_images_left_under_its_id(client_as, client):
    """SQLite may give a new Data Bite the id of a deleted one; whatever that
    one left behind is not the new one's."""
    analyst = client_as("editor")
    first = create_bite(analyst)
    leftover = settings.UPLOADS / "images" / "data-bites" / str(int(first) + 1)
    leftover.mkdir(parents=True)
    (leftover / "old-chart.png").write_bytes(PNG)

    bid = published_bite(analyst, slug="spring-survey", body="![Old](image:old-chart.png)")
    assert bid == str(int(first) + 1)
    assert stored(bid) == []
    assert client.get("/images/data-bites/spring-survey/old-chart.png").status_code == 404
    assert "<img" not in content_body(client.get("/data-bites/spring-survey.html").text)
