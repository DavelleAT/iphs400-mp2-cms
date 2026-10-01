"""T05: Report file attachment (issue #6)."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import db, settings, uploads, users
from app.publish import render_site
from tests.conftest import DEMO_USERS, csrf_from, post_form, second_analyst, stored_slugs
from tests.test_t04_reports import REPORT, report_id, report_row

# A minimal, well-formed PDF: the header and the end-of-file marker are what
# make it a PDF, whatever the upload's filename says.
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
       b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
       b"trailer<</Root 1 0 R>>\n%%EOF\n")


# The edit page's attached-file line when there is none (T23: in the form, under
# the Editor).
NO_FILE = '<p class="field-console-attached">None</p>'


def post_with_file(c: TestClient, path: str, data: dict, file=None, *, with_csrf=True):
    """POST a multipart admin form. `file` is (filename, bytes, content type);
    None sends the form with no file chosen, as a browser does."""
    if with_csrf:
        data = {**data, "csrf_token": csrf_from(c.get("/admin").text)}
    file = file or ("", b"", "application/octet-stream")
    return c.post(path, data=data, files={"file": file}, follow_redirects=False)


def reports_file(rid: str):
    return settings.UPLOADS / "reports" / f"{rid}.pdf"


def pdf(name: str = "factbook-2026.pdf", content: bytes = PDF):
    return (name, content, "application/pdf")


def test_analyst_attaches_a_pdf_when_creating_a_draft_report(client_as):
    analyst = client_as("editor")
    response = post_with_file(analyst, "/admin/reports", REPORT, pdf())
    assert response.status_code == 303, response.text

    rid = report_id(analyst, REPORT["slug"])
    page = analyst.get(f"/admin/reports/{rid}").text
    assert "factbook-2026.pdf" in page
    download = analyst.get(f"/admin/reports/{rid}/file")
    assert download.status_code == 200
    assert download.content == PDF
    assert download.headers["content-type"] == "application/pdf"


NOT_PDFS = [
    pytest.param(pdf(content=b"<script>alert(1)</script>"), "not a valid PDF", id="html-named-pdf"),
    pytest.param(pdf(content=b"MZ\x90\x00" + b"\x00" * 64), "not a valid PDF", id="exe-named-pdf"),
    pytest.param(pdf(content=b""), "not a valid PDF", id="empty"),
    pytest.param(pdf(content=b"%PDF-1.4\nno end marker"), "not a valid PDF", id="truncated"),
    pytest.param(("factbook.txt", PDF, "application/pdf"), "Only PDF files", id="wrong-extension"),
    pytest.param(("factbook", PDF, "application/pdf"), "Only PDF files", id="no-extension"),
    pytest.param(("factbook.pdf", PDF, "text/html"), "Only PDF files", id="declared-html"),
]


@pytest.mark.parametrize("upload, message", NOT_PDFS)
def test_a_non_pdf_is_rejected_and_nothing_is_saved(client_as, upload, message):
    analyst = client_as("editor")
    response = post_with_file(analyst, "/admin/reports", REPORT, upload)
    assert response.status_code == 400
    assert message in response.text
    assert REPORT["slug"] not in stored_slugs("reports")
    assert not list(settings.UPLOADS.rglob("*.*"))


def test_a_file_over_the_size_cap_is_rejected_with_a_clear_error(client_as, monkeypatch):
    monkeypatch.setattr(uploads, "MAX_BYTES", uploads.MIB)  # 1 MB, to keep the test fast
    analyst = client_as("editor")
    padded = PDF[:-6] + b" " * uploads.MIB + b"%%EOF\n"  # a real PDF, just too big
    response = post_with_file(analyst, "/admin/reports", REPORT, pdf(content=padded))
    assert response.status_code == 400
    assert "That file is over the 1 MB limit." in response.text
    assert REPORT["slug"] not in stored_slugs("reports")

    # One just under the cap is fine.
    fits = PDF[:-6] + b" " * (uploads.MIB - len(PDF)) + b"%%EOF\n"
    assert len(fits) <= uploads.MIB
    assert post_with_file(analyst, "/admin/reports", REPORT, pdf(content=fits)).status_code == 303


@pytest.mark.parametrize("uploaded_name, shown_name", [
    ("../../../etc/cron.d/evil.pdf", "evil.pdf"),
    ("..\\..\\Windows\\evil.pdf", "evil.pdf"),
    ("Fact'book <img src=x onerror=alert(1)>.PDF", "Fact-book-img-src-x-onerror-alert-1.pdf"),
    ("Données 2026 (final).pdf", "Donnees-2026-final.pdf"),
    ("..pdf", "report.pdf"),
])
def test_the_uploaded_filename_is_sanitized(client_as, tmp_path, uploaded_name, shown_name):
    analyst = client_as("editor")
    upload = (uploaded_name, PDF, "application/pdf")
    assert post_with_file(analyst, "/admin/reports", REPORT, upload).status_code == 303

    rid = report_id(analyst, REPORT["slug"])
    page = analyst.get(f"/admin/reports/{rid}").text
    assert f">{shown_name}</a>" in page
    download = analyst.get(f"/admin/reports/{rid}/file")
    assert f'filename="{shown_name}"' in download.headers["content-disposition"]
    # Stored under the uploads directory, named by the Report's id only.
    stored = [p for p in tmp_path.rglob("*") if p.is_file() and p.suffix == ".pdf"]
    assert stored == [settings.UPLOADS / "reports" / f"{rid}.pdf"]


REVISED = PDF.replace(b"%PDF-1.4", b"%PDF-1.7")  # a different, still-valid PDF


def draft_with_file(c: TestClient) -> str:
    assert post_with_file(c, "/admin/reports", REPORT, pdf()).status_code == 303
    return report_id(c, REPORT["slug"])


def test_any_analyst_replaces_and_removes_the_file_on_a_draft_report(client_as):
    riley = second_analyst(client_as("admin"))
    rid = draft_with_file(riley)
    analyst = client_as("editor")  # not the author

    response = post_with_file(analyst, f"/admin/reports/{rid}", REPORT,
                              pdf("factbook-v2.pdf", REVISED))
    assert response.status_code == 303
    assert "factbook-v2.pdf" in analyst.get(f"/admin/reports/{rid}").text
    assert analyst.get(f"/admin/reports/{rid}/file").content == REVISED

    assert post_form(analyst, f"/admin/reports/{rid}/file/delete", {}).status_code == 303
    page = analyst.get(f"/admin/reports/{rid}").text
    assert NO_FILE in page and "factbook-v2.pdf" not in page
    assert analyst.get(f"/admin/reports/{rid}/file").status_code == 404
    assert not reports_file(rid).exists()


def test_saving_a_draft_with_no_file_chosen_keeps_its_file(client_as):
    analyst = client_as("editor")
    rid = draft_with_file(analyst)
    edited = {**REPORT, "body": "Revised body."}
    assert post_with_file(analyst, f"/admin/reports/{rid}", edited).status_code == 303
    assert analyst.get(f"/admin/reports/{rid}/file").content == PDF


def test_an_invalid_file_on_edit_changes_nothing(client_as):
    analyst = client_as("editor")
    rid = draft_with_file(analyst)
    response = post_with_file(analyst, f"/admin/reports/{rid}",
                              {**REPORT, "title": "Changed title"},
                              pdf(content=b"not a pdf"))
    assert response.status_code == 400
    assert "not a valid PDF" in response.text
    assert "Changed title" not in analyst.get("/admin/reports").text
    assert analyst.get(f"/admin/reports/{rid}/file").content == PDF


def test_published_report_file_is_locked_against_analyst_replace_and_remove(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = draft_with_file(analyst)
    assert post_form(director, f"/admin/reports/{rid}/publish", {}).status_code == 303

    replace = post_with_file(analyst, f"/admin/reports/{rid}", REPORT,
                             pdf("tampered.pdf", REVISED))
    assert replace.status_code == 403
    assert post_form(analyst, f"/admin/reports/{rid}/file/delete", {}).status_code == 403

    page = analyst.get(f"/admin/reports/{rid}").text
    assert "factbook-2026.pdf" in page and "tampered.pdf" not in page
    assert "/file/delete" not in page and 'type="file"' not in page
    assert analyst.get(f"/admin/reports/{rid}/file").content == PDF


def test_director_replaces_and_removes_the_file_on_a_published_report(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    rid = draft_with_file(analyst)
    assert post_form(director, f"/admin/reports/{rid}/publish", {}).status_code == 303

    response = post_with_file(director, f"/admin/reports/{rid}", REPORT,
                              pdf("factbook-corrected.pdf", REVISED))
    assert response.status_code == 303
    assert director.get(f"/admin/reports/{rid}/file").content == REVISED
    assert "Published" in report_row(director, REPORT["slug"])

    assert post_form(director, f"/admin/reports/{rid}/file/delete", {}).status_code == 303
    assert director.get(f"/admin/reports/{rid}/file").status_code == 404


def test_director_attaches_a_file_to_a_published_report_that_had_none(client_as):
    director, analyst = client_as("admin"), client_as("editor")
    assert post_with_file(analyst, "/admin/reports", REPORT).status_code == 303
    rid = report_id(analyst, REPORT["slug"])
    assert post_form(director, f"/admin/reports/{rid}/publish", {}).status_code == 303
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT, pdf()).status_code == 303
    assert director.get(f"/admin/reports/{rid}/file").content == PDF


def test_deleting_a_report_deletes_its_file(client_as):
    director = client_as("admin")
    rid = draft_with_file(director)
    assert reports_file(rid).exists()
    assert post_form(director, f"/admin/reports/{rid}/delete", {}).status_code == 303
    assert not reports_file(rid).exists()


def test_a_draft_reports_file_never_appears_in_public_output(client_as, client, tmp_path):
    analyst = client_as("editor")
    upload = pdf("unreleased-enrollment.pdf", PDF + b"% UNRELEASED-MARKER\n%%EOF\n")
    assert post_with_file(analyst, "/admin/reports", REPORT, upload).status_code == 303

    home = client.get("/").text
    assert "unreleased-enrollment" not in home and "/file" not in home

    out = render_site(tmp_path / "site")
    for path in out.rglob("*"):
        assert path.suffix != ".pdf", path
        if path.is_file():
            content = path.read_bytes()
            assert b"UNRELEASED-MARKER" not in content and b"unreleased-enrollment" not in content
    # And the upload itself lives outside site/.
    assert settings.SITE not in reports_file(report_id(analyst, REPORT["slug"])).parents


def test_a_report_with_no_file_works_end_to_end(client_as, client, tmp_path):
    director, analyst = client_as("admin"), client_as("editor")
    assert post_with_file(analyst, "/admin/reports", REPORT).status_code == 303
    rid = report_id(analyst, REPORT["slug"])
    page = analyst.get(f"/admin/reports/{rid}").text
    assert NO_FILE in page and "/file/delete" not in page
    assert analyst.get(f"/admin/reports/{rid}/file").status_code == 404

    edited = {**REPORT, "body": "Revised body."}
    assert post_with_file(analyst, f"/admin/reports/{rid}", edited).status_code == 303
    # Removing a file that isn't there is harmless.
    assert post_form(analyst, f"/admin/reports/{rid}/file/delete", {}).status_code == 303
    assert post_form(director, f"/admin/reports/{rid}/publish", {}).status_code == 303

    assert "Published" in report_row(director, REPORT["slug"])
    assert REPORT["title"] in client.get("/").text
    assert (render_site(tmp_path / "site") / "index.html").exists()


def test_the_file_routes_404_for_a_missing_report(client_as):
    director = client_as("admin")
    assert director.get("/admin/reports/999/file").status_code == 404
    assert post_form(director, "/admin/reports/999/file/delete", {}).status_code == 404


FILE_ROUTES = [
    ("GET", "/admin/reports/{id}/file"),
    ("POST", "/admin/reports/{id}/file/delete"),
    ("POST", "/admin/reports/{id}"),  # the edit form, now carrying a file
    ("POST", "/admin/reports"),       # the create form, likewise
]


@pytest.mark.parametrize("method, path", FILE_ROUTES)
def test_anonymous_visitor_is_redirected_from_every_file_route(client, client_as, method, path):
    rid = draft_with_file(client_as("editor"))
    files = {"file": pdf("tampered.pdf", REVISED)} if method == "POST" else None
    response = client.request(method, path.format(id=rid),
                              data={**REPORT, "slug": "new-slug"} if files else None,
                              files=files, follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].endswith("/login")
    assert reports_file(rid).read_bytes() == PDF


@pytest.mark.parametrize("method, path", [r for r in FILE_ROUTES if r[0] == "POST"])
def test_file_posts_without_csrf_token_are_rejected(client_as, method, path):
    director = client_as("admin")
    rid = draft_with_file(director)
    director.get("/admin")  # the session has a token; the POST just omits it
    response = post_with_file(director, path.format(id=rid), {**REPORT, "slug": "new-slug"},
                              pdf("tampered.pdf", REVISED), with_csrf=False)
    assert response.status_code == 403
    assert reports_file(rid).read_bytes() == PDF
    assert "new-slug" not in stored_slugs("reports")


PRE_T05_SCHEMA = """
CREATE TABLE users (
    id            INTEGER PRIMARY KEY,
    email         TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    name          TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('admin', 'editor')),
    password_hash TEXT    NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE reports (
    id         INTEGER PRIMARY KEY,
    title      TEXT    NOT NULL,
    slug       TEXT    NOT NULL UNIQUE,
    body       TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
    author_id  INTEGER NOT NULL REFERENCES users (id),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""


def test_an_existing_database_gains_the_file_column(tmp_path, monkeypatch, client_as):
    """A cms.db made before T05 has a reports table without file_name."""
    old = tmp_path / "old.db"
    with sqlite3.connect(old) as conn:
        conn.executescript(PRE_T05_SCHEMA)
        conn.execute("INSERT INTO users (email, name, role, password_hash)"
                     " VALUES ('x@example.test', 'X', 'admin', 'x')")
        conn.execute("INSERT INTO reports (title, slug, body, author_id)"
                     " VALUES ('Old CDS', 'old-cds', 'Body.', 1)")
        assert "file_name" not in {r[1] for r in conn.execute("PRAGMA table_info(reports)")}
    monkeypatch.setattr(settings, "DATABASE_PATH", old)
    db.init_db()
    for role, user in DEMO_USERS.items():
        users.create_user(user["email"], user["password"], role)

    analyst = client_as("editor")
    rid = report_id(analyst, "old-cds")
    assert NO_FILE in analyst.get(f"/admin/reports/{rid}").text
    assert post_with_file(analyst, f"/admin/reports/{rid}",
                          {"title": "Old CDS", "slug": "old-cds", "body": "Body."},
                          pdf()).status_code == 303
    assert analyst.get(f"/admin/reports/{rid}/file").content == PDF
    db.init_db()  # running it again is harmless


def test_a_file_missing_from_disk_is_404_not_a_crash(client_as):
    """e.g. uploads/ was wiped but cms.db kept."""
    analyst = client_as("editor")
    rid = draft_with_file(analyst)
    reports_file(rid).unlink()
    assert analyst.get(f"/admin/reports/{rid}/file").status_code == 404


def test_a_failed_file_write_saves_nothing(client_as, monkeypatch, tmp_path):
    analyst = client_as("editor")
    rid = draft_with_file(analyst)
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    monkeypatch.setattr(settings, "UPLOADS", blocker)  # every write now fails

    with pytest.raises(OSError):
        post_with_file(analyst, f"/admin/reports/{rid}",
                       {**REPORT, "title": "Half-saved title"}, pdf())
    with pytest.raises(OSError):
        post_with_file(analyst, "/admin/reports",
                       {**REPORT, "slug": "half-saved"}, pdf())

    listing = analyst.get("/admin/reports").text
    assert "Half-saved title" not in listing and "half-saved" not in stored_slugs("reports")
