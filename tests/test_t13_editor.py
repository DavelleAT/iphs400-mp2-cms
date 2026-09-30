"""T13: the Editor's server side (app.editor): locked blocks, the Editor's
HTML, and what a posted body saves. Tested directly as a pure module; the
routes are tested in test_t13_editor_routes.py."""
from __future__ import annotations

import importlib.util
from html import escape
from html.parser import HTMLParser
from pathlib import Path

import pytest

import test_t09_tables
import test_t10_chart_images
from app import editor
from app.content import ContentError
from app.rendering import render_markdown

_SPEC = importlib.util.spec_from_file_location(
    "seed_demo", Path(__file__).resolve().parents[1] / "scripts" / "seed_demo.py")
seed_demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(seed_demo)

SUPPORTED = [
    "Plain paragraph.",
    "Soft\nwrapped *paragraph* with **bold** and a line  \nbreak\\\nor two.",
    "## Section\n\n### Subsection\n\nSetext section\n---",
    "- one\n- two\n  1. nested\n\n3. three\n4. four",
    "> Quote with a [link](https://example.test) and [mail](mailto:ir@example.test)\n>\n> - list",
    "| a | b |\n|:--|--:|\n| 1 | 2 |",
    "Chart: ![Fall enrollment](image:fall.png)",
    "Autolink <https://example.test>, entity &copy;, escaped \\*star\\*.",
]


@pytest.mark.parametrize("body", SUPPORTED)
def test_supported_blocks_are_not_locked(body):
    assert editor.tokenize(body) == editor.Tokenized(body, ())


UNSUPPORTED = [
    "```\nfenced code\n```",
    "```chart\n{}\n```",
    "    indented code",
    "<div>raw html</div>",
    "# Heading one",
    "#### Heading four",
    "---",
    "Paragraph with `inline code`.",
    "Paragraph with <b>inline html</b>.",
    "A [plain http](http://example.test) link.",
    "A [relative](reports/cds.html) link.",
    'A [titled](https://example.test "Title") link.',
    "![Hot-linked](https://example.test/logo.png)",
    '![Titled](image:fall.png "Title")',
    "- list holding\n\n      code",
    "> quote holding\n>\n> ***",
    "locked-0",
]


@pytest.mark.parametrize("block", UNSUPPORTED)
def test_an_unsupported_block_is_locked_whole(block):
    body = f"Before.\n\n{block}\n\nAfter."
    assert editor.tokenize(body) == editor.Tokenized("Before.\n\nlocked-0\n\nAfter.", (block,))


def test_locked_blocks_are_numbered_in_order_and_kept_apart_from_their_neighbours():
    body = "Intro.\n```\ncode\n```\nOutro with `code`.\n\n## Fine\n"
    assert editor.tokenize(body) == editor.Tokenized(
        "Intro.\n\nlocked-0\n\nlocked-1\n\n## Fine\n", ("```\ncode\n```", "Outro with `code`."))


# What a post saves.

IMAGES = "/admin/data-bites/7/images/"


def editor_image_src(name: str) -> str:
    return IMAGES + name


def editor_image_name(src: str) -> str | None:
    return src.removeprefix(IMAGES) if src.startswith(IMAGES) else None


def site_image_src(name: str) -> str:
    return f"../images/{name}"


def as_posted(html: str) -> str:
    """The Editor's HTML as its script posts it: each locked block emptied,
    since what it shows is only for display."""
    out: list[str] = []
    skipping = 0

    class Emptier(HTMLParser):
        def handle_starttag(self, tag, attrs):
            nonlocal skipping
            if skipping:
                skipping += tag not in VOID
                return
            out.append(self.get_starttag_text())
            if "data-locked" in dict(attrs):
                skipping = 1

        def handle_endtag(self, tag):
            nonlocal skipping
            if skipping:
                skipping -= 1
                if skipping:
                    return
            out.append(f"</{tag}>")

        def handle_data(self, data):
            if not skipping:
                out.append(escape(data, quote=False))

    Emptier(convert_charrefs=True).feed(html)
    return "".join(out)


VOID = {"br", "img", "hr", "input"}


def edited(markdown_body: str) -> str:
    """The Editor's HTML for a stored body, posted back with no change."""
    return as_posted(str(editor.editor_html(editor.tokenize(markdown_body).markdown,
                                            markdown_body, editor_image_src)))


