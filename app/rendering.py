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

And one addition to Markdown, for chart images (ADR-004): an image whose URL
is `image:<name>` gets its URL from the `image_src` the caller passes, which
knows the item's images and where the page being rendered finds them. A name
it doesn't know, or no `image_src`, renders nothing. Any other image URL is
left to the sanitizer.
"""
from __future__ import annotations

import re
from collections.abc import Callable

import nh3
from markdown_it import MarkdownIt
from markdown_it.token import Token
from markupsafe import Markup

TABLE_SCROLL = "content-table-scroll"
IMAGE_REFERENCE = "image:"
# A chart image's name -> its URL from the page being rendered; None if the
# item has no image of that name.
ImageSrc = Callable[[str], "str | None"]

_MARKDOWN = MarkdownIt("commonmark").enable("table")
_MARKDOWN.add_render_rule("table_open", lambda self, tokens, idx, options, env: (
    f'<div class="{TABLE_SCROLL}">\n' + self.renderToken(tokens, idx, options, env)))
_MARKDOWN.add_render_rule("table_close", lambda self, tokens, idx, options, env: (
    self.renderToken(tokens, idx, options, env) + "</div>\n"))


def _chart_image_name(token) -> str | None:
    """The name in an `image:<name>` image token; None for any other image."""
    src = token.attrGet("src")
    return src.removeprefix(IMAGE_REFERENCE) if str(src).startswith(IMAGE_REFERENCE) else None


def _render_image(self, tokens, idx, options, env):
    name = _chart_image_name(tokens[idx])
    if name is not None:
        url = env["image_src"](name) if env.get("image_src") else None
        if url is None:
            return ""
        tokens[idx].attrSet("src", url)
    return self.image(tokens, idx, options, env)


_MARKDOWN.add_render_rule("image", _render_image)

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


def render_markdown(text: str, image_src: ImageSrc | None = None) -> Markup:
    """`text` as sanitized HTML, its `image:<name>` references resolved by
    `image_src`."""
    return Markup(nh3.clean(_MARKDOWN.render(text or "", {"image_src": image_src}),
                            attributes=_ALLOWED_ATTRIBUTES,
                            attribute_filter=table_cell_alignment,
                            allowed_classes={"div": {TABLE_SCROLL}}))


def parse(text: str) -> list[Token]:
    """`text`'s block tokens, parsed as render_markdown parses it."""
    return _MARKDOWN.parse(text or "")


def images_without_description(text: str) -> list[str]:
    """The names in `text`'s `image:<name>` references that have no
    description (alt text), in order, for the edit page to warn of: a screen
    reader skips an image with an empty alt."""
    return [name for block in parse(text) for token in block.children or []
            if token.type == "image" and not token.content.strip()
            and (name := _chart_image_name(token)) is not None]
