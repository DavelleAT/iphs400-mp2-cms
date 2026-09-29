"""Markdown to safe HTML: the one pipeline every rendering of user-written
Markdown goes through, the admin preview now and the public export later.

markdown-it-py renders (raw HTML in the Markdown is let through to it), then
nh3 sanitizes, dropping <script>, event-handler attributes, javascript: URLs,
and anything else not on its allowlist. The stored body stays raw; only this
function's output is ever marked safe.
"""
from __future__ import annotations

import nh3
from markdown_it import MarkdownIt
from markupsafe import Markup

_MARKDOWN = MarkdownIt("commonmark").enable("table")


def render_markdown(text: str) -> Markup:
    return Markup(nh3.clean(_MARKDOWN.render(text or "")))
