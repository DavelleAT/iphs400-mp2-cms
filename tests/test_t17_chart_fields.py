"""T17: Chart builder (issue #20). Each of T16's errors names the field it is
in, so the builder can show it next to that field or cell, and
`charts.problems` finds every field's error at once (app.charts). Tested
directly as a pure module; the preview route is in test_t17_chart_preview.py."""
from __future__ import annotations

import json

import pytest

from app import charts
from app.charts import ChartError
from tests.test_t16_charts import VIOLATIONS, categories, chart_data, series, source


def fields(text: str) -> list[tuple[str | None, str]]:
    return [(error.field, str(error)) for error in charts.problems(text)]


def test_a_valid_chart_has_no_problems():
    assert charts.problems(source()) == []


@pytest.mark.parametrize("override, field, message", [
    ({"title": ""}, "title", "the title must be 1 to 120 characters"),
    ({"type": "pie"}, "type", "its type must be"),
    ({"x_label": "x" * 61}, "x_label", "the category axis label must be at most 60"),
    ({"y_label": "a\tb"}, "y_label", "the value axis label must be on one line"),
    ({"source": "s" * 201}, "source", "the source must be at most 200"),
    ({"unit": {"text": "€", "position": "suffix"}}, "unit", "a currency other than $"),
    ({"unit": {"text": "$", "position": "suffix"}}, "unit", "$ goes before the number"),
    ({"categories": ["First-year", ""]}, "categories.1", "each category must be 1 to 60"),
    ({"categories": ["Senior", "Senior"]}, "categories.1", "the category 'Senior' appears twice"),
    ({"categories": categories(31)}, "categories", "a bar chart has 1 to 30 categories"),
    ({"type": "line", "categories": ["2024"]}, "categories", "a line chart has 2 to 60"),
    ({"series": [series("1", "2", name="")]}, "series.0.name", "a series name must be 1 to 40"),
    ({"series": [series("1", "2", name="A"), series("3", "4", name="A")]}, "series.1.name",
     "the series name 'A' appears twice"),
    ({"series": [series("1", "2", name=str(i)) for i in range(5)]}, "series",
     "a chart has 1 to 4 series"),
    ({"series": [series("1")]}, "series.0.values", "has 1 values but 2 categories"),
    ({"series": [series("482", "abc")]}, "series.0.values.1", "'abc' isn't a number"),
    ({"series": [series("€5", "1")]}, "series.0.values.0", "a currency other than $"),
    ({"series": [series("5$%", "1")]}, "series.0.values.0", "isn't a number"),
    ({"series": [series("1", "x" * 21)]}, "series.0.values.1", "must be at most 20"),
    ({"series": [series("$1", "2", name="A"), series("3", "4%", name="B")]}, "series.1.values.1",
     "'4%' is in %, but the chart's units are $"),
])
def test_each_error_names_its_field(override, field, message):
    [(found, text)] = fields(source(**override))
    assert found == field and message in text


def test_parse_keeps_the_field_under_its_chart_number():
    with pytest.raises(ChartError, match="^Chart 3: series 'Fall 2025', 'Senior'") as raised:
        charts.parse(source(series=[series("1", "abc")]), 3)
    assert raised.value.field == "series.0.values.1"


@pytest.mark.parametrize("text, message", VIOLATIONS)
def test_every_t16_error_is_still_found_with_its_message(text, message):
    found = charts.problems(text)
    assert found and message in str(found[0])
    with pytest.raises(ChartError) as raised:
        charts.parse(text)
    assert str(raised.value).removeprefix("Chart 1: ") in [str(error) for error in found]


def test_every_field_with_an_error_is_found_at_once():
    text = source(title="", x_label="a\nb", categories=["First-year", ""],
                  series=[series("abc", "2", name="A"), series("1", "<5x", name="")])
    assert [field for field, _ in fields(text)] == [
        "title", "x_label", "categories.1", "series.1.name",
        "series.0.values.0", "series.1.values.1"]


def test_whole_chart_errors_wait_until_each_field_is_right():
    """Counts, duplicates, and unit conflicts come from the whole chart, so
    they are only reported once nothing else is wrong."""
    text = source(title="", categories=["Senior", "Senior"])
    assert [field for field, _ in fields(text)] == ["title"]


@pytest.mark.parametrize("text, message", [
    ("{", "its data can't be read"),
    ("[]", "the chart must be an object"),
    (json.dumps({**chart_data(), "colour": "red"}), "unknown key 'colour'"),
    (json.dumps({**chart_data(), "categories": "Senior"}), "the categories must be a list"),
    ("x" * (charts.MAX_BYTES + 1), "larger than 32 KB"),
])
def test_an_error_in_no_one_field_has_none(text, message):
    [(field, found)] = fields(text)
    assert field is None and message in found


# Suggesting a horizontal bar chart.

def test_a_long_category_suggests_a_horizontal_bar_chart():
    long = "x" * (charts.LONG_CATEGORY + 1)
    assert charts.suggestion(source(categories=["Senior", long])) == "hbar"


@pytest.mark.parametrize("text", [
    source(categories=["Senior", "x" * charts.LONG_CATEGORY]),
    source(type="hbar", categories=["Senior", "x" * 40]),
    source(type="line", categories=["Senior", "x" * 40]),
    json.dumps({"type": "bar", "categories": "x" * 40}),
    json.dumps({"type": "bar", "categories": [None, 5]}),
    "[]", "{",
])
def test_nothing_else_suggests_one(text):
    assert charts.suggestion(text) is None
