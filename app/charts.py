"""Charts (spec #14, ADR-006): the `chart` fence's grammar, and the rules
that read its cells as numbers.

A Chart is stored in a body as a fence whose info string is `chart`, holding
one strict JSON object (grammar version 1). Its value cells are kept as the
writer typed them ("1,200", "<10", "n/a") and read here, so labels and the
data table keep the original notation. `parse` reads a block into a Chart or
raises ChartError naming the problem; nothing is drawn from a block that
hasn't passed it (app.chart_drawing).
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from markdown_it.token import Token

INFO = "chart"
VERSION = 1
MAX_BYTES = 32 * 1024
TYPES = ("bar", "hbar", "line")
TYPE_NAMES = {"bar": "bar chart", "hbar": "horizontal bar chart", "line": "line chart"}
# The grammar's keys, in canonical order.
KEYS = ("version", "type", "title", "x_label", "y_label", "unit", "source",
        "categories", "series")
_REQUIRED = {"version", "type", "title", "categories", "series"}
_UNIT_KEYS = ("text", "position")
_SERIES_KEYS = ("name", "values")
# How many categories each type may have.
CATEGORIES = {"bar": (1, 30), "hbar": (1, 30), "line": (2, 60)}
MAX_SERIES = 4
# Each string's length, as (fewest, most) characters.
_LENGTHS = {"title": (1, 120), "x_label": (0, 60), "y_label": (0, 60),
            "source": (0, 200), "unit": (1, 20), "category": (1, 60),
            "series": (1, 40), "value": (0, 20)}
# What a message calls each string.
_NAMES = {"title": "the title", "x_label": "the horizontal axis label",
          "y_label": "the vertical axis label", "source": "the source",
          "unit": "the units"}

PREFIX, SUFFIX = "prefix", "suffix"
MISSING = {"", "—", "n/a"}
_SUPPRESSED = re.compile(r"\*|(?:<|≤|<=)[0-9]+")
_NUMBER = re.compile(r"""
    (?P<sign>[-+])?
    (?P<open>\()?
    (?P<dollar>\$)?
    (?P<digits>[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?P<fraction>\.[0-9]+)?
    (?P<percent>%)?
    (?P<close>\))?
    (?:\ (?P<word>[^\W\d_]+(?:[ -][^\W\d_]+)*))?
""", re.X)


class ChartError(ValueError):
    """A Chart broke a rule; the message is safe to show and names it."""


@dataclass(frozen=True)
class Unit:
    text: str
    position: str  # PREFIX or SUFFIX


DOLLARS = Unit("$", PREFIX)
PERCENT = Unit("%", SUFFIX)


@dataclass(frozen=True)
class Cell:
    """A value cell: the text as typed, and what it reads as."""
    text: str
    kind: str  # "number", "missing", or "suppressed"
    number: float | None = None
    unit: Unit | None = None


@dataclass(frozen=True)
class Series:
    name: str
    values: tuple[str, ...]
    cells: tuple[Cell, ...]


@dataclass(frozen=True)
class Chart:
    type: str
    title: str
    categories: tuple[str, ...]
    series: tuple[Series, ...]
    x_label: str | None = None
    y_label: str | None = None
    # The units as stored; None if the block gives none.
    unit: Unit | None = None
    source: str | None = None

    @property
    def effective_unit(self) -> Unit | None:
        """The units the Chart is drawn in: as stored, or else the first in
        its data."""
        return self.unit or next((cell.unit for cell in self.cells() if cell.unit), None)

    def cells(self) -> Iterable[Cell]:
        """Every value cell, category by category, series across: the order
        the builder's grid reads in."""
        for row in zip(*(series.cells for series in self.series)):
            yield from row

    @property
    def suppressed(self) -> bool:
        return any(cell.kind == "suppressed" for cell in self.cells())

    def canonical(self) -> str:
        """The block in canonical form, with a trailing newline (spec #14)."""
        data: dict = {"version": VERSION, "type": self.type, "title": self.title}
        for key in ("x_label", "y_label"):
            if getattr(self, key) is not None:
                data[key] = getattr(self, key)
        if self.unit:
            data["unit"] = {"text": self.unit.text, "position": self.unit.position}
        if self.source is not None:
            data["source"] = self.source
        data["categories"] = list(self.categories)
        data["series"] = [{"name": series.name, "values": list(series.values)}
                          for series in self.series]
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


# Reading a cell.

def _other_currency(text: str) -> bool:
    return any(unicodedata.category(char) == "Sc" and char != "$" for char in text)


def read_cell(typed: str) -> Cell:
    """A value cell as typed. ValueError, saying why, if it's none of a
    number, a missing value, or a suppressed one."""
    text = typed.strip()
    if text.lower() in MISSING:
        return Cell(text, "missing")
    if _SUPPRESSED.fullmatch(text):
        return Cell(text, "suppressed")
    if _other_currency(text):
        raise ValueError(f"'{text}' is in a currency other than $")
    match = _NUMBER.fullmatch(text)
    if not match or bool(match["open"]) != bool(match["close"]) or (
            match["open"] and match["sign"]):
        raise ValueError(f"'{text}' isn't a number")
    units = [unit for unit, given in ((DOLLARS, match["dollar"]), (PERCENT, match["percent"]))
             if given]
    if match["word"]:
        units.append(Unit(match["word"], SUFFIX))
    if len(units) > 1:
        raise ValueError(f"'{text}' has more than one unit")
    number = float(match["digits"].replace(",", "") + (match["fraction"] or ""))
    if match["sign"] == "-" or match["open"]:
        number = -number
    if not math.isfinite(number):
        raise ValueError(f"'{text}' isn't a number")
    return Cell(text, "number", number, units[0] if units else None)


# Reading a block.

def is_chart(token: Token) -> bool:
    """Whether a block token is a Chart's fence. The info string is trimmed,
    as CommonMark trims it (markdown-it-py doesn't)."""
    return token.type == "fence" and token.info.strip() == INFO


def sources(tokens: Iterable[Token]) -> list[str]:
    """The source of each Chart in a body's block tokens, in order."""
    return [token.content for token in tokens if is_chart(token)]


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    keys = [key for key, _ in pairs]
    for key in keys:
        if keys.count(key) > 1:
            raise ChartError(f"the key '{key}' appears twice")
    return dict(pairs)


def _no_constant(name: str):
    raise ChartError(f"{name} isn't a number a chart can hold")


def _string(value: object, what: str, name: str) -> str:
    """A string of the grammar's, NFC-normalized, its length and its single
    line checked. `what` is its kind in _LENGTHS; `name` how a message calls it."""
    if not isinstance(value, str):
        raise ChartError(f"{name} must be text")
    value = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(char) in ("Cc", "Zl", "Zp") for char in value):
        raise ChartError(f"{name} must be on one line, with no tabs")
    fewest, most = _LENGTHS[what]
    if not fewest <= len(value) <= most or (fewest and not value.strip()):
        raise ChartError(f"{name} must be {fewest} to {most} characters"
                         if fewest else f"{name} must be at most {most} characters")
    return value


