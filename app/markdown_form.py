"""Editor HTML to Markdown in its standard form (spec #14, ADR-005).

The Editor posts HTML; the body is stored as Markdown. app.editor sanitizes
the posted HTML with nh3 first, and this module turns what is left into
Markdown, written one standard way, with stdlib `html.parser`. It writes only
what the Editor supports: paragraphs, Sections (H2) and Subsections (H3),
bulleted and numbered lists, block quotes, tables, and bold, italic, line
breaks, `https:`/`mailto:` and site links (app.site_links), and chart images
inline. Any other element is let through as its text. Everything the writer typed is escaped, so it
renders as the text it is and never as Markdown syntax.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from html.parser import HTMLParser

from app.content import ContentError
from app.rendering import LINK_SCHEMES
from app.site_links import REFERENCE

# A locked block's token (app.editor): on its own, a top-level paragraph that
# the stored block is put back in place of. The Editor shows the block as an
# empty <div data-locked="locked-<n>">, and it is written as its token.
LOCKED_TOKEN = re.compile(r"locked-(\d+)")
_LOCKED = "data-locked"
_LOCKED_MOVED = ("A part of the body that can't be edited here was moved into a list, "
                 "quote, table, or paragraph. Move it back, or remove it.")
_LOCKED_FORGED = ("A part of the body that can't be edited here was changed. Reload the "
                  "page to get it back.")

# An <img>'s src -> the name of the item's chart image it shows; None for
# any other picture, which is dropped.
ImageName = Callable[[str], "str | None"]


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[_Element | str] = field(default_factory=list)


# Elements with no end tag, which never hold children.
_VOID = {"br", "img", "hr", "input", "meta", "link", "wbr", "col", "source"}
# Elements whose content is never text for the body (nh3 drops them too).
_SKIPPED = {"script", "style", "template", "head", "title"}


class _TreeBuilder(HTMLParser):
    """The HTML as a tree of _Elements. Forgiving: an end tag closes the
    nearest open element of its name, and one with none open is ignored."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Element("root")
        self._open = [self.root]
        self._skipping = 0

    def handle_starttag(self, tag, attrs):
        if self._skipping or tag in _SKIPPED:
            self._skipping += tag not in _VOID
            return
        element = _Element(tag, {name: value or "" for name, value in attrs})
        self._open[-1].children.append(element)
        if tag not in _VOID:
            self._open.append(element)

    def handle_startendtag(self, tag, attrs):
        if not self._skipping and tag not in _SKIPPED:
            self._open[-1].children.append(_Element(tag, {n: v or "" for n, v in attrs}))

    def handle_endtag(self, tag):
        if self._skipping:
            self._skipping -= tag in _SKIPPED or 0
            return
        for depth in range(len(self._open) - 1, 0, -1):
            if self._open[depth].tag == tag:
                del self._open[depth:]
                return

    def handle_data(self, data):
        if not self._skipping:
            self._open[-1].children.append(data)


def _tree(html: str) -> _Element:
    builder = _TreeBuilder()
    builder.feed(html)
    builder.close()
    return builder.root


# Every ASCII punctuation character that can start Markdown syntax anywhere in
# a line. A backslash before any ASCII punctuation is always a literal.
_ESCAPED = re.compile(r"([\\`*_\[\]<>&|#~!])")
_WHITESPACE = re.compile(r"[ \t\n\r\f]+")
# At the start of a line, the syntax that _ESCAPED leaves alone: a list
# marker, a setext underline, or a numbered list's "1." or "1)".
_LINE_START = re.compile(r"^(?:([-+=])|(\d+)([.)]))")
# In a link's destination: what would end it early, and what Markdown would
# otherwise read as an escape or an entity.
_DESTINATION_ENCODED = re.compile(r"[\x00-\x20\x7f<>]")
_DESTINATION_ESCAPED = re.compile(r"([\\()&])")

