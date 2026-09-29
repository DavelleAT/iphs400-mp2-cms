"""Markdown to safe HTML: the one pipeline every rendering of user-written
Markdown goes through, the admin preview now and the public export later.

markdown-it-py renders (raw HTML in the Markdown is let through to it), then
nh3 sanitizes, dropping <script>, event-handler attributes, javascript: URLs,
and anything else not on its allowlist. The stored body stays raw; only this
function's output is ever marked safe.

Two additions to nh3's allowlist, both for Markdown tables:
  - `style` on a table cell, but only as exactly `text-align:left|right|center`,
    so a column's alignment (`|---:|`) survives and nothing else does.
  - the class TABLE_SCROLL on a <div>: each Markdown table is wrapped in one, so
    a wide table can scroll sideways without restyling the <table> itself.
"""
from __future__ import annotations

import re

import nh3
from markdown_it import MarkdownIt
from markupsafe import Markup

TABLE_SCROLL = "content-table-scroll"

_MARKDOWN = MarkdownIt("commonmark").enable("table")
_MARKDOWN.add_render_rule("table_open", lambda self, tokens, idx, options, env: (
    f'<div class="{TABLE_SCROLL}">\n' + self.renderToken(tokens, idx, options, env)))
_MARKDOWN.add_render_rule("table_close", lambda self, tokens, idx, options, env: (
    self.renderToken(tokens, idx, options, env) + "</div>\n"))

_TABLE_CELLS = ("th", "td")
_ALLOWED_ATTRIBUTES = {**nh3.ALLOWED_ATTRIBUTES,
                       **{cell: nh3.ALLOWED_ATTRIBUTES.get(cell, set()) | {"style"}
                          for cell in _TABLE_CELLS}}
_TEXT_ALIGN = re.compile(r"\s*text-align\s*:\s*(left|right|center)\s*", re.I)


def _cell_alignment(tag: str, attribute: str, value: str) -> str | None:
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


def render_markdown(text: str) -> Markup:
    return Markup(nh3.clean(_MARKDOWN.render(text or ""),
                            attributes=_ALLOWED_ATTRIBUTES,
                            attribute_filter=_cell_alignment,
                            allowed_classes={"div": {TABLE_SCROLL}}))