def _keys(data: object, allowed: tuple[str, ...], required: set[str], name: str) -> dict:
    if not isinstance(data, dict):
        raise ChartError(f"{name} must be an object")
    for key in data:
        if key not in allowed:
            raise ChartError(f"{name} has an unknown key '{key}'")
    for key in allowed:
        if key in required and key not in data:
            raise ChartError(f"{name} is missing '{key}'")
    return data


def _list(value: object, name: str) -> list:
    if not isinstance(value, list):
        raise ChartError(f"{name} must be a list")
    return value


def _unit(value: object) -> Unit:
    data = _keys(value, _UNIT_KEYS, set(_UNIT_KEYS), "the units")
    text = _string(data["text"], "unit", "the units").strip()
    position = data["position"]
    if position not in (PREFIX, SUFFIX):
        raise ChartError("the units' position must be 'prefix' or 'suffix'")
    if _other_currency(text):
        raise ChartError(f"the units '{text}' are a currency other than $")
    if (position == PREFIX) != (text == "$"):
        raise ChartError("$ goes before the number, and any other units after it")
    return Unit(text, position)


def _series(value: object, categories: tuple[str, ...]) -> Series:
    data = _keys(value, _SERIES_KEYS, set(_SERIES_KEYS), "each series")
    name = _string(data["name"], "series", "a series name")
    values = _list(data["values"], f"series '{name}'s values")
    if len(values) != len(categories):
        raise ChartError(f"series '{name}' has {len(values)} values but "
                         f"{len(categories)} categories")
    typed = tuple(_string(item, "value", f"series '{name}', '{category}'")
                  for item, category in zip(values, categories))
    cells = []
    for text, category in zip(typed, categories):
        try:
            cells.append(read_cell(text))
        except ValueError as exc:
            raise ChartError(f"series '{name}', '{category}': {exc}") from None
    return Series(name, typed, tuple(cells))


