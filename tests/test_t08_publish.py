"""T08: `cms publish` export (issue #9).

`cms publish` writes the same pages the app serves as the public site, at the
same paths, so an exported page is the live page's bytes, not a second
rendering of it.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app import settings
from app.cli import main
from app.publish import render_site
from tests.conftest import post_form
from tests.test_t03_data_bites import BITE, create_bite
from tests.test_t04_reports import REPORT, report_id
from tests.test_t05_report_files import PDF, pdf, post_with_file, reports_file
from tests.test_t07_public_site import (DRAFT_LEAKS, a_site_with_drafts, crawl,
                                        published_bite, published_report)


def exported(out: Path) -> dict[str, bytes]:
    """Every file under the exported site, by path relative to its root."""
    return {p.relative_to(out).as_posix(): p.read_bytes()
            for p in out.rglob("*") if p.is_file()}


def test_publish_writes_each_published_data_bite_to_its_page(client_as, tmp_path):
    analyst = client_as("editor")
    published_bite(analyst)
    published_bite(analyst, slug="spring-survey", title="Spring survey results")

    site = exported(render_site(tmp_path / "site"))
    assert BITE["title"].encode() in site["data-bites/fall-enrollment.html"]
    assert b"<strong>1,745</strong>" in site["data-bites/fall-enrollment.html"]
    assert b"Spring survey results" in site["data-bites/spring-survey.html"]


def test_publish_writes_each_published_report_and_copies_its_file(client_as, tmp_path):
    director = client_as("admin")
    rid = published_report(director)
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT,
                          pdf("Factbook 2026.pdf")).status_code == 303
    published_report(director, slug="cds", title="Common Data Set 2025-26")

    site = exported(render_site(tmp_path / "site"))
    assert b"<strong>program</strong>" in site["reports/factbook.html"]
    assert b'href="../reports/files/factbook.pdf"' in site["reports/factbook.html"]
    assert site["reports/files/factbook.pdf"] == PDF
    # A Report with no file is a plain Markdown page, with nothing to copy.
    assert b"Common Data Set 2025-26" in site["reports/cds.html"]
    assert b"files/" not in site["reports/cds.html"]
    assert [p for p in site if p.startswith("reports/files/")] == ["reports/files/factbook.pdf"]


def test_a_published_report_whose_stored_file_is_gone_still_publishes(client_as, tmp_path):
    director = client_as("admin")
    rid = published_report(director)
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT, pdf()).status_code == 303
    reports_file(rid).unlink()

    site = exported(render_site(tmp_path / "site"))
    assert b"files/" not in site["reports/factbook.html"]
    assert not any(p.startswith("reports/files/") for p in site)


def test_no_draft_or_draft_file_is_exported(client_as, tmp_path):
    director, analyst = client_as("admin"), client_as("editor")
    a_site_with_drafts(director, analyst)
    # The draft's file really is stored, so its absence below means something.
    assert reports_file(report_id(analyst, "draft-cds")).is_file()

    site = exported(render_site(tmp_path / "site"))
    assert "data-bites/fall-enrollment.html" in site and "reports/files/factbook.pdf" in site
    for path, content in site.items():
        assert "unreleased" not in path and "draft" not in path, path
        for leak in DRAFT_LEAKS:
            assert leak not in content, (path, leak)


def test_publishing_again_removes_what_was_unpublished(client_as, tmp_path):
    director = client_as("admin")
    bite = published_bite(director)
    rid = published_report(director)
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT, pdf()).status_code == 303
    out = render_site(tmp_path / "site")
    assert (out / "reports/files/factbook.pdf").exists()

    post_form(director, f"/admin/data-bites/{bite}/unpublish", {})
    post_form(director, f"/admin/reports/{rid}/unpublish", {})
    site = exported(render_site(out))
    assert "data-bites/fall-enrollment.html" not in site
    assert "reports/factbook.html" not in site and "reports/files/factbook.pdf" not in site
    for content in site.values():
        assert BITE["title"].encode() not in content and REPORT["title"].encode() not in content


def publish_a_full_site(director: TestClient, analyst: TestClient) -> None:
    published_bite(analyst)
    published_bite(analyst, slug="spring-survey", title="Spring survey results")
    create_bite(analyst, slug="unreleased-bite", title="Unreleased enrollment count")
    rid = published_report(director)
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT, pdf()).status_code == 303
    published_report(director, slug="cds", title="Common Data Set 2025-26")


def test_the_export_is_the_live_public_site(client_as, client, tmp_path):
    """Same pages, same paths, same bytes: one rendering, not two. And as
    crawl() follows every link from the home page, failing on a root-absolute
    or broken one, every exported link is relative and resolves."""
    publish_a_full_site(client_as("admin"), client_as("editor"))

    site = exported(render_site(tmp_path / "site"))
    live = {path.removeprefix("/"): content for path, content in crawl(client).items()}
    assert set(site) == set(live)
    for path, content in site.items():
        assert content == live[path], path


def test_script_in_a_body_is_inert_in_the_export(client_as, tmp_path):
    director = client_as("admin")
    payload = 'Hi <script>alert(1)</script> <img src="x.png" onerror="alert(2)">'
    published_bite(director, body=payload)
    published_report(director, body=payload)

    site = exported(render_site(tmp_path / "site"))
    for path in ("data-bites/fall-enrollment.html", "reports/factbook.html"):
        html = site[path].decode()
        assert "Hi" in html and "<script" not in html and "onerror" not in html, path


def test_cms_publish_writes_site(client_as, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(settings, "SITE", tmp_path / "site")
    published_bite(client_as("editor"))

    assert main(["publish"]) == 0
    assert (tmp_path / "site/data-bites/fall-enrollment.html").is_file()
    assert str(tmp_path / "site") in capsys.readouterr().out
