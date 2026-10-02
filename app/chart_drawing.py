"""Drawing a Chart (spec #14, ADR-006): a parsed app.charts.Chart as an
inline SVG figure with its "Show the data" table.

What this returns is inserted *after* nh3 (app.rendering), so it is safe
because of how it's built, not by filtering: every element goes through
app.chart_svg, which refuses anything outside the spec's fixed vocabulary,
and a writer's strings are only ever text content, escaped there.

Layout is in the SVG's own units: the stylesheet (static/site.css) sets
its text to FONT units and scales the SVG to the column. Both drawings share
the scale, so the phone one starts its axis where the wide one does.
"""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.chart_svg import (BASELINE, GRID, INK, LINE_CLASSES, MARKER_CLASSES, MUTED, NONE,
                           SERIES, SERIES_CLASSES, SURFACE)
from app.chart_svg import element as _element
from app.chart_svg import text as _text
from app.charts import Chart, Unit

PRIVACY_NOTE = "Some values are suppressed for privacy."
DATA_SUMMARY = "Show the data"

# Each Chart is drawn twice: WIDTH units wide, and PHONE_WIDTH for a narrow
# screen, which the stylesheet shows in its place, so its text stays near
# FONT pixels on a phone rather than shrinking with a wide drawing.
WIDTH = 520
PHONE_WIDTH = 360
FONT = 13            # the stylesheet's size for the SVG's text
_CHAR = FONT * 0.6   # an estimate of one character's width
_LINE = 18           # a line of text
_PLOT_HEIGHT = 220
_BAR = 24            # the thickest a bar is
_GAP = 2             # between touching bars


def _width(text: str) -> float:
    return len(text) * _CHAR


