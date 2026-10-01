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

Charts (ADR-006) are the one thing put in *after* nh3, which would strip
their SVG. Each render takes a fresh nonce once the text is fixed, and each
valid `chart` fence renders as the placeholder `chart-<nonce>-<n>`. After
nh3, each placeholder must be there exactly once, as its own paragraph, and
is swapped for the drawn figure (app.chart_drawing); anything else raises
ChartPlacementError rather than emit a partial page. An invalid fence renders
only CHART_NOT_SHOWN.
"""
from __future__ import annotations

import hashlib
import re
import secrets
from collections.abc import Callable
from html.parser import HTMLParser

import nh3
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markupsafe import Markup

from app import chart_drawing, charts
from app.site_links import TABLES as SITE_LINK_SCHEMES

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
_URL_SCHEMES = {"https", "mailto", "image", *SITE_LINK_SCHEMES}

_MARKDOWN = MarkdownIt("commonmark").enable("table")
_MARKDOWN.add_render_rule("table_open", lambda self, tokens, idx, options, env: (
    f'<div class="{TABLE_SCROLL}">\n' + self.renderToken(tokens, idx, options, env)))
_MARKDOWN.add_render_rule("table_close", lambda self, tokens, idx, options, env: (
    self.renderToken(tokens, idx, options, env) + "</div>\n"))


def _image_text_join(state) -> None:
    """An escaped character or entity in an image's description (`\\[`,
    `&amp;`) is text, as markdown-it's own text_join makes it everywhere but
    there: so the alt keeps it, and the Editor reads it as text."""
    for block in state.tokens:
        images = [token for token in block.children or [] if token.type == "image"]
        for image in images:
            for child in image.children or []:
                if child.type == "text_special":
                    child.type = "text"


_MARKDOWN.core.ruler.push("image_text_join", _image_text_join)

CHART_NOT_SHOWN = "This chart could not be shown."


class ChartPlacementError(RuntimeError):
    """A Chart's placeholder wasn't where the render left it, exactly once."""


def _fence(self, tokens, idx, options, env):
    """A `chart` fence as its placeholder, if it is valid; any other fence
    as markdown-it renders it."""
    token = tokens[idx]
    if not charts.is_chart(token):
        return self.fence(tokens, idx, options, env)
    try:
        chart = charts.parse(token.content)
    except charts.ChartError:
        return f"<p>{CHART_NOT_SHOWN}</p>\n"
    env["charts"].append(chart)
    return f"<p>chart-{env['nonce']}-{len(env['charts']) - 1}</p>\n"


_MARKDOWN.add_render_rule("fence", _fence)


def _placed_charts(html: str, nonce: str, drawn: list[str]) -> str:
    """`html` with each Chart's placeholder replaced by its figure.
    ChartPlacementError unless each placeholder is there exactly once, as
    its own paragraph, and nothing else carries the nonce."""
    if html.count(nonce) != len(drawn):
        raise ChartPlacementError("a Chart's placeholder is missing or repeated")
    for number, figure in enumerate(drawn):
        placeholder = f"<p>chart-{nonce}-{number}</p>"
        if html.count(placeholder) != 1:
            raise ChartPlacementError(f"Chart {number + 1}'s placeholder isn't in place")
        html = html.replace(placeholder, figure)
    if nonce in html:
        raise ChartPlacementError("a Chart's placeholder was left over")
    return html


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
    references resolved by `image_src`, and its site links by `link_href`;
    its Charts drawn."""
    text = text or ""
    # Only after the text is fixed, so nothing in it can know the nonce.
    env = {"nonce": secrets.token_hex(16), "charts": []}
    html = _unlinked(nh3.clean(_MARKDOWN.render(text, env),
                               attributes=_ALLOWED_ATTRIBUTES,
                               attribute_filter=_link_rule(image_src, link_href),
                               url_schemes=_URL_SCHEMES,
                               allowed_classes={"div": {TABLE_SCROLL}}))
    if not env["charts"]:
        return Markup(html)
    # The titles' ids: the same on every render of this text, so the export
    # is the live site byte for byte (ADR-006).
    key = hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]
    drawn = [chart_drawing.draw(chart, key, number)
             for number, chart in enumerate(env["charts"])]
    return Markup(_placed_charts(html, env["nonce"], drawn))


def first_chart(text: str) -> str | None:
    """The first Chart in `text` that stands on its own (not inside a quote
    or a list), as the Markdown of its fence alone, which render_markdown
    draws as the item's page does; None if there is none. For the home
    page's latest Data Bite (spec #22)."""
    for token in parse(text):
        if token.level == 0 and charts.is_chart(token) and token.map:
            start, end = token.map
            # Lines as markdown-it counts them: it reads \r\n and \r as \n.
            lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
            return "\n".join(lines[start:end]) + "\n"
    return None


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
