"""Admin links are generated from the routes (path_for), never hard-coded, and
still lead where they did."""
from __future__ import annotations

import re

from app import settings
from tests.test_t03_data_bites import create_bite
from tests.test_t04_reports import REPORT, create_report
from tests.test_t05_report_files import pdf, post_with_file


def hrefs(html: str) -> set[str]:
    return set(re.findall(r'href="([^"]+)"', html))


def test_no_template_hard_codes_a_root_absolute_link():
    """What scripts/check_submission.py looks for, in every template."""
    offenders = [str(path.relative_to(settings.TEMPLATES))
                 for path in settings.TEMPLATES.rglob("*.html")
                 if re.search(r'(?:href|src)="/', path.read_text())]
    assert offenders == []


def test_generated_admin_links_lead_where_they_did(client_as):
    director = client_as("admin")
    bid = create_bite(director)
    rid = create_report(director)
    assert post_with_file(director, f"/admin/reports/{rid}", REPORT, pdf()).status_code == 303

    home = director.get("/admin").text
    # A count links to its type's own list, filtered by State, since T24.
    assert {"/admin/content", "/admin/users",
            "/admin/data-bites?status=draft"} <= hrefs(home)
    assert "/admin" in hrefs(director.get("/admin/content").text)
    assert f"/admin/data-bites/{bid}" in hrefs(director.get("/admin/data-bites").text)
    assert "/admin/data-bites" in hrefs(director.get(f"/admin/data-bites/{bid}").text)
    assert f"/admin/reports/{rid}" in hrefs(director.get("/admin/reports").text)
    report_page = hrefs(director.get(f"/admin/reports/{rid}").text)
    assert {"/admin/reports", f"/admin/reports/{rid}/file"} <= report_page
    for path in ("/admin/content", "/admin/users", f"/admin/data-bites/{bid}",
                 f"/admin/reports/{rid}", f"/admin/reports/{rid}/file"):
        assert director.get(path).status_code == 200, path