def save(stored: str | None, *, html: str | None = None, dirty: bool = True,
         textarea: str = "") -> str:
    posted = editor.Posted(body=textarea, body_html=html, body_dirty=dirty)
    return editor.saved_body(posted, stored, editor_image_name)


def canonical(html: str) -> list[tuple]:
    """HTML as what a reader gets: its elements, their attributes, and its
    text with whitespace collapsed; whitespace between elements dropped."""
    found: list[tuple] = []

    class Canon(HTMLParser):
        def handle_starttag(self, tag, attrs):
            found.append(("start", tag, sorted(attrs)))

        def handle_endtag(self, tag):
            found.append(("end", tag))

        def handle_data(self, data):
            text = " ".join(data.split())
            if text:
                if found and found[-1][0] == "text":
                    found[-1] = ("text", f"{found[-1][1]} {text}")
                else:
                    found.append(("text", text))

    Canon(convert_charrefs=True).feed(html)
    return found


def rendered(body: str) -> list[tuple]:
    return canonical(str(render_markdown(body, site_image_src)))


FIXTURES = {
    **{f"seed:{slug}": body for _, _, slug, body, _, _ in seed_demo.DEMO_CONTENT},
    "t09:table": test_t09_tables.TABLE,
    "t09:styles": ('<p style="position:fixed;top:0">cover</p>\n\n'
                   '<table><tr><td style="text-align:right;background:url(https://evil.test/x);'
                   'position:fixed">cell</td></tr></table>\n\n'
                   '<span style="text-align:right">span</span>'),
    "t09:wrapper-class": ('<p class="content-table-scroll">p</p>'
                          '<div class="content-table-scroll x" id="y">d</div>'),
    "t10:chart": test_t10_chart_images.CHART,
    "t10:two-charts": test_t10_chart_images.CHART + "\n\n![Spring](image:spring.webp)",
    "t10:missing": "Before ![Missing chart](image:no-such.png) after",
    "t10:other-urls": '![Logo](https://example.test/logo.png) ![x](javascript:alert(1))',
    "t10:hostile-alt": "![x\" onerror='alert(1)'](image:fall-by-class.png)",
    "t10:undescribed": "![](image:fall-by-class.png)\n\n![ ](image:other.png)",
    "t10:old": "![Old](image:old-chart.png)",
    **{f"supported:{i}": body for i, body in enumerate(SUPPORTED)},
    **{f"locked:{i}": f"Before.\n\n{body}\n\nAfter." for i, body in enumerate(UNSUPPORTED)},
}


@pytest.mark.parametrize("body", FIXTURES.values(), ids=FIXTURES.keys())
def test_an_untouched_body_is_kept_byte_for_byte(body):
    for stored in (body, body.replace("\n", "\r\n")):
        assert save(stored, html="<p>anything at all</p>", dirty=False) == stored
        assert save(stored, html=edited(stored), dirty=False) == stored


@pytest.mark.parametrize("body", FIXTURES.values(), ids=FIXTURES.keys())
def test_a_no_change_round_trip_renders_the_same(body):
    saved = save(body, html=edited(body))
    assert rendered(saved) == rendered(body), saved
    # The standard form is stable: saving it again changes nothing.
    assert save(saved, html=edited(saved)) == saved


def test_editing_one_block_changes_only_that_block():
    body = seed_demo.DEMO_CONTENT[0][3]
    html = edited(body).replace("Headcount by class", "Headcount by class and year")
    before, after = rendered(body), rendered(save(body, html=html))
    changed = [i for i, (old, new) in enumerate(zip(before, after)) if old != new]
    assert len(before) == len(after) and len(changed) == 1
    assert after[changed[0]] == ("text", "Headcount by class and year on the census date.")


LOCKED_BODY = ("Intro paragraph.\r\n\r\n```\r\n<script>alert('x')</script>\r\n```\r\n\r\n"
               "Middle paragraph.\r\n\r\nOutro with `inline code`, kept.\r\n")


def test_the_editor_shows_a_locked_block_rendered_never_its_source():
    html = str(editor.editor_html(editor.tokenize(LOCKED_BODY).markdown, LOCKED_BODY,
                                  editor_image_src))
    assert 'data-locked="locked-0"' in html and 'data-locked="locked-1"' in html
    assert "&lt;script&gt;alert(" in html and "<code>inline code</code>" in html
    for source in ("```", "`inline code`", "<script>", "locked-0<", "\r"):
        assert source not in html, source


