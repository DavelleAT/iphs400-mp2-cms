"""Charts (spec #14, ADR-006): the `chart` fence's grammar, and the rules
that read its cells as numbers.

A Chart is stored in a body as a fence whose info string is `chart`, holding
one strict JSON object (grammar version 1). Its value cells are kept as the
writer typed them ("1,200", "<10", "n/a") and read here, so labels and the
data table keep the original notation. `parse` reads a block into a Chart or
raises ChartError naming the problem; nothing is drawn from a block that
hasn't passed it (app.chart_drawing).

Each ChartError names its `field` too, for the builder (T17) to show it by:
"title", "unit", "categories.3", "series.1.name", "series.1.values.3" (series
1's value for category 3), and so on, as the grammar's keys and indexes go;
None for one in no one field. `problems` finds every field's error at once.
Its `short` message leaves out where it is, for beside its cell.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cached_property

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
# A category longer than this suggests a horizontal bar chart (spec #14).
LONG_CATEGORY = 15
# Each string's length, as (fewest, most) characters.
_LENGTHS = {"title": (1, 120), "x_label": (0, 60), "y_label": (0, 60),
            "source": (0, 200), "unit": (1, 20), "category": (1, 60),
            "series": (1, 40), "value": (0, 20)}
# What a message calls each string.
# The labels are named by their axis's role, not its direction: a horizontal
# bar chart's categories run down its side.
_NAMES = {"title": "the title", "x_label": "the category axis label",
          "y_label": "the value axis label", "source": "the source",
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
    """A Chart broke a rule; the message is safe to show and names it, and
    `field` is where it is (see above). `short` is the message less the
    cell it names, if it names one."""

    def __init__(self, message: str, field: str | None = None,
                 short: str | None = None) -> None:
        super().__init__(message)
        self.field = field
        self.short = short or message


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

    @cached_property
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


def _string(value: object, what: str, name: str, field: str | None = None) -> str:
    """A string of the grammar's, NFC-normalized, its length and its single
    line checked. `what` is its kind in _LENGTHS; `name` how a message calls
    it; `field` where it is."""
    if not isinstance(value, str):
        raise ChartError(f"{name} must be text", field)
    value = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(char) in ("Cc", "Zl", "Zp") for char in value):
        raise ChartError(f"{name} must be on one line, with no tabs", field)
    fewest, most = _LENGTHS[what]
    if not fewest <= len(value) <= most or (fewest and not value.strip()):
        raise ChartError(f"{name} must be {fewest} to {most} characters"
                         if fewest else f"{name} must be at most {most} characters", field)
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
    text = _string(data["text"], "unit", "the units", "unit").strip()
    position = data["position"]
    if position not in (PREFIX, SUFFIX):
        raise ChartError("the units' position must be 'prefix' or 'suffix'", "unit")
    if _other_currency(text):
        raise ChartError(f"the units '{text}' are a currency other than $", "unit")
    if (position == PREFIX) != (text == "$"):
        raise ChartError("$ goes before the number, and any other units after it", "unit")
    return Unit(text, position)


def _type(kind: object) -> str:
    if kind not in TYPES:
        raise ChartError("its type must be 'bar', 'hbar', or 'line'", "type")
    return kind


def _category(value: object, index: int) -> str:
    return _string(value, "category", "each category", f"categories.{index}")


def _series_name(value: object, index: int) -> str:
    return _string(value, "series", "a series name", f"series.{index}.name")


def _cell(value: object, name: object, category: object, field: str) -> tuple[str, Cell]:
    """A value cell, as typed and as read, of series `name` and `category`."""
    where = f"series '{name}', '{category}'"
    try:
        typed = _string(value, "value", where, field)
    except ChartError as exc:
        raise ChartError(str(exc), field, str(exc).removeprefix(f"{where} ")) from None
    try:
        return typed, read_cell(typed)
    except ValueError as exc:
        raise ChartError(f"{where}: {exc}", field, str(exc)) from None


def _series(value: object, index: int, categories: tuple[str, ...]) -> Series:
    data = _keys(value, _SERIES_KEYS, set(_SERIES_KEYS), "each series")
    name = _series_name(data["name"], index)
    values = _list(data["values"], f"series '{name}'s values")
    if len(values) != len(categories):
        raise ChartError(f"series '{name}' has {len(values)} values but "
                         f"{len(categories)} categories", f"series.{index}.values")
    typed, cells = zip(*(_cell(item, name, category, f"series.{index}.values.{place}")
                         for place, (item, category) in enumerate(zip(values, categories))))
    return Series(name, typed, cells)


def _second(names: Sequence[str]) -> int | None:
    """Where the first name in `names` that repeats one before it is."""
    return next((index for index, name in enumerate(names) if name in names[:index]), None)


def _chart(data: object) -> Chart:
    data = _keys(data, KEYS, _REQUIRED, "the chart")
    version = data["version"]
    if type(version) is not int or version != VERSION:
        raise ChartError(f"its version must be {VERSION}")
    kind = _type(data["type"])
    optional = {key: _string(data[key], key, _NAMES[key], key)
                for key in ("x_label", "y_label", "source") if key in data}
    categories = tuple(_category(item, index) for index, item
                       in enumerate(_list(data["categories"], "the categories")))
    fewest, most = CATEGORIES[kind]
    if not fewest <= len(categories) <= most:
        raise ChartError(f"a {TYPE_NAMES[kind]} has {fewest} to {most} categories; "
                         f"this one has {len(categories)}", "categories")
    if (twice := _second(categories)) is not None:
        raise ChartError(f"the category '{categories[twice]}' appears twice",
                         f"categories.{twice}")
    raw_series = _list(data["series"], "the series")
    if not 1 <= len(raw_series) <= MAX_SERIES:
        raise ChartError(f"a chart has 1 to {MAX_SERIES} series; this one has {len(raw_series)}",
                         "series")
    series = tuple(_series(item, index, categories) for index, item in enumerate(raw_series))
    if (twice := _second([item.name for item in series])) is not None:
        raise ChartError(f"the series name '{series[twice].name}' appears twice",
                         f"series.{twice}.name")
    chart = Chart(type=kind, title=_string(data["title"], "title", "the title", "title"),
                  categories=categories, series=series,
                  unit=_unit(data["unit"]) if "unit" in data else None, **optional)
    _one_unit(chart)
    return chart


def _one_unit(chart: Chart) -> None:
    """ChartError naming the first cell whose units aren't the Chart's."""
    unit = chart.effective_unit
    for category_index, category in enumerate(chart.categories):
        for series_index, series in enumerate(chart.series):
            cell = series.cells[category_index]
            if cell.unit and cell.unit != unit:
                short = (f"'{cell.text}' is in {cell.unit.text}, but the chart's units "
                         f"are {unit.text}")
                raise ChartError(f"series '{series.name}', '{category}': {short}",
                                 f"series.{series_index}.values.{category_index}", short)


def _load(source: str) -> object:
    """A block's JSON, read strictly. ChartError if it can't be."""
    if len(source.encode("utf-8")) > MAX_BYTES:
        raise ChartError(f"it is larger than {MAX_BYTES // 1024} KB")
    try:
        return json.loads(source, object_pairs_hook=_no_duplicates,
                          parse_constant=_no_constant)
    except json.JSONDecodeError as exc:
        raise ChartError(f"its data can't be read ({exc.msg}, line {exc.lineno})") from None
    except RecursionError:
        raise ChartError("its data is nested too deeply") from None


def parse(source: str, number: int = 1) -> Chart:
    """The Chart in a `chart` fence's source, the `number`th in its body.
    ChartError, its message starting "Chart <number>: ", if it breaks a rule."""
    try:
        return _chart(_load(source))
    except ChartError as exc:
        raise ChartError(f"Chart {number}: {exc}", exc.field, exc.short) from None


# The builder (T17).

def _field_problems(data: object) -> list[ChartError]:
    """The error in each field of `data` that breaks a rule on its own: the
    type, each string, and each value cell, the cells in the grid's order.
    Whatever isn't the shape the grammar has is left for _chart."""
    if not isinstance(data, dict):
        return []
    found: list[ChartError] = []

    def check(rule, *args) -> None:
        try:
            rule(*args)
        except ChartError as exc:
            found.append(exc)

    if "type" in data:
        check(_type, data["type"])
    for key in ("title", "x_label", "y_label", "source"):
        if key in data:
            check(_string, data[key], key, _NAMES[key], key)
    if "unit" in data:
        check(_unit, data["unit"])
    categories = data.get("categories")
    categories = categories if isinstance(categories, list) else []
    for index, category in enumerate(categories):
        check(_category, category, index)
    series = data.get("series")
    series = [item if isinstance(item, dict) else {}
              for item in (series if isinstance(series, list) else [])]
    for index, item in enumerate(series):
        if "name" in item:
            check(_series_name, item["name"], index)
    for place, category in enumerate(categories):
        for index, item in enumerate(series):
            values = item.get("values")
            if isinstance(values, list) and place < len(values):
                check(_cell, values[place], item.get("name"), category,
                      f"series.{index}.values.{place}")
    return found


def problems(source: str) -> list[ChartError]:
    """Every error in a Chart's source, for the builder to show by its
    field: the error in each field that breaks a rule on its own, or if
    there are none, the first rule the whole Chart breaks (as `parse`, less
    its "Chart <number>: "). [] if the Chart is valid."""
    try:
        data = _load(source)
        found = _field_problems(data)
        if not found:
            _chart(data)
    except ChartError as exc:
        return [exc]
    return found


def suggestion(source: str) -> str | None:
    """The type a Chart's source would be better drawn as, if any: "hbar"
    for a vertical bar chart with a category over LONG_CATEGORY characters,
    which would be shortened under its bar. It is only a suggestion."""
    try:
        data = _load(source)
    except ChartError:
        return None
    if not isinstance(data, dict) or data.get("type") != "bar":
        return None
    categories = data.get("categories")
    if isinstance(categories, list) and any(
            isinstance(category, str) and len(category) > LONG_CATEGORY
            for category in categories):
        return "hbar"
    return None


def check(tokens: Iterable[Token]) -> None:
    """ChartError for the first Chart in a body's block tokens that breaks a rule."""
    for number, source in enumerate(sources(tokens), start=1):
        parse(source, number)