# A line break, in inline Markdown before it is split into lines. Writer text
# never holds one: _escape turns every newline into a space.
_BREAK = "\n"
_BOLD = {"strong", "b"}
_ITALIC = {"em", "i"}

# The title is the page's only H1, so a pasted H1 becomes a Section; the
# Editor has no level below a Subsection.
_HEADING_LEVELS = {"h1": 2, "h2": 2, "h3": 3, "h4": 3, "h5": 3, "h6": 3}
_LISTS = {"ul", "ol"}
_TABLE_SECTIONS = {"thead", "tbody", "tfoot"}
_CELLS = {"th", "td"}
# Elements that hold blocks, not inline text. Any other element is inline;
# one the Editor doesn't write (a <div> or <section> from a paste) is a
# wrapper, and only what is in it is kept.
_BLOCK_TAGS = {"p", "blockquote", "table", "hr", "pre", "li", "tr", "caption",
               *_LISTS, *_HEADING_LEVELS, *_TABLE_SECTIONS, *_CELLS,
               "div", "section", "article", "header", "footer", "main", "aside", "nav",
               "figure", "figcaption", "address", "details", "summary", "dl", "dt", "dd",
               "center"}
_ALIGNMENTS = {"text-align:left": ":--", "text-align:right": "--:",
               "text-align:center": ":-:"}


def is_link(href: str) -> bool:
    """Whether the Editor keeps a link to `href` (spec #14, "Links"): an
    `https:` or `mailto:` address, or a site link."""
    return href.lower().startswith(LINK_SCHEMES) or REFERENCE.fullmatch(href) is not None


def _escape(text: str) -> str:
    return _ESCAPED.sub(r"\\\1", _WHITESPACE.sub(" ", text))


def _escape_line_start(line: str) -> str:
    return _LINE_START.sub(lambda m: f"\\{m[1]}" if m[1] else f"{m[2]}\\{m[3]}", line)


def _destination(url: str) -> str:
    url = _DESTINATION_ENCODED.sub(lambda m: f"%{ord(m[0]):02X}", url)
    return _DESTINATION_ESCAPED.sub(r"\\\1", url)


def _is_block(node: _Element | str) -> bool:
    return isinstance(node, _Element) and (node.tag in _BLOCK_TAGS or _LOCKED in node.attrs)


def _locked_token(node: _Element) -> str:
    """The token of a locked block as the Editor posts it: empty, since what
    it shows is only for display and what is saved comes from the stored
    body. Anything else was not made by the Editor."""
    token = node.attrs[_LOCKED]
    if not LOCKED_TOKEN.fullmatch(token) or any(
            isinstance(child, _Element) or child.strip() for child in node.children):
        raise ContentError(_LOCKED_FORGED)
    return token


def _indent(text: str, first: str, rest: str) -> str:
    """`text` with `first` before its first line and `rest` before each
    other non-empty line."""
    lines = text.split("\n")
    return "\n".join([first + lines[0], *(rest + line if line else "" for line in lines[1:])])


def _start(ol: _Element) -> int:
    start = ol.attrs.get("start", "1").strip()
    return int(start) if start.isdigit() and len(start) <= 9 else 1


def _items(listing: _Element) -> list[list[_Element | str]]:
    """A list's items, each as its children. A list put straight inside a
    list, not in an item (as some browsers indent), belongs to the item
    before it."""
    items: list[list[_Element | str]] = []
    for child in listing.children:
        if isinstance(child, _Element) and child.tag == "li":
            items.append(list(child.children))
        elif isinstance(child, _Element) or child.strip():
            if not items:
                items.append([])
            items[-1].append(child)
    return items


def _rows(table: _Element) -> list[_Element]:
    """A table's rows, in order, from its sections or straight inside it."""
    rows = []
    for child in table.children:
        if isinstance(child, _Element) and child.tag == "tr":
            rows.append(child)
        elif isinstance(child, _Element) and child.tag in _TABLE_SECTIONS:
            rows.extend(row for row in child.children
                        if isinstance(row, _Element) and row.tag == "tr")
    return rows


