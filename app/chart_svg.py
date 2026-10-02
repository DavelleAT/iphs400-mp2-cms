"""What a drawn Chart's SVG may contain (spec #14, ADR-006), and the builders
that refuse anything else.

app.chart_drawing's output is inserted *after* nh3 (app.rendering), so it is
safe because of how it's built, not by filtering. Every element goes through
element(), which refuses any element or attribute outside this fixed
vocabulary, and any attribute value that isn't one of:
  - a number formatted here (and checked with math.isfinite),
  - a palette constant (fill, stroke), a fixed class name, or a fixed token,
  - the title's id, `chart-<key>-<n>-title`.
Writer strings (title, labels, units, source, category and series names,
cell text) are only ever text content, escaped by text().
"""
from __future__ import annotations

import math
import re
from html import escape

# The palette (dataviz reference palette, slots 1 to 4, light steps): what a
# Chart shows without a stylesheet. The public site's (static/site.css)
# recolours the series by class, and the console's (static/admin.css) swaps
# in the dark steps in dark mode.
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100")
INK = "#52514e"       # labels, values, legend, axis titles
MUTED = "#898781"     # tick labels
GRID = "#e1e0d9"
BASELINE = "#a3a29b"
SURFACE = "#ffffff"   # the ring around a marker
NONE = "none"         # a line's fill
PALETTE = frozenset({*SERIES, INK, MUTED, GRID, BASELINE, SURFACE, NONE})

ELEMENTS = frozenset({"figure", "figcaption", "svg", "g", "title", "rect", "line", "polyline",
                      "circle", "text", "p", "small", "details", "summary", "table", "thead",
                      "tbody", "tr", "th", "td"})
ATTRIBUTES = frozenset({"class", "viewBox", "role", "aria-labelledby", "aria-hidden", "id", "x",
                        "y", "x1", "y1", "x2", "y2", "width", "height", "cx", "cy", "r",
                        "points", "fill", "stroke", "stroke-width", "text-anchor", "scope"})
SERIES_CLASSES = tuple(f"chart-series-{i}" for i in range(1, len(SERIES) + 1))
LINE_CLASSES = tuple(f"chart-line-{i}" for i in range(1, len(SERIES) + 1))
MARKER_CLASSES = tuple(f"chart-marker-{i}" for i in range(1, len(SERIES) + 1))
CLASSES = frozenset({"chart-figure", "chart-title", "chart-svg", "chart-svg-phone", "chart-grid", "chart-baseline",
                     "chart-tick", "chart-category", "chart-value", "chart-axis-title",
                     "chart-legend", "chart-note", "chart-source", "chart-data",
                     *SERIES_CLASSES, *LINE_CLASSES, *MARKER_CLASSES})
_NUMERIC = frozenset({"x", "y", "x1", "y1", "x2", "y2", "width", "height", "cx", "cy", "r",
                      "stroke-width"})
_TOKENS = {"role": {"img"}, "text-anchor": {"start", "middle", "end"}, "scope": {"row", "col"},
           "aria-hidden": {"true"}}
TITLE_ID = re.compile(r"chart-[0-9a-f]{32}-[0-9]+-title")


class ChartDrawError(RuntimeError):
    """The drawing broke its own rules: a bug, never a writer's mistake."""


def number(value: float) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ChartDrawError(f"not a finite number: {value!r}")
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _value(name: str, value: object) -> str:
    """An attribute's value, if the vocabulary allows it."""
    if name == "viewBox":
        return " ".join(map(number, value))
    if name == "points":
        return " ".join(f"{number(x)},{number(y)}" for x, y in value)
    if name in _NUMERIC:
        return number(value)
    allowed = (name == "class" and value in CLASSES
               or name in ("fill", "stroke") and value in PALETTE
               or name in ("id", "aria-labelledby") and TITLE_ID.fullmatch(str(value))
               or value in _TOKENS.get(name, ()))
    if not allowed:
        raise ChartDrawError(f"{name}={value!r} is not in the vocabulary")
    return str(value)


def element(name: str, attributes: dict | None = None, *content: str) -> str:
    """An element of the vocabulary. `content` is elements from here, or
    text(): never a writer's string as it is."""
    if name not in ELEMENTS:
        raise ChartDrawError(f"<{name}> is not in the vocabulary")
    parts = []
    for key, value in (attributes or {}).items():
        if key not in ATTRIBUTES:
            raise ChartDrawError(f"{key} is not in the vocabulary")
        parts.append(f' {key}="{_value(key, value)}"')
    return f"<{name}{''.join(parts)}>{''.join(content)}</{name}>"


def text(text: str) -> str:
    return escape(text, quote=True)
