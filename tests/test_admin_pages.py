"""Every admin page is styled, and a refused request gets a page, not JSON."""
from __future__ import annotations

import re
from urllib.parse import urljoin

import pytest

from tests.test_t03_data_bites import create_bite


@pytest.mark.parametrize("path", ["/login", "/admin", "/admin/content", "/admin/users",
                                  "/admin/data-bites", "/admin/data-bites/{bid}"])
def test_every_admin_page_links_a_stylesheet_that_loads(client_as, path):
    director = client_as("admin")
    url = f"http://testserver{path.format(bid=create_bite(director))}"
    page = director.get(url)
    [href] = re.findall(r'<link rel="stylesheet" href="([^"]+)"', page.text)
    css = director.get(urljoin(url, href))
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css"), href


def test_an_analyst_refused_a_director_page_sees_a_page(client_as):
    response = client_as("editor").get("/admin/users")
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("text/html")
    assert "Directors only." in response.text
    assert 'href="/admin"' in response.text  # a way back to the dashboard
