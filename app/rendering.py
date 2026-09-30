"""Markdown to safe HTML: the one pipeline every rendering of user-written
Markdown goes through: the public site, its export, and the Site preview.

markdown-it-py renders (raw HTML in the Markdown is let through to it), then
nh3 sanitizes, dropping <script>, event-handler attributes, javascript: URLs,
and anything else not on its allowlist. The stored body stays raw; only this
function's output is ever marked safe.

Two additions to nh3's allowlist, both for Markdown tables:
  - `style` on a table cell, but only as exactly `text-align:left|right|center`,
    so a column's alignment (`|---:|`) survives and nothing else does.
  - the class TABLE_SCROLL on a <div>: each Markdown table is wrapped in one, so
    a wide table can scroll sideways without restyling the <table> itself.

And the link rule (spec #14, "Links"): every site-owned link and asset is
relative, and only an explicit external link may be absolute. It holds for
every body, however it was saved, raw HTML in it included:
  - an <a> keeps its href only if it is `https:` or `mailto:`, or a site
    link (`report:<ref>`, `data-bite:<ref>`, app.site_links) that the
    caller's `link_href` resolves, to where the page being rendered finds its
    target. Any other <a> is its text.
  - an <img> is kept only for a chart image (ADR-004), `image:<name>`, whose
    URL the caller's `image_src` gives: it knows the item's images and where
    the page finds them. Any other image, or a name it doesn't know, renders
    nothing.
nh3 checks a URL's scheme before its attribute filter sees it, so it lets
these schemes through, and the filter decides. An <a> or <img> the filter
left with no href or src is then taken out (_Unlinked).
"""
from __future__ import annotations

import re
from collections.abc import Callable
from html.parser import HTMLParser

import nh3
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markupsafe import Markup

TABLE_SCROLL = "content-table-scroll"
IMAGE_REFERENCE = "image:"
# The only absolute links a body may have (spec #14, "Links").
LINK_SCHEMES = ("https:", "mailto:")
# A chart image's name -> its URL from the page being rendered; None if the
# item has no image of that name.
ImageSrc = Callable[[str], "str | None"]
# A link's href, if it is not `https:` or `mailto:` -> the href the page
# being rendered links by; None if it is not a site link that resolves.
LinkHref = Callable[[str], "str | None"]
# Every scheme the link rule decides on; nh3 drops any other before it can.
_URL_SCHEMES = {"https", "mailto", "image", "report", "data-bite"}

_MARKDOWN = MarkdownIt("commonmark").enable("table")
_MARKDOWN.add_render_rule("table_open", lambda self, tokens, idx, options, env: (
    f'<div class="{TABLE_SCROLL}">\n' + self.renderToken(tokens, idx, options, env)))
_MARKDOWN.add_render_rule("table_close", lambda self, tokens, idx, options, env: (
    self.renderToken(tokens, idx, options, env) + "</div>\n"))


def _chart_image_name(src: str | None) -> str | None:
    """The name in an `image:<name>` src; None for any other."""
    return src.removeprefix(IMAGE_REFERENCE) if str(src).startswith(IMAGE_REFERENCE) else None

_TABLE_CELLS = ("th", "td")
_ALLOWED_ATTRIBUTES = {**nh3.ALLOWED_ATTRIBUTES,
                       **{cell: nh3.ALLOWED_ATTRIBUTES.get(cell, set()) | {"style"}
                          for cell in _TABLE_CELLS}}
_TEXT_ALIGN = re.compile(r"\s*text-align\s*:\s*(left|right|center)\s*", re.I)


def table_cell_alignment(tag: str, attribute: str, value: str) -> str | None:
    """Keep a table cell's `style` only as its text-align, and only if that is
    one of the three a Markdown table writes; drop every other declaration."""
    if attribute != "style":
        return value
    if tag not in _TABLE_CELLS:
        return None
    for declaration in value.split(";"):
        if match := _TEXT_ALIGN.fullmatch(declaration):
            return f"text-align:{match.group(1).lower()}"
    return None


def _link_rule(image_src: ImageSrc | None, link_href: LinkHref | None):
    """nh3's attribute filter: the link rule, and table_cell_alignment."""
    def keep(tag: str, attribute: str, value: str) -> str | None:
        if tag == "a" and attribute == "href":
            if value.lower().startswith(LINK_SCHEMES):
                return value
            return link_href(value) if link_href else None
        if tag == "img" and attribute == "src":
            name = _chart_image_name(value)
            return image_src(name) if name is not None and image_src else None
        return table_cell_alignment(tag, attribute, value)

    return keep


class _Unlinked(HTMLParser):
    """nh3's output as it is, less each <a> with no href (its content stays)
    and each <img> with no src: those the link rule took them from."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        # Whether each open <a> is kept. nh3 never nests one in another.
        self._anchors: list[bool] = []

    def handle_starttag(self, tag, attrs):
        names = {name for name, _ in attrs}
        if tag == "a":
            self._anchors.append("href" in names)
        if (tag == "a" and "href" not in names) or (tag == "img" and "src" not in names):
            return
        self.out.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag == "a":
            self._anchors.pop()

    def handle_endtag(self, tag):
        if tag == "a" and self._anchors and not self._anchors.pop():
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        self.out.append(data)

    def handle_entityref(self, name):
        self.out.append(f"&{name};")

    def handle_charref(self, name):
        self.out.append(f"&#{name};")

    def handle_comment(self, data):
        self.out.append(f"<!--{data}-->")


def _unlinked(html: str) -> str:
    parser = _Unlinked()
    parser.feed(html)
    parser.close()
    return "".join(parser.out)


def render_markdown(text: str, image_src: ImageSrc | None = None,
                    link_href: LinkHref | None = None) -> Markup:
    """`text` as sanitized HTML, under the link rule: its `image:<name>`
    references resolved by `image_src`, and its site links by `link_href`."""
    return Markup(_unlinked(nh3.clean(_MARKDOWN.render(text or ""),
                                      attributes=_ALLOWED_ATTRIBUTES,
                                      attribute_filter=_link_rule(image_src, link_href),
                                      url_schemes=_URL_SCHEMES,
                                      allowed_classes={"div": {TABLE_SCROLL}})))


def parse(text: str) -> list[Token]:
    """`text`'s block tokens, parsed as render_markdown parses it."""
    return _MARKDOWN.parse(text or "")


def images_without_description(text: str) -> list[str]:
    """The names in `text`'s `image:<name>` references that have no
    description (alt text), in order, for the edit page to warn of: a screen
    reader skips an image with an empty alt."""
    return [name for block in parse(text) for token in block.children or []
            if token.type == "image" and not token.content.strip()
            and (name := _chart_image_name(token.attrGet("src"))) is not None]