def _without_breaks(node: _Element | str) -> _Element | str:
    """A table cell's content with each line break as a space: a Markdown
    table row is one line."""
    if isinstance(node, str):
        return node
    if node.tag == "br":
        return " "
    return _Element(node.tag, node.attrs, [_without_breaks(child) for child in node.children])


@dataclass(frozen=True)
class _Converter:
    image_name: ImageName | None
    # Off in a table cell, where a line never starts a block.
    escape_line_starts: bool = True

    # Inline.

    def inline(self, node: _Element | str, marks: frozenset[str] = frozenset()) -> str:
        """One node's inline Markdown. `marks` are what is already open
        around it ("bold", "italic", "link"), so none is written twice."""
        if isinstance(node, str):
            return _escape(node)
        if _LOCKED in node.attrs:
            raise ContentError(_LOCKED_MOVED)
        if node.tag == "br":
            return _BREAK
        if node.tag == "img":
            return self.image(node)
        if node.tag in _BOLD:
            return self.delimit("**", node, marks, "bold")
        if node.tag in _ITALIC:
            return self.delimit("*", node, marks, "italic")
        if node.tag == "a":
            return self.link(node, marks)
        return self.content(node, marks)

    def content(self, node: _Element, marks: frozenset[str]) -> str:
        return "".join(self.inline(child, marks) for child in node.children)

    def delimit(self, marker: str, node: _Element, marks: frozenset[str], mark: str) -> str:
        content = self.content(node, marks | {mark})
        core = content.strip(" ")
        if mark in marks or not core:
            return content
        # Markdown only opens and closes emphasis next to non-space characters.
        lead = content[:len(content) - len(content.lstrip(" "))]
        trail = content[len(content.rstrip(" ")):]
        return f"{lead}{marker}{core}{marker}{trail}"

    def link(self, node: _Element, marks: frozenset[str]) -> str:
        text = self.content(node, marks | {"link"})
        href = node.attrs.get("href", "").strip()
        if "link" in marks or not text.strip() or not is_link(href):
            return text
        return f"[{text}]({_destination(href)})"

    def image(self, node: _Element) -> str:
        name = self.image_name(node.attrs.get("src", "")) if self.image_name else None
        if name is None:
            return ""
        return f"![{_escape(node.attrs.get('alt', ''))}]({_destination('image:' + name)})"

    def lines(self, nodes: list[_Element | str]) -> list[str]:
        """Inline nodes as lines of Markdown, split at line breaks, with no
        empty line at either end."""
        lines = [line.strip(" ")
                 for line in "".join(self.inline(node) for node in nodes).split(_BREAK)]
        if self.escape_line_starts:
            lines = list(map(_escape_line_start, lines))
        while lines and not lines[-1]:
            lines.pop()
        while lines and not lines[0]:
            lines.pop(0)
        return lines

    # Blocks.

    def blocks(self, element: _Element, *, top: bool = False) -> list[str]:
        """An element's children as Markdown blocks, in order. A run of
        inline children between blocks is a paragraph. Only the `top`, the
        body itself, may hold a locked block."""
        blocks: list[str | None] = []
        run: list[_Element | str] = []
        # The marker of the list just written, if the last block is a list:
        # a list straight after another of the same kind needs the other
        # marker, or Markdown joins the two.
        previous_marker: str | None = None
        for child in [*element.children, None]:
            block = child if isinstance(child, _Element) and _is_block(child) else None
            if child is not None and block is None:
                run.append(child)
                continue
            if run and (paragraph := self.paragraph(run)) is not None:
                blocks.append(paragraph)
                previous_marker = None
            run = []
            if block is None:
                break
            if _LOCKED in block.attrs:
                if not top:
                    raise ContentError(_LOCKED_MOVED)
                blocks.append(_locked_token(block))
                previous_marker = None
                continue
            if block.tag in _LISTS:
                ordered = block.tag == "ol"
                marker = (")" if previous_marker == "." else ".") if ordered else (
                    "*" if previous_marker == "-" else "-")
                if (written := self.list(block, marker)) is not None:
                    blocks.append(written)
                    previous_marker = marker
                continue
            previous_marker = None
            if block.tag == "p":
                blocks.append(self.paragraph(block.children))
            elif block.tag in _HEADING_LEVELS:
                blocks.append(self.heading(_HEADING_LEVELS[block.tag], block.children))
            elif block.tag == "blockquote":
                blocks.append(self.quote(block))
            elif block.tag == "table":
                blocks.append(self.table(block))
            else:
                blocks.extend(self.blocks(block))
        return [written for written in blocks if written is not None]

    def paragraph(self, nodes: list[_Element | str]) -> str | None:
        # A backslash at the end of a line is a line break.
        text = "\\\n".join(self.lines(nodes))
        if LOCKED_TOKEN.fullmatch(text):
            # Writer text, not a token: "locked\-0" renders as "locked-0".
            text = text.replace("-", "\\-", 1)
        return text or None

    def heading(self, level: int, nodes: list[_Element | str]) -> str | None:
        # A heading is one line: a line break in it is a space.
        text = " ".join(self.lines(nodes))
        return f"{'#' * level} {text}" if text else None

    def list(self, listing: _Element, marker: str) -> str | None:
        items = _items(listing)
        if not items:
            return None
        # A list whose items hold paragraphs is loose: blank lines between
        # its items and their blocks, which Markdown renders as <p>s again.
        loose = any(isinstance(node, _Element) and node.tag == "p"
                    for item in items for node in item)
        separator = "\n\n" if loose else "\n"
        number = _start(listing)
        written = []
        for item in items:
            prefix = f"{number}{marker} " if marker in ".)" else f"{marker} "
            number += 1
            content = separator.join(self.blocks(_Element("li", children=item)))
            written.append(_indent(content, prefix, " " * len(prefix)) if content
                           else prefix.rstrip())
        return separator.join(written)

    def quote(self, quote: _Element) -> str | None:
        blocks = self.blocks(quote)
        if not blocks:
            return None
        return "\n".join(f"> {line}" if line else ">"
                         for line in "\n\n".join(blocks).split("\n"))

    def cell(self, cell: _Element) -> str:
        content = _Element(cell.tag, cell.attrs, [_without_breaks(node) for node in cell.children])
        blocks = replace(self, escape_line_starts=False).blocks(content)
        return " ".join(line.strip() for block in blocks for line in block.split("\n")
                        if line.strip())

    def table(self, table: _Element) -> str | None:
        """A table as a Markdown table. Its first row is the header, and each
        column is aligned as its header cell is."""
        rows = [[cell for cell in row.children if isinstance(cell, _Element)
                 and cell.tag in _CELLS] for row in _rows(table)]
        width = max(map(len, rows), default=0)
        if not width:
            return None
        text = [[self.cell(cell) for cell in row] + [""] * (width - len(row)) for row in rows]
        header = rows[0] + [None] * (width - len(rows[0]))
        alignment = [_ALIGNMENTS.get(cell.attrs.get("style", "") if cell else "", "---")
                     for cell in header]
        return "\n".join(f"| {' | '.join(row)} |" for row in [text[0], alignment, *text[1:]])


def to_markdown(html: str, image_name: ImageName | None = None) -> str:
    """Sanitized Editor HTML as standard-form Markdown: blocks separated by
    one blank line, ending in a newline; "" if nothing is left. An <img> is
    kept only as the chart image `image_name` names for its src. A locked
    block is written as its token; ContentError if one is not as the Editor
    shows it, at the top level and empty."""
    blocks = _Converter(image_name).blocks(_tree(html), top=True)
    return "\n\n".join(blocks) + "\n" if blocks else ""
