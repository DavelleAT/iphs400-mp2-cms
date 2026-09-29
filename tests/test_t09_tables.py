"""T09: Readable tables in Data Bites and Reports (issue #10)."""
from __future__ import annotations

import re

import pytest

from tests.test_t07_public_site import published_bite, published_report

TABLE = ("| Class | Enrolled | Change |\n"
         "|:------|---------:|:------:|\n"
         "| First-year | 482 | +3% |\n"
         "| Senior | 431 | -1% |\n")

PAGES = [pytest.param(published_bite, "/data-bites/fall-enrollment.html", id="data-bite"),
         pytest.param(published_report, "/reports/factbook.html", id="report")]


def content_body(html: str) -> str:
    """The page's rendered Markdown body, as HTML."""
    match = re.search(r'<div class="content-body">(.*?)</div><!-- /content-body -->', html, re.S)
    assert match, "no content-body wrapper on the page"
    return match.group(1)


@pytest.mark.parametrize("publish, path", PAGES)
def test_a_table_renders_inside_the_content_body(client_as, client, publish, path):
    publish(client_as("admin"), body=f"Enrollment by class:\n\n{TABLE}")

    body = content_body(client.get(path).text)
    # Wrapped, so a wide table scrolls in its wrapper and stays a <table>.
    assert re.search(r'<div class="content-table-scroll">\s*<table>\s*<thead>', body), body
    assert '<td style="text-align:left">First-year</td>' in body


@pytest.mark.parametrize("publish, path", PAGES)
def test_column_alignment_survives_sanitizing(client_as, client, publish, path):
    publish(client_as("admin"), body=TABLE)

    body = content_body(client.get(path).text)
    assert '<th style="text-align:left">Class</th>' in body
    assert '<td style="text-align:right">482</td>' in body
    assert '<td style="text-align:center">+3%</td>' in body


@pytest.mark.parametrize("publish, path", PAGES)
def test_any_other_style_is_still_stripped(client_as, client, publish, path):
    payload = ('<p style="position:fixed;top:0">cover</p>\n\n'
               '<table><tr><td style="text-align:right;background:url(https://evil.test/x);'
               'position:fixed">cell</td></tr></table>\n\n'
               '<span style="text-align:right">span</span>')
    publish(client_as("admin"), body=payload)

    body = content_body(client.get(path).text)
    for leak in ("position", "background", "evil.test", "top:0"):
        assert leak not in body, (leak, body)
    # text-align is kept only on table cells.
    assert '<p style' not in body and '<span style' not in body
    assert '<td style="text-align:right">cell</td>' in body


@pytest.mark.parametrize("publish, path", PAGES)
def test_text_align_keeps_only_the_three_markdown_values(client_as, client, publish, path):
    smuggled = ["text-align:url(https://evil.test/x)", "text-align:expression(alert(1))",
                "text-align:var(--x)", r"text-al\69 gn:right", "text-align:justify"]
    cells = "".join(f'<td style="{value}">c{i}</td>' for i, value in enumerate(smuggled))
    publish(client_as("admin"), body=f"<table><tr>{cells}</tr></table>")

    body = content_body(client.get(path).text)
    assert "style" not in body and "evil.test" not in body, body


def test_the_wrapper_class_is_the_only_class_let_through(client_as, client):
    published_bite(client_as("editor"), body='<p class="content-table-scroll">p</p>'
                   '<div class="content-table-scroll x" id="y">d</div>')

    body = content_body(client.get("/data-bites/fall-enrollment.html").text)
    assert "<p>p</p>" in body and '<div class="content-table-scroll">d</div>' in body


def test_the_stylesheet_styles_tables_only_inside_content_bodies(client):
    css = re.sub(r"/\*.*?\*/", "", client.get("/style.css").text, flags=re.S)
    rules = re.findall(r"([^{}]+)\{", css)
    table_rules = [r.strip() for r in rules if re.search(r"\b(table|th|td)\b", r)]
    assert table_rules, "no table styles"
    for selector in table_rules:
        for part in selector.split(","):
            assert part.strip().startswith(".content-body "), part
    # Borders and padding, a header row, and sideways scrolling in the wrapper.
    assert re.search(r"\.content-body t[hd][^{]*\{[^}]*border", css)
    assert re.search(r"\.content-body t[hd][^{]*\{[^}]*padding", css)
    assert re.search(r"\.content-body th[^{]*\{[^}]*(background|font-weight)", css)
    assert re.search(r"\.content-body \.content-table-scroll\s*\{[^}]*overflow-x:\s*auto", css)
    # The <table> keeps its own display, so it stays a table to screen readers.
    assert not re.search(r"\.content-body table[^{]*\{[^}]*display", css)
