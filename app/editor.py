"""The Editor's server side (spec #14, ADR-005).

The body is stored as Markdown. The Editor shows it as HTML and posts HTML
back, which app.markdown_form turns into Markdown again. This module decides
what the Editor is shown, and what a posted body saves.

**Locked blocks.** A top-level block of the stored body that the Editor can't
represent (a code block, raw HTML, an inline code span, ...) is *locked*: it
is cut out and replaced by the token `locked-<n>` (n: its place among the
body's locked blocks), and the Editor shows its rendered, sanitized HTML,
read-only. Its Markdown source never reaches the browser. On save, each token
is replaced by that block's source from the *stored* body, never from
anything posted.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass

import nh3
from markdown_it.token import Token
from markupsafe import Markup, escape

from app.content import ContentError
from app.markdown_form import LOCKED_TOKEN, ImageName, to_markdown
from app.rendering import (IMAGE_REFERENCE, ImageSrc, parse, render_markdown,
                           table_cell_alignment)

# Block tokens the Editor can represent, and the headings among them.
_SUPPORTED_BLOCKS = {
    "paragraph_open", "paragraph_close", "heading_open", "heading_close", "inline",
    "bullet_list_open", "bullet_list_close", "ordered_list_open", "ordered_list_close",
    "list_item_open", "list_item_close", "blockquote_open", "blockquote_close",
    "table_open", "table_close", "thead_open", "thead_close", "tbody_open", "tbody_close",
    "tr_open", "tr_close", "th_open", "th_close", "td_open", "td_close",
}
_SUPPORTED_HEADINGS = {"h2", "h3"}
_SUPPORTED_INLINE = {"text", "softbreak", "hardbreak", "strong_open", "strong_close",
                     "em_open", "em_close", "link_open", "link_close", "image"}
_LINK_SCHEMES = ("https:", "mailto:")
_NEWLINE = re.compile(r"\r\n?|\n")
_LAST_ENDING = re.compile(r"(?:\r\n?|\n)\Z")


@dataclass(frozen=True)
class Tokenized:
    """A body with each locked block replaced by its token."""
    markdown: str
    # The locked blocks' Markdown source, by token number.
    locked: tuple[str, ...]


def _supported_inline(token: Token) -> bool:
    if token.type not in _SUPPORTED_INLINE:
        return False
    if token.type == "link_open":
        return (str(token.attrGet("href")).lower().startswith(_LINK_SCHEMES)
                and token.attrGet("title") is None)
    if token.type == "image":
        return (str(token.attrGet("src")).startswith(IMAGE_REFERENCE)
                and token.attrGet("title") is None
                and all(map(_supported_inline, token.children or [])))
    return True


def _supported(block: list[Token]) -> bool:
    """Whether the Editor can represent a top-level block, given as its
    tokens: it and everything in it."""
    if [token.type for token in block] == ["paragraph_open", "inline", "paragraph_close"] \
            and LOCKED_TOKEN.fullmatch(block[1].content):
        # Text that reads as a token; locked, so it is never taken for one.
        return False
    for token in block:
        if token.type not in _SUPPORTED_BLOCKS:
            return False
        if token.type == "heading_open" and token.tag not in _SUPPORTED_HEADINGS:
            return False
        if token.type == "inline" and not all(map(_supported_inline, token.children or [])):
            return False
    return True


def _top_level_blocks(tokens: list[Token]) -> list[list[Token]]:
    """The tokens of each top-level block, in order."""
    blocks: list[list[Token]] = []
    depth = 0
    for token in tokens:
        if depth == 0:
            blocks.append([])
        blocks[-1].append(token)
        depth += token.nesting
    return blocks


def _lines(text: str) -> list[str]:
    """`text`'s lines, each with its line ending, numbered as markdown-it
    numbers them (it reads \\r\\n and \\r as \\n)."""
    parts = _NEWLINE.split(text)
    endings = _NEWLINE.findall(text)
    lines = [part + ending for part, ending in zip(parts, endings)]
    return lines + [parts[-1]] if parts[-1] else lines


def _ending(line: str) -> str:
    return line[len(line.rstrip("\r\n")):] or "\n"


def _is_blank(line: str) -> bool:
    return not line.strip()


def tokenize(body: str) -> Tokenized:
    """`body` with each locked block replaced by its token, on a line of its
    own with a blank line either side."""
    lines = _lines(body)
    locked: list[str] = []
    # (first line, line after the last) of each locked block.
    spans = []
    for block in _top_level_blocks(parse(body)):
        if block[0].map and not _supported(block):
            start, end = block[0].map
            while end > start and _is_blank(lines[end - 1]):
                end -= 1
            spans.append((start, end))
    written: list[str] = []
    at = 0
    for start, end in spans:
        written.extend(lines[at:start])
        if written and not _is_blank(written[-1]):
            written.append("\n")
        # The token keeps the line ending of the block's last line, so that
        # putting the block back gives its bytes exactly.
        written.append(f"locked-{len(locked)}{_ending(lines[end - 1])}")
        # Its bytes exactly, less the ending of its last line.
        locked.append(_LAST_ENDING.sub("", "".join(lines[start:end])))
        if end < len(lines) and not _is_blank(lines[end]):
            written.append("\n")
        at = end
    written.extend(lines[at:])
    markdown = "".join(written)
    if spans and spans[-1][1] == len(lines) and not body.endswith(("\n", "\r")):
        markdown = markdown.removesuffix("\n")
    return Tokenized(markdown, tuple(locked))


def _token_paragraphs(markdown: str) -> list[tuple[int, int, int]]:
    """Where `markdown` holds a locked block's token: (first line, line after
    the last, token number) of each top-level paragraph that is one."""
    return [(block[0].map[0], block[0].map[1], int(match[1]))
            for block in _top_level_blocks(parse(markdown))
            if [token.type for token in block] == ["paragraph_open", "inline", "paragraph_close"]
            and (match := LOCKED_TOKEN.fullmatch(block[1].content))]


UNKNOWN_TOKEN = ("A part of the body that can't be edited here is not in the saved "
                 "version. Reload the page to get the saved version back.")
DUPLICATE_TOKEN = ("A part of the body that can't be edited here appears twice. "
                   "Remove one of them.")


def restore(markdown: str, stored: str) -> str:
    """`markdown` with each token replaced by its locked block from `stored`,
    byte for byte. A token that is missing was removed, with its block.
    ContentError for a token `stored` has no block for, or one used twice."""
    locked = tokenize(stored).locked
    found = _token_paragraphs(markdown)
    numbers = [number for _, _, number in found]
    if any(number >= len(locked) for number in numbers):
        raise ContentError(UNKNOWN_TOKEN)
    if len(set(numbers)) != len(numbers):
        raise ContentError(DUPLICATE_TOKEN)
    lines = _lines(markdown)
    for start, end, number in reversed(found):
        lines[start:end] = [locked[number] + _ending(lines[end - 1])]
    return "".join(lines)


# The Editor's HTML.

LOCKED_NOTE = "This part can't be edited here."


def _locked_html(number: int, locked: tuple[str, ...], image_src: ImageSrc | None) -> str:
    """A locked block as the Editor shows it: its rendered, sanitized HTML,
    never its source. Its token is the only thing the Editor posts back."""
    shown = render_markdown(locked[number], image_src) if number < len(locked) else ""
    return (f'<div class="admin-editor-locked" data-locked="locked-{number}">'
            f'<p class="admin-editor-locked-note">{escape(LOCKED_NOTE)}</p>'
            f'<div class="admin-editor-locked-shown">{shown}</div></div>')


def editor_html(markdown: str, stored: str, image_src: ImageSrc | None) -> Markup:
    """What the Editor shows for `markdown`, a tokenized body (usually
    tokenize(stored).markdown), whose tokens are `stored`'s locked blocks.
    Rendered and sanitized as the site renders it, with each chart image's
    src from `image_src`."""
    locked = tokenize(stored).locked
    # Each token is swapped for a placeholder only this call knows, so that
    # nothing the writer typed can render as one.
    nonce = secrets.token_hex(16)
    lines = _lines(markdown)
    for start, end, number in _token_paragraphs(markdown):
        lines[start:end] = [f"locked-{nonce}-{number}{_ending(lines[end - 1])}"]
    html = str(render_markdown("".join(lines), image_src))
    return Markup(re.sub(rf"<p>locked-{nonce}-(\d+)</p>",
                         lambda m: _locked_html(int(m[1]), locked, image_src), html))


# What a post saves.

# The Editor's HTML as nh3 lets it through, before app.markdown_form reads it:
# only what the Editor can represent, and each locked block's token.
_POSTED_TAGS = {"p", "br", "strong", "b", "em", "i", "a", "img", "ul", "ol", "li",
                "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "table", "thead",
                "tbody", "tfoot", "tr", "th", "td", "div", "span"}
_POSTED_ATTRIBUTES = {"a": {"href"}, "img": {"src", "alt"}, "ol": {"start"},
                      "th": {"style"}, "td": {"style"}, "div": {"data-locked"}}


def _sanitized(html: str) -> str:
    return nh3.clean(html, tags=_POSTED_TAGS, attributes=_POSTED_ATTRIBUTES,
                     attribute_filter=table_cell_alignment, link_rel=None)


def _normalized(text: str) -> str:
    return _NEWLINE.sub("\n", text)


@dataclass(frozen=True)
class Posted:
    """A body as an edit form posts it. With the Editor, `body_html` is its
    HTML and `body_dirty` whether the writer changed it. Without (the
    script didn't load), `body_html` is None and `body` is the textarea's
    Markdown: the tokenized body, as the page gave it, perhaps edited."""
    body: str
    body_html: str | None
    body_dirty: bool

    def untouched(self, stored: str) -> bool:
        if self.body_html is not None:
            return not self.body_dirty
        return _normalized(self.body) == _normalized(tokenize(stored).markdown)

    def markdown(self, image_name: ImageName | None) -> str:
        """The body the writer wants, tokenized. ContentError if the Editor's
        HTML has a locked block it didn't make."""
        if self.body_html is None:
            return self.body
        return to_markdown(_sanitized(self.body_html), image_name)


def saved_body(posted: Posted, stored: str | None, image_name: ImageName | None) -> str:
    """The body to save for `posted`, over `stored` (None for a new item). An
    untouched body is `stored` exactly, whatever was posted; any other is the
    posted body, in standard form if from the Editor, with its locked blocks
    put back from `stored`. ContentError if it can't be."""
    if stored is not None and posted.untouched(stored):
        return stored
    return restore(posted.markdown(image_name), stored or "")


def item_base(title: str, slug: str, body: str) -> str:
    """The version of an item an edit form was opened on: a hash of the
    stored title, slug, and body, which the form saves all of."""
    return hashlib.sha256(json.dumps([title, slug, body]).encode()).hexdigest()