def _fit(text: str, room: float) -> str:
    """`text`, shortened with an ellipsis to fit `room` units."""
    if _width(text) <= room:
        return text
    keep = max(1, int(room // _CHAR) - 1)
    return text[:keep].rstrip() + "…"


def _label(x: float, y: float, text: str, css: str, anchor: str = "middle",
           fill: str = INK) -> str:
    return _element("text", {"class": css, "x": x, "y": y, "text-anchor": anchor, "fill": fill},
                    _text(text))


# Scales and ticks.

@dataclass(frozen=True)
class Scale:
    low: float
    high: float
    step: float

    @property
    def ticks(self) -> list[float]:
        count = round((self.high - self.low) / self.step)
        return [round(self.low + i * self.step, 10) for i in range(count + 1)]

    def at(self, value: float, start: float, length: float) -> float:
        """Where `value` falls along an axis from `start`, `length` long."""
        return start + length * (value - self.low) / (self.high - self.low)


def _scale(values: Sequence[float], *, from_zero: bool) -> Scale:
    """A scale with round ticks over `values`. A bar chart's (`from_zero`)
    always takes in zero; a line chart's does when its values come close."""
    low, high = (min(values), max(values)) if values else (0.0, 1.0)
    if from_zero or (low > 0 and low <= high / 3):
        low = min(low, 0.0)
    if from_zero or (high < 0 and high >= low / 3):
        high = max(high, 0.0)
    span = high - low or abs(high) or 1.0
    raw = span / 5
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    low, high = math.floor(low / step) * step, math.ceil(high / step) * step
    if high == low:
        high = low + step
    return Scale(low, high, step)


def _tick_text(value: float, step: float, unit: Unit | None) -> str:
    """A tick's label: a round number, with the units if they are $ or %."""
    decimals = max(0, -math.floor(math.log10(step) + 1e-9))
    if round(step * 10 ** decimals, 6) % 1:
        decimals += 1
    digits = f"{abs(value):,.{decimals}f}"
    sign = "-" if value < 0 and digits.strip("0.,") else ""
    if unit and unit.text == "$":
        return f"{sign}${digits}"
    if unit and unit.text == "%":
        return f"{sign}{digits}%"
    return sign + digits


def _value_title(chart: Chart) -> str | None:
    """The value axis's title: the y label, with the units if they are a
    word (the ticks show only $ and %), e.g. "Exports (tonnes)"."""
    unit = chart.effective_unit
    word = unit.text if unit and unit.text not in ("$", "%") else None
    if chart.y_label and word:
        return f"{chart.y_label} ({word})"
    return chart.y_label or word


def _axis(chart: Chart) -> tuple[Scale, list[tuple[float, str]]]:
    """The value axis: its scale, and each tick with its label."""
    numbers = [cell.number for cell in chart.cells() if cell.kind == "number"]
    scale = _scale(numbers, from_zero=chart.type != "line")
    unit = chart.effective_unit
    return scale, [(tick, _tick_text(tick, scale.step, unit)) for tick in scale.ticks]


def _negative(chart: Chart) -> list[str]:
    """The text of each negative value, as typed."""
    return [cell.text for cell in chart.cells() if cell.kind == "number" and cell.number < 0]


# The legend.

def _legend(chart: Chart, top: float, full: float) -> tuple[str, float]:
    """The legend for two or more series, from `top`, and its height."""
    if len(chart.series) < 2:
        return "", 0.0
    items, x, y = [], 0.0, top + FONT
    for index, series in enumerate(chart.series):
        name = _fit(series.name, full - 20)
        width = 18 + _width(name) + 16
        if x and x + width > full:
            x, y = 0.0, y + _LINE
        if chart.type == "line":
            swatch = _element("line", {"class": LINE_CLASSES[index], "x1": x, "y1": y - 4,
                                       "x2": x + 14, "y2": y - 4, "stroke": SERIES[index],
                                       "stroke-width": 2})
        else:
            swatch = _element("rect", {"class": SERIES_CLASSES[index], "x": x, "y": y - 10,
                                       "width": 12, "height": 12, "fill": SERIES[index]})
        items.append(swatch + _label(x + 18, y, name, "chart-legend", "start"))
        x += width
    return _element("g", {"class": "chart-legend"}, *items), y - top + 10


def _mark_title(chart: Chart, series_name: str, category: str, text: str) -> str:
    """A mark's tooltip: what it is, and its value as typed."""
    named = f"{series_name}, {category}" if len(chart.series) > 1 else category
    return _element("title", None, _text(f"{named}: {text}"))


# Bar and line charts: categories along the bottom.

def _category_labels(categories: Sequence[str], centre, step: float, y: float,
                     full: float) -> list[str]:
    """The categories under the plot, every k-th if they're crowded, each
    shortened to the room it has."""
    least = 4 * _CHAR + 4
    every = max(1, math.ceil(least / step)) if step < least else 1
    room = every * step - 4
    labels = []
    for index, category in enumerate(categories):
        if index % every:
            continue
        # Centred, so it has as much room to each side as the SVG leaves it.
        at = centre(index)
        fits = min(room, 2 * min(at, full - at))
        labels.append(_label(at, y, _fit(category, fits), "chart-category"))
    return labels


def _vertical(chart: Chart, full: float) -> tuple[str, float, Scale]:
    scale, ticks = _axis(chart)
    single = len(chart.series) == 1
    legend, legend_height = _legend(chart, 0, full)
    value_title = _value_title(chart)
    left = max(_width(text) for _, text in ticks) + 10
    end_label = ""
    if chart.type == "line" and single:
        last = [cell for cell in chart.series[0].cells if cell.kind == "number"]
        end_label = last[-1].text if last else ""
    right = 12 + (_width(end_label) + 8 if end_label else 0)
    plot_width = full - left - right
    count = len(chart.categories)
    step = plot_width / count
    # A single series' bars carry their values, if each fits its bar's
    # room: above a bar, or below a negative one, outside the plot.
    labelled = chart.type == "bar" and single and all(
        _width(cell.text) <= step - 2 for cell in chart.series[0].cells)
    above = FONT + 6 if labelled else 0
    below = FONT + 4 if labelled and _negative(chart) else 0
    top = legend_height + (_LINE if value_title else 0) + 10 + above
    bottom = top + _PLOT_HEIGHT

    def y(value: float) -> float:
        return scale.at(value, bottom, -_PLOT_HEIGHT)

    parts = [legend]
    if value_title:
        parts.append(_label(0, legend_height + FONT, _fit(value_title, full), "chart-axis-title",
                            "start"))
    grid = []
    for tick, text in ticks:
        grid.append(_element("line", {"class": "chart-grid", "x1": left, "y1": y(tick),
                                      "x2": left + plot_width, "y2": y(tick), "stroke": GRID,
                                      "stroke-width": 1}))
        grid.append(_label(left - 6, y(tick) + 4, text, "chart-tick", "end", MUTED))
    parts.append(_element("g", None, *grid))
    base = 0.0 if scale.low <= 0 <= scale.high else scale.low
    parts.append(_element("line", {"class": "chart-baseline", "x1": left, "y1": y(base),
                                   "x2": left + plot_width, "y2": y(base), "stroke": BASELINE,
                                   "stroke-width": 1}))
    if chart.type == "bar":
        parts.extend(_bars(chart, left, step, y, labelled))

        def centre(index: int) -> float:
            return left + (index + 0.5) * step
    else:
        inset = 12
        step = (plot_width - 2 * inset) / (count - 1)
        parts.extend(_lines(chart, lambda index: left + inset + index * step, y, end_label))

        def centre(index: int) -> float:
            return left + inset + index * step
    labels_y = bottom + below + 6 + FONT
    parts.append(_element("g", None, *_category_labels(chart.categories, centre, step, labels_y, full)))
    height = labels_y + 6
    if chart.x_label:
        height += _LINE
        parts.append(_label(left + plot_width / 2, height - 6, _fit(chart.x_label, full),
                            "chart-axis-title"))
    return "".join(parts), height, scale


def _bars(chart: Chart, left: float, step: float, y, labelled: bool) -> list[str]:
    count = len(chart.series)
    group = min(step * 0.7, count * _BAR + (count - 1) * _GAP)
    width = (group - (count - 1) * _GAP) / count
    marks, labels = [], []
    for index, category in enumerate(chart.categories):
        x0 = left + index * step + (step - group) / 2
        for number, series in enumerate(chart.series):
            cell = series.cells[index]
            x = x0 + number * (width + _GAP)
            if cell.kind == "number":
                top, bottom = y(max(cell.number, 0)), y(min(cell.number, 0))
                marks.append(_element("rect", {"class": SERIES_CLASSES[number], "x": x, "y": top,
                                               "width": width, "height": bottom - top,
                                               "fill": SERIES[number]},
                                      _mark_title(chart, series.name, category, cell.text)))
                if labelled:
                    at = top - 4 if cell.number >= 0 else bottom + FONT
                    labels.append(_label(x + width / 2, at, cell.text, "chart-value"))
            elif cell.kind == "suppressed" and labelled:
                labels.append(_label(x + width / 2, y(0) - 4, cell.text, "chart-value"))
    return [_element("g", None, *marks), _element("g", None, *labels)]


def _runs(points: Iterable[tuple[float, float] | None]) -> list[list[tuple[float, float]]]:
    """The unbroken runs of a line's points; a missing or suppressed value
    breaks it."""
    runs: list[list[tuple[float, float]]] = [[]]
    for point in points:
        if point is None:
            runs.append([])
        else:
            runs[-1].append(point)
    return [run for run in runs if run]


def _lines(chart: Chart, x, y, end_label: str) -> list[str]:
    marked = len(chart.categories) <= 12
    parts = []
    for number, series in enumerate(chart.series):
        points = [(x(index), y(cell.number)) if cell.kind == "number" else None
                  for index, cell in enumerate(series.cells)]
        lines, markers = [], []
        for run in _runs(points):
            if len(run) > 1:
                lines.append(_element("polyline", {"class": LINE_CLASSES[number], "points": run,
                                                   "fill": NONE, "stroke": SERIES[number],
                                                   "stroke-width": 2}))
        for index, (point, cell) in enumerate(zip(points, series.cells)):
            alone = point is not None and all(
                points[i] is None for i in (index - 1, index + 1) if 0 <= i < len(points))
            if point is not None and (marked or alone):
                markers.append(_element(
                    "circle", {"class": MARKER_CLASSES[number], "cx": point[0], "cy": point[1],
                               "r": 4, "fill": SERIES[number], "stroke": SURFACE,
                               "stroke-width": 2},
                    _mark_title(chart, series.name, chart.categories[index], cell.text)))
        parts.append(_element("g", None, *lines, *markers))
    if end_label:
        last = max(i for i, cell in enumerate(chart.series[0].cells) if cell.kind == "number")
        number = chart.series[0].cells[last].number
        parts.append(_label(x(last) + 8, y(number) + 4, end_label, "chart-value", "start"))
    return parts


# Horizontal bar charts: categories down the side.

def _horizontal(chart: Chart, full: float) -> tuple[str, float, Scale]:
    scale, ticks = _axis(chart)
    count = len(chart.series)
    single = count == 1
    thickness = 20 if single else 14
    band = count * thickness + (count - 1) * _GAP + 12
    legend, legend_height = _legend(chart, 0, full)
    top = legend_height + (_LINE if chart.x_label else 0) + 6
    # The category names' column, then room for a negative bar's value, left
    # of the bar, before the plot.
    names = min(max(_width(category) for category in chart.categories) + 10, full * 0.4)
    before = max(map(_width, _negative(chart)), default=-6) + 6 if single else 0
    left = max(names + before, _width(ticks[0][1]) / 2 + 2)
    names = left - before
    labels = [cell.text for cell in chart.series[0].cells] if single else []
    right = max([_width(text) for text in labels] + [_width(ticks[-1][1]) / 2]) + 10
    plot_width = full - left - right
    plot_height = len(chart.categories) * band
    bottom = top + plot_height

    def x(value: float) -> float:
        return scale.at(value, left, plot_width)

    parts = [legend]
    if chart.x_label:
        parts.append(_label(0, legend_height + FONT, _fit(chart.x_label, full),
                            "chart-axis-title", "start"))
    grid = []
    for tick, text in ticks:
        grid.append(_element("line", {"class": "chart-grid", "x1": x(tick), "y1": top,
                                      "x2": x(tick), "y2": bottom, "stroke": GRID,
                                      "stroke-width": 1}))
        grid.append(_label(x(tick), bottom + 6 + FONT, text, "chart-tick", "middle", MUTED))
    parts.append(_element("g", None, *grid))
    parts.append(_element("line", {"class": "chart-baseline", "x1": x(0), "y1": top,
                                   "x2": x(0), "y2": bottom, "stroke": BASELINE,
                                   "stroke-width": 1}))
    marks, values, categories = [], [], []
    for index, category in enumerate(chart.categories):
        band_top = top + index * band
        categories.append(_label(names - 8, band_top + band / 2 + 4, _fit(category, names - 10),
                                 "chart-category", "end"))
        for number, series in enumerate(chart.series):
            cell = series.cells[index]
            bar_y = band_top + 6 + number * (thickness + _GAP)
            if cell.kind == "number":
                start, end = x(min(cell.number, 0)), x(max(cell.number, 0))
                marks.append(_element("rect", {"class": SERIES_CLASSES[number], "x": start,
                                               "y": bar_y, "width": end - start,
                                               "height": thickness, "fill": SERIES[number]},
                                      _mark_title(chart, series.name, category, cell.text)))
                if single:
                    at, anchor = (end + 4, "start") if cell.number >= 0 else (start - 4, "end")
                    values.append(_label(at, bar_y + thickness / 2 + 4, cell.text,
                                         "chart-value", anchor))
            elif cell.kind == "suppressed" and single:
                values.append(_label(x(0) + 4, bar_y + thickness / 2 + 4, cell.text,
                                     "chart-value", "start"))
    parts += [_element("g", None, *categories), _element("g", None, *marks),
              _element("g", None, *values)]
    height = bottom + 6 + FONT + 6
    value_title = _value_title(chart)
    if value_title:
        height += _LINE
        parts.append(_label(left + plot_width / 2, height - 6, _fit(value_title, full),
                            "chart-axis-title"))
    return "".join(parts), height, scale


# The figure.

def _note(text: str, css: str = "chart-note") -> str:
    return _element("p", {"class": css}, _element("small", None, _text(text)))


def _data_table(chart: Chart) -> str:
    """The Chart's data as a table, each value with its original notation."""
    head = _element("tr", None,
                    _element("th", {"scope": "col"}, _text(chart.x_label or "Category")),
                    *(_element("th", {"scope": "col"}, _text(series.name))
                      for series in chart.series))
    rows = [_element("tr", None, _element("th", {"scope": "row"}, _text(category)),
                     *(_element("td", None, _text(series.cells[index].text))
                       for series in chart.series))
            for index, category in enumerate(chart.categories)]
    return _element("details", {"class": "chart-data"},
                    _element("summary", None, _text(DATA_SUMMARY)),
                    _element("table", None, _element("thead", None, head),
                             _element("tbody", None, *rows)))


def _svg(chart: Chart, title_id: str, full: float, css: str) -> tuple[str, Scale]:
    body, height, scale = (_horizontal if chart.type == "hbar" else _vertical)(chart, full)
    return _element("svg", {"class": css, "viewBox": (0, 0, full, math.ceil(height)),
                            "role": "img", "aria-labelledby": title_id}, body), scale


def draw(chart: Chart, key: str, number: int) -> str:
    """The figure for `chart`, the `number`th in a body whose key (32 hex
    characters, the same on every render of that body) is `key`."""
    title_id = f"chart-{key}-{number}-title"
    wide, scale = _svg(chart, title_id, WIDTH, "chart-svg")
    phone, _ = _svg(chart, title_id, PHONE_WIDTH, "chart-svg-phone")
    notes = []
    if chart.type == "line" and scale.low > 0:
        start = _tick_text(scale.low, scale.step, chart.effective_unit)
        notes.append(_note(f"The vertical axis starts at {start}, not zero."))
    if chart.suppressed:
        notes.append(_note(PRIVACY_NOTE))
    if chart.source:
        notes.append(_note(chart.source, "chart-source"))
    return _element("figure", {"class": "chart-figure"},
                    _element("figcaption", {"class": "chart-title", "id": title_id},
                             _text(chart.title)),
                    wide, phone, *notes, _data_table(chart))