def test_a_locked_blocks_bytes_survive_edits_around_it():
    html = edited(LOCKED_BODY).replace("Intro paragraph.", "New intro.").replace(
        "Middle paragraph.", "New middle.")
    saved = save(LOCKED_BODY, html=html)
    assert "```\r\n<script>alert('x')</script>\r\n```" in saved
    assert "Outro with `inline code`, kept." in saved
    assert saved.startswith("New intro.\n\n```") and "New middle." in saved


def test_removing_a_locked_block_drops_only_that_block():
    html = edited(LOCKED_BODY).replace('<div class="admin-editor-locked" data-locked="locked-0"></div>', "")
    saved = save(LOCKED_BODY, html=html)
    assert "<script>" not in saved and "```" not in saved
    assert saved == "Intro paragraph.\n\nMiddle paragraph.\n\nOutro with `inline code`, kept.\n"


@pytest.mark.parametrize("html", [
    '<div data-locked="locked-2"></div>',
    '<div data-locked="locked-0"></div><div data-locked="locked-0"></div>',
    '<div data-locked="locked-0"><pre>my own content</pre></div>',
])
def test_an_unknown_duplicated_or_forged_token_is_refused(html):
    with pytest.raises(ContentError):
        save(LOCKED_BODY, html="<p>Intro.</p>" + html)


def test_a_token_on_a_new_item_is_refused():
    with pytest.raises(ContentError):
        save(None, html='<div data-locked="locked-0"></div>')
    with pytest.raises(ContentError):
        save(None, textarea="locked-0")


# The Markdown fallback: the textarea holds the tokenized body.

def test_the_fallback_untouched_keeps_the_stored_body():
    textarea = editor.tokenize(LOCKED_BODY).markdown.replace("\r\n", "\n").replace("\n", "\r\n")
    assert save(LOCKED_BODY, textarea=textarea) == LOCKED_BODY


def test_the_fallback_restores_locked_blocks_around_an_edit():
    textarea = editor.tokenize(LOCKED_BODY).markdown.replace("Middle", "Edited")
    saved = save(LOCKED_BODY, textarea=textarea)
    assert saved == LOCKED_BODY.replace("Middle", "Edited")


def test_the_fallback_saves_markdown_as_posted():
    assert save("Old.", textarea="New *body*\r\n\r\n<b>raw</b>") == "New *body*\r\n\r\n<b>raw</b>"


# Hostile Editor HTML.

HOSTILE = ('<p>a<script>alert(1)</script><img src="x" onerror="alert(2)">'
           '<a href="javascript:alert(3)">js</a><a href="/admin/users">root</a>'
           '<a href="https://ok.test" onclick="alert(4)" style="color:red">ok</a></p>'
           '<p style="position:fixed">fixed</p><iframe src="https://evil.test"></iframe>'
           '<object data="x"></object><svg onload="alert(5)"><text>svg</text></svg>'
           '<math><mi>m</mi></math><form action="https://evil.test"><input value="in"></form>'
           '<style>p{color:red}</style><h1 onclick="x">big</h1><marquee>old</marquee>')


def test_hostile_editor_html_never_survives_to_a_render():
    saved = save("Old.", html=HOSTILE)
    html = str(render_markdown(saved, site_image_src))
    for bad in ("<script", "alert(", "onerror", "onclick", "onload", "style", "javascript:",
                'href="/', "<iframe", "<object", "<svg", "<form", "<input", "<marquee",
                "evil.test", "color:red"):
        assert bad not in html and bad not in saved, (bad, saved)
    assert '<a href="https://ok.test"' in html and "<h2>big</h2>" in html


# The base version.

def test_the_item_base_covers_title_slug_and_body():
    base = editor.item_base("Title", "slug", "Body")
    assert base == editor.item_base("Title", "slug", "Body") and len(base) == 64
    changed = {editor.item_base("Title!", "slug", "Body"), editor.item_base("Title", "slug-2", "Body"),
               editor.item_base("Title", "slug", "Body "), editor.item_base("Titles", "lug", "Body")}
    assert base not in changed and len(changed) == 4
