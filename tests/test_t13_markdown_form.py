"""T13: Editor HTML -> standard-form Markdown (app.markdown_form), tested
directly as a pure module (spec #14, "Testing Decisions")."""
from __future__ import annotations

import re
from html import escape, unescape

import pytest

from app.content import ContentError
from app.markdown_form import to_markdown
from app.rendering import render_markdown


def test_paragraphs_and_inline_formatting():
    html = "<p>Fall <strong>headcount</strong> rose <em>slightly</em>.</p><p>Second.</p>"
    assert to_markdown(html) == "Fall **headcount** rose *slightly*.\n\nSecond.\n"


def test_sections_and_subsections():
    html = "<h2>Enrollment</h2><p>Text.</p><h3>By class</h3>"
    assert to_markdown(html) == "## Enrollment\n\nText.\n\n### By class\n"


def test_a_line_break_stays_inside_its_paragraph():
    assert to_markdown("<p>First line<br>second line<br></p>") == "First line\\\nsecond line\n"


# Writer text that looks like Markdown syntax, at the start of a line, in the
# middle, and after a line break.
LOOKS_LIKE_SYNTAX = [
    "# not a heading", "## not a section #", "- not a list", "+ not a list", "* not a list",
    "1. not a list", "12) not a list", "> not a quote", "--- ", "===", "***", "```not code",
    "~~~ not code", "    four spaces", "<script>alert(1)</script>", "<b>not bold</b>",
    "*not italic*", "**not bold**", "_not italic_", "`not code`", "[not](https://a.test)",
    "![not](image:a.png)", "&amp; &copy; &#65;", "a | b | c", "back\\slash\\", "locked-0",
    "https://a.test/x", "a  b\t\tc",
]


@pytest.mark.parametrize("text", LOOKS_LIKE_SYNTAX)
def test_writer_text_renders_as_the_text_typed(text):
    for html in (f"<p>{escape(text)}</p>", f"<p>x<br>{escape(text)}</p>",
                 f"<p>{escape(text)}<br>x</p>", f"<h2>{escape(text)}</h2>"):
        rendered = str(render_markdown(to_markdown(html)))
        assert _text_of(rendered) == _text_of(html), (text, to_markdown(html), rendered)
        assert "<ul" not in rendered and "<ol" not in rendered and "<pre" not in rendered
        assert "<blockquote" not in rendered and "<hr" not in rendered


def _text_of(html: str) -> str:
    """The text a reader sees: tags dropped, entities decoded, runs of
    whitespace as one space."""
    return " ".join(unescape(re.sub(r"<[^>]*>", " ", html)).split())


def test_bulleted_and_numbered_lists():
    html = "<ul><li>One</li><li>Two</li></ul><ol start=\"3\"><li>Three</li><li>Four</li></ol>"
    assert to_markdown(html) == "- One\n- Two\n\n3. Three\n4. Four\n"


def test_a_nested_list_is_indented_under_its_item():
    html = "<ol><li>Fall<ul><li>First-year</li><li>Transfer</li></ul></li><li>Spring</li></ol>"
    assert to_markdown(html) == "1. Fall\n   - First-year\n   - Transfer\n2. Spring\n"


def test_a_list_with_paragraphs_in_its_items_stays_loose():
    html = "<ul><li><p>One</p><p>More on one.</p></li><li><p>Two</p></li></ul>"
    assert to_markdown(html) == "- One\n\n  More on one.\n\n- Two\n"


def test_a_block_quote_holds_its_blocks():
    html = "<blockquote><p>Quoted<br>twice.</p><ul><li>item</li></ul></blockquote>"
    assert to_markdown(html) == "> Quoted\\\n> twice.\n>\n> - item\n"


def test_text_outside_any_paragraph_becomes_one():
    html = "Loose <b>text</b><div>In a div</div><span>after</span><section><p>deep</p></section>"
    assert to_markdown(html) == "Loose **text**\n\nIn a div\n\nafter\n\ndeep\n"


def test_https_and_mailto_links_are_kept():
    html = ('<p><a href="https://example.test/ir?a=1&amp;b=(2) x">IR <em>office</em></a> or '
            '<a href="mailto:ir@example.test">email</a></p>')
    rendered = str(render_markdown(to_markdown(html)))
    assert '<a href="https://example.test/ir?a=1&amp;b=(2)%20x"' in rendered, rendered
    assert "IR <em>office</em></a>" in rendered
    assert '<a href="mailto:ir@example.test"' in rendered


@pytest.mark.parametrize("href", ["http://example.test", "javascript:alert(1)", "/admin",
                                  "reports/cds.html", "data:text/html,x", "", "//evil.test"])
def test_any_other_link_is_kept_as_its_text(href):
    markdown = to_markdown(f'<p>See <a href="{escape(href)}">the CDS</a>.</p>')
    assert markdown == "See the CDS.\n"


def test_a_chart_image_is_written_as_its_image_reference():
    html = ('<p><img src="/admin/data-bites/3/images/fall.png" alt="Fall [by] class">'
            '<img src="https://example.test/logo.png" alt="Logo"></p>')
    name = {"/admin/data-bites/3/images/fall.png": "fall.png"}.get
    assert to_markdown(html, image_name=name) == "![Fall \\[by\\] class](image:fall.png)\n"
    assert to_markdown(html) == ""


def test_a_table_keeps_its_header_and_alignment():
    html = ('<div class="content-table-scroll"><table><thead><tr>'
            '<th style="text-align:left">Class</th><th style="text-align:right">Enrolled</th>'
            '<th style="text-align:center">Change</th><th>Note</th></tr></thead>'
            '<tbody><tr><td>First | year</td><td>482</td><td>+3%</td><td></td></tr>'
            '</tbody></table></div>')
    assert to_markdown(html) == ("| Class | Enrolled | Change | Note |\n"
                                 "| :-- | --: | :-: | --- |\n"
                                 "| First \\| year | 482 | +3% |  |\n")


def test_a_pasted_table_takes_its_first_row_as_the_header():
    html = ("<table><tbody><tr><td>Class</td><td>Enrolled</td></tr>"
            "<tr><td>First-year<br>(new)</td></tr><tr><td>Senior</td><td>431</td><td>x</td></tr>"
            "</tbody></table>")
    assert to_markdown(html) == ("| Class | Enrolled |  |\n| --- | --- | --- |\n"
                                 "| First-year (new) |  |  |\n| Senior | 431 | x |\n")


def test_a_locked_block_is_written_as_its_token():
    html = '<p>a</p><div data-locked="locked-1"></div><p>b</p>'
    assert to_markdown(html) == "a\n\nlocked-1\n\nb\n"


def test_writer_text_that_reads_as_a_token_is_not_one():
    assert to_markdown("<p>locked-0</p>") == "locked\\-0\n"


@pytest.mark.parametrize("html", [
    '<div data-locked="locked-0"><p>forged content</p></div>',
    '<div data-locked="locked-0">x</div>',
    '<div data-locked="locked-0"><img src="x" alt="y"></div>',
    '<blockquote><div data-locked="locked-0"></div></blockquote>',
    '<ul><li><div data-locked="locked-0"></div></li></ul>',
    '<div><div data-locked="locked-0"></div></div>',
    '<div data-locked="locked-x"></div>',
    '<div data-locked="0"></div>',
])
def test_a_forged_or_moved_locked_block_is_refused(html):
    with pytest.raises(ContentError):
        to_markdown(html)