def _chart(data: object) -> Chart:
    data = _keys(data, KEYS, _REQUIRED, "the chart")
    version = data["version"]
    if type(version) is not int or version != VERSION:
        raise ChartError(f"its version must be {VERSION}")
    kind = data["type"]
    if kind not in TYPES:
        raise ChartError("its type must be 'bar', 'hbar', or 'line'")
    optional = {key: _string(data[key], key, _NAMES[key])
                for key in ("x_label", "y_label", "source") if key in data}
    categories = tuple(_string(item, "category", "each category")
                       for item in _list(data["categories"], "the categories"))
    fewest, most = CATEGORIES[kind]
    if not fewest <= len(categories) <= most:
        raise ChartError(f"a {TYPE_NAMES[kind]} has {fewest} to {most} categories; "
                         f"this one has {len(categories)}")
    for category in categories:
        if categories.count(category) > 1:
            raise ChartError(f"the category '{category}' appears twice")
    raw_series = _list(data["series"], "the series")
    if not 1 <= len(raw_series) <= MAX_SERIES:
        raise ChartError(f"a chart has 1 to {MAX_SERIES} series; this one has {len(raw_series)}")
    series = tuple(_series(item, categories) for item in raw_series)
    names = [item.name for item in series]
    for name in names:
        if names.count(name) > 1:
            raise ChartError(f"the series name '{name}' appears twice")
    chart = Chart(type=kind, title=_string(data["title"], "title", "the title"),
                  categories=categories, series=series,
                  unit=_unit(data["unit"]) if "unit" in data else None, **optional)
    _one_unit(chart)
    return chart


def _one_unit(chart: Chart) -> None:
    """ChartError naming the first cell whose units aren't the Chart's."""
    unit = chart.effective_unit
    for category_index, category in enumerate(chart.categories):
        for series in chart.series:
            cell = series.cells[category_index]
            if cell.unit and cell.unit != unit:
                raise ChartError(f"series '{series.name}', '{category}': '{cell.text}' is in "
                                 f"{cell.unit.text}, but the chart's units are {unit.text}")


def parse(source: str, number: int = 1) -> Chart:
    """The Chart in a `chart` fence's source, the `number`th in its body.
    ChartError, its message starting "Chart <number>: ", if it breaks a rule."""
    try:
        if len(source.encode("utf-8")) > MAX_BYTES:
            raise ChartError(f"it is larger than {MAX_BYTES // 1024} KB")
        try:
            data = json.loads(source, object_pairs_hook=_no_duplicates,
                              parse_constant=_no_constant)
        except json.JSONDecodeError as exc:
            raise ChartError(f"its data can't be read ({exc.msg}, line {exc.lineno})") from None
        return _chart(data)
    except ChartError as exc:
        raise ChartError(f"Chart {number}: {exc}") from None
    except RecursionError:
        raise ChartError(f"Chart {number}: its data is nested too deeply") from None


def check(tokens: Iterable[Token]) -> None:
    """ChartError for the first Chart in a body's block tokens that breaks a rule."""
    for number, source in enumerate(sources(tokens), start=1):
        parse(source, number)
