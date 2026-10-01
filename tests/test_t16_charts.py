"""T16: Chart rendering (issue #19). The `chart` fence's grammar, its number,
unit, missing, and suppressed rules, and its canonical form (app.charts).
Tested directly as a pure module; the save paths are in
test_t16_chart_saves.py."""
from __future__ import annotations

import json

import pytest

from app import charts
from app.charts import DOLLARS, PERCENT, ChartError, Unit, read_cell


def chart_data(**override) -> dict:
    """A valid bar chart's data, with `override` in place of its keys (None
    removes one)."""
    data = {"version": 1, "type": "bar", "title": "Fall enrollment by class",
            "categories": ["First-year", "Senior"],
            "series": [{"name": "Fall 2025", "values": ["482", "431"]}]}
    data.update(override)
    return {key: value for key, value in data.items() if value is not None}


def source(**override) -> str:
    return json.dumps(chart_data(**override), ensure_ascii=False)


def fence(text: str) -> str:
    return f"```chart\n{text}\n```\n"


def series(*values: str, name: str = "Fall 2025") -> dict:
    return {"name": name, "values": list(values)}


def categories(n: int) -> list[str]:
    return [f"Category {i}" for i in range(n)]


def test_a_valid_block_parses():
    chart = charts.parse(source(x_label="Class", y_label="Students",
                                unit={"text": "students", "position": "suffix"},
                                source="Registrar, census date"))
    assert chart.type == "bar" and chart.title == "Fall enrollment by class"
    assert chart.categories == ("First-year", "Senior")
    assert [cell.number for cell in chart.series[0].cells] == [482.0, 431.0]
    assert chart.unit == Unit("students", "suffix")


# Every way a block can break the grammar, and what the error says.
VIOLATIONS = [
    # Required keys.
    *[pytest.param(source(**{key: None}), f"is missing '{key}'", id=f"missing-{key}")
      for key in ("version", "type", "title", "categories", "series")],
    pytest.param(source(series=[{"name": "Fall"}]), "is missing 'values'", id="missing-values"),
    pytest.param(source(series=[{"values": ["1", "2"]}]), "is missing 'name'", id="missing-name"),
    pytest.param(source(unit={"text": "%"}), "is missing 'position'", id="missing-position"),
    # Unknown keys.
    pytest.param(source(colour="red"), "unknown key 'colour'", id="unknown-key"),
    pytest.param(source(series=[{**series("1", "2"), "colour": "red"}]),
                 "unknown key 'colour'", id="unknown-series-key"),
    pytest.param(source(unit={"text": "%", "position": "suffix", "size": 2}),
                 "unknown key 'size'", id="unknown-unit-key"),
    # Wrong types and values.
    pytest.param(source(version="1"), "version must be 1", id="version-string"),
    pytest.param(source(version=True), "version must be 1", id="version-true"),
    pytest.param(source(version=1.0), "version must be 1", id="version-float"),
    pytest.param(source(version=2), "version must be 1", id="version-2"),
    pytest.param(source(type="pie"), "type must be", id="type-pie"),
    pytest.param(source(type=["bar"]), "type must be", id="type-list"),
    pytest.param(source(title=5), "the title must be text", id="title-number"),
    pytest.param(source(x_label=False), "axis label must be text", id="x-label-bool"),
    pytest.param(source(source=["a"]), "the source must be text", id="source-list"),
    pytest.param(source(categories="First-year"), "categories must be a list",
                 id="categories-string"),
    pytest.param(source(categories=["First-year", 2]), "each category must be text",
                 id="category-number"),
    pytest.param(source(series={"name": "a", "values": []}), "series must be a list",
                 id="series-object"),
    pytest.param(source(series=["Fall"]), "each series must be an object", id="series-string"),
    pytest.param(source(series=[{"name": "Fall", "values": "482"}]), "values must be a list",
                 id="values-string"),
    pytest.param(source(series=[{"name": "Fall", "values": [482, 431]}]),
                 "'Fall', 'First-year' must be text", id="value-number"),
    pytest.param(source(series=[{"name": 7, "values": ["1", "2"]}]),
                 "a series name must be text", id="series-name-number"),
    pytest.param(source(unit="%"), "the units must be an object", id="unit-string"),
    pytest.param(source(unit={"text": "%", "position": "middle"}), "'prefix' or 'suffix'",
                 id="unit-position"),
    pytest.param(source(unit={"text": "$", "position": "suffix"}), "$ goes before the number",
                 id="dollar-suffix"),
    pytest.param(source(unit={"text": "%", "position": "prefix"}), "$ goes before the number",
                 id="percent-prefix"),
    pytest.param(source(unit={"text": "€", "position": "prefix"}), "currency other than $",
                 id="unit-euro"),
    pytest.param("[]", "the chart must be an object", id="not-an-object"),
    # Duplicate keys, NaN and Infinity, trailing data, broken JSON.
    pytest.param('{"version": 1, "version": 1, "type": "bar"}', "the key 'version' appears twice",
                 id="duplicate-key"),
    pytest.param(source().replace('"name": "Fall 2025"', '"name": "Fall 2025", "name": "x"'),
                 "the key 'name' appears twice", id="duplicate-nested-key"),
    pytest.param(source().replace('"version": 1', '"version": NaN'), "NaN isn't a number",
                 id="nan"),
    pytest.param(source().replace('"version": 1', '"version": Infinity'),
                 "Infinity isn't a number", id="infinity"),
    pytest.param(source().replace('"version": 1', '"version": -Infinity'),
                 "-Infinity isn't a number", id="minus-infinity"),
    pytest.param(source() + " {}", "can't be read (Extra data", id="trailing-object"),
    pytest.param(source() + "\nx", "can't be read (Extra data", id="trailing-text"),
    pytest.param("{", "can't be read", id="broken-json"),
    pytest.param("", "can't be read", id="empty"),
    # Lengths.
    pytest.param(source(title="t" * 121), "the title must be 1 to 120", id="title-long"),
    pytest.param(source(title=""), "the title must be 1 to 120", id="title-empty"),
    pytest.param(source(title="   "), "the title must be 1 to 120", id="title-blank"),
    pytest.param(source(x_label="x" * 61), "at most 60", id="x-label-long"),
    pytest.param(source(y_label="y" * 61), "at most 60", id="y-label-long"),
    pytest.param(source(source="s" * 201), "at most 200", id="source-long"),
    pytest.param(source(unit={"text": "u" * 21, "position": "suffix"}), "1 to 20",
                 id="unit-long"),
    pytest.param(source(unit={"text": " ", "position": "suffix"}), "1 to 20", id="unit-blank"),
    pytest.param(source(categories=["c" * 61, "Senior"]), "each category must be 1 to 60",
                 id="category-long"),
    pytest.param(source(categories=["", "Senior"]), "each category must be 1 to 60",
                 id="category-empty"),
    pytest.param(source(series=[series("1", "2", name="n" * 41)]), "1 to 40",
                 id="series-name-long"),
    pytest.param(source(series=[series("1" * 21, "2")]), "at most 20", id="value-long"),
    # Single line.
    pytest.param(source(title="Fall\nenrollment"), "the title must be on one line",
                 id="title-newline"),
    pytest.param(source(title="Fall\renrollment"), "on one line", id="title-return"),
    pytest.param(source(source="Registrar\tcensus"), "on one line", id="source-tab"),
    pytest.param(source(x_label="Class year"), "on one line", id="label-line-separator"),
    pytest.param(source(categories=["First\nyear", "Senior"]), "on one line",
                 id="category-newline"),
    pytest.param(source(series=[series("4\n82", "431")]), "on one line", id="value-newline"),
    pytest.param(source(series=[series("1", "2", name="Fall\x00")]), "on one line",
                 id="series-name-nul"),
    # Counts.
    pytest.param(source(series=[series("482")]),
                 "series 'Fall 2025' has 1 values but 2 categories", id="values-short"),
    pytest.param(source(series=[series("1", "2", "3")]), "has 3 values but 2 categories",
                 id="values-long"),
    pytest.param(source(categories=[], series=[series()]),
                 "a bar chart has 1 to 30 categories; this one has 0", id="no-categories"),
    pytest.param(source(categories=categories(31), series=[series(*["1"] * 31)]),
                 "has 1 to 30 categories; this one has 31", id="bar-31-categories"),
    pytest.param(source(type="hbar", categories=categories(31), series=[series(*["1"] * 31)]),
                 "a horizontal bar chart has 1 to 30", id="hbar-31-categories"),
    pytest.param(source(type="line", categories=["Fall"], series=[series("1")]),
                 "a line chart has 2 to 60 categories; this one has 1", id="line-1-category"),
    pytest.param(source(type="line", categories=categories(61), series=[series(*["1"] * 61)]),
                 "a line chart has 2 to 60 categories; this one has 61", id="line-61-categories"),
    pytest.param(source(series=[]), "1 to 4 series; this one has 0", id="no-series"),
    pytest.param(source(series=[series("1", "2", name=f"S{i}") for i in range(5)]),
                 "1 to 4 series; this one has 5", id="five-series"),
    pytest.param(source(categories=["Senior", "Senior"]), "the category 'Senior' appears twice",
                 id="duplicate-category"),
    pytest.param(source(series=[series("1", "2"), series("3", "4")]),
                 "the series name 'Fall 2025' appears twice", id="duplicate-series"),
    # Size.
    pytest.param(source(source=None, x_label=None) + " " * (32 * 1024), "larger than 32 KB",
                 id="over-32-kb"),
    # Cells.
    pytest.param(source(series=[series("482", "lots")]),
                 "series 'Fall 2025', 'Senior': 'lots' isn't a number", id="value-text"),
    pytest.param(source(series=[series("€482", "431")]),
                 "series 'Fall 2025', 'First-year': '€482' is in a currency other than $",
                 id="value-euro"),
    pytest.param(source(series=[series("$5", "5%")]),
                 "'Senior': '5%' is in %, but the chart's units are $", id="mixed-units"),
]


@pytest.mark.parametrize("text, message", VIOLATIONS)
def test_each_grammar_violation_is_refused_with_a_named_error(text, message):
    with pytest.raises(ChartError) as raised:
        charts.parse(text, 2)
    assert str(raised.value).startswith("Chart 2: ")
    assert message in str(raised.value)


def test_a_block_of_exactly_32_kb_is_allowed():
    text = source()
    padded = text + " " * (32 * 1024 - len(text.encode()))
    assert len(padded.encode()) == 32 * 1024
    charts.parse(padded)


def test_the_limits_themselves_are_allowed():
    charts.parse(source(title="t" * 120, x_label="x" * 60, y_label="y" * 60, source="s" * 200,
                        unit={"text": "u" * 20, "position": "suffix"},
                        categories=["c" * 60, *categories(29)],
                        series=[series(*["1" * 20] * 30, name="n" * 40),
                                *(series(*["1"] * 30, name=f"S{i}") for i in range(3))]))
    charts.parse(source(type="line", categories=categories(60), series=[series(*["1"] * 60)]))


def test_strings_are_nfc_normalized():
    decomposed = "Café"
    chart = charts.parse(source(title=decomposed, categories=[decomposed, "Senior"]))
    assert chart.title == chart.categories[0] == "Café"


def test_two_categories_equal_only_after_normalizing_are_duplicates():
    with pytest.raises(ChartError, match="appears twice"):
        charts.parse(source(categories=["Café", "Café"]))


# Reading cells.

NUMBERS = [
    ("482", 482, None), ("1,234", 1234, None), ("1,234,567.5", 1234567.5, None),
    ("0.75", 0.75, None), ("-5", -5, None), ("+3", 3, None), ("-1,200.5", -1200.5, None),
    ("(3.2)", -3.2, None), ("(1,000)", -1000, None), ("$1,200", 1200, DOLLARS),
    ("-$4.50", -4.5, DOLLARS), ("+$1,200", 1200, DOLLARS), ("($1,000)", -1000, DOLLARS),
    ("12%", 12, PERCENT), ("-0.5%", -0.5, PERCENT), ("+3%", 3, PERCENT), ("(12%)", -12, PERCENT),
    ("1,200 students", 1200, Unit("students", "suffix")),
    ("3 full-time faculty", 3, Unit("full-time faculty", "suffix")),
    ("  482  ", 482, None),
]


@pytest.mark.parametrize("text, number, unit", NUMBERS)
def test_each_number_format_reads_as_its_number_and_unit(text, number, unit):
    cell = read_cell(text)
    assert (cell.kind, cell.number, cell.unit) == ("number", number, unit)
    assert cell.text == text.strip()


@pytest.mark.parametrize("text", ["", "   ", "—", "n/a", "N/A", " — "])
def test_blank_dash_and_na_are_missing(text):
    assert read_cell(text).kind == "missing"


@pytest.mark.parametrize("text", ["*", "<10", "≤5", "<=5", " <10 ", "<0"])
def test_suppressed_notation_is_suppressed_and_kept_as_typed(text):
    cell = read_cell(text)
    assert (cell.kind, cell.text, cell.number) == ("suppressed", text.strip(), None)


@pytest.mark.parametrize("text", ["**", "<", "< 10", "<10.5", "<-5", "<=", ">10", "≥5",
                                  "*5", "10*", "<10%", "n/a*"])
def test_anything_else_that_looks_suppressed_is_not_a_value(text):
    with pytest.raises(ValueError, match="isn't a number"):
        read_cell(text)


@pytest.mark.parametrize("text", ["€5", "£1,000", "¥300", "5€", "₹40", "($€5)"])
def test_any_other_currency_is_an_error(text):
    with pytest.raises(ValueError, match="currency other than \\$"):
        read_cell(text)


NOT_NUMBERS = ["+-5", "-+5", "(+3)", "-(3)", "1,23", "12,3456", ",123", "3.2.1", ".5", "5.",
               "5$", "%12", "(3.2", "3.2)", "--5", "$$5", "1e3", "Fall 2025", "12 %",
               "12  students", "students", "12students", "0x10", "1_000", "½", "٣"]


@pytest.mark.parametrize("text", NOT_NUMBERS)
def test_anything_else_is_not_a_number(text):
    with pytest.raises(ValueError, match="isn't a number"):
        read_cell(text)


@pytest.mark.parametrize("text", ["$5%", "$5 students", "5% students"])
def test_a_cell_with_two_units_is_an_error(text):
    with pytest.raises(ValueError, match="more than one unit"):
        read_cell(text)


# Units.

def units_of(*values: str, **override) -> Unit | None:
    return charts.parse(source(series=[series(*values)], **override)).effective_unit


def test_a_percent_in_the_data_makes_the_units_percent():
    assert units_of("12%", "15") == PERCENT


def test_a_dollar_in_the_data_makes_the_units_dollars():
    assert units_of("15", "$1,200") == DOLLARS


def test_a_word_in_the_data_makes_the_units_that_word():
    assert units_of("482 students", "431") == Unit("students", "suffix")


def test_stated_units_win_and_a_bare_number_fits_any():
    assert units_of("12", "15", unit={"text": "%", "position": "suffix"}) == PERCENT


def test_no_units_anywhere_is_none():
    assert units_of("12", "15") is None


def test_inferred_units_are_not_written_into_the_block():
    chart = charts.parse(source(series=[series("12%", "15")]))
    assert "unit" not in json.loads(chart.canonical())


@pytest.mark.parametrize("values, override, message", [
    (("$5", "5%"), {}, "series 'Fall 2025', 'Senior': '5%' is in %, but the chart's units are $"),
    (("5%", "$5"), {}, "'Senior': '$5' is in $, but the chart's units are %"),
    (("5 students", "5 faculty"), {}, "'5 faculty' is in faculty, but the chart's units are students"),
    (("5", "5%"), {"unit": {"text": "$", "position": "prefix"}},
     "'Senior': '5%' is in %, but the chart's units are $"),
    (("5 Students", "6"), {"unit": {"text": "students", "position": "suffix"}},
     "'First-year': '5 Students' is in Students"),
])
def test_a_unit_conflict_names_its_first_cell(values, override, message):
    with pytest.raises(ChartError, match="^Chart 1: ") as raised:
        charts.parse(source(series=[series(*values)], **override))
    assert message in str(raised.value)


def test_the_first_conflict_is_found_category_by_category_series_across():
    text = source(series=[series("$1", "$2", name="A"), series("3%", "4", name="B")])
    with pytest.raises(ChartError, match="series 'B', 'First-year': '3%'"):
        charts.parse(text)


# The canonical form.

CANONICAL = """{
  "version": 1,
  "type": "line",
  "title": "Retention, first to second year",
  "x_label": "Entering class",
  "y_label": "Retained",
  "unit": {
    "text": "%",
    "position": "suffix"
  },
  "source": "Registrar, census date",
  "categories": [
    "2023",
    "2024"
  ],
  "series": [
    {
      "name": "All students",
      "values": [
        "91%",
        "<10"
      ]
    }
  ]
}
"""


def test_the_canonical_form_orders_keys_as_the_grammar_and_ends_with_a_newline():
    shuffled = {"series": [{"values": ["91%", "<10"], "name": "All students"}],
                "categories": ["2023", "2024"], "source": "Registrar, census date",
                "unit": {"position": "suffix", "text": "%"}, "y_label": "Retained",
                "x_label": "Entering class", "title": "Retention, first to second year",
                "type": "line", "version": 1}
    assert charts.parse(json.dumps(shuffled)).canonical() == CANONICAL


def test_the_canonical_form_leaves_out_absent_keys_and_keeps_non_ascii_as_is():
    text = charts.parse(source(title="Café—enrollment")).canonical()
    assert list(json.loads(text)) == ["version", "type", "title", "categories", "series"]
    assert "Café—enrollment" in text and "\\u" not in text


def test_the_canonical_form_is_stable():
    once = charts.parse(source(title="Café")).canonical()
    assert charts.parse(once).canonical() == once


def test_values_are_kept_exactly_as_typed_in_the_canonical_form():
    text = charts.parse(source(series=[series(" 1,200 ", "<10")])).canonical()
    assert json.loads(text)["series"][0]["values"] == [" 1,200 ", "<10"]


# Finding Charts in a body.

def test_a_chart_fence_is_one_whose_trimmed_info_string_is_chart():
    from app.rendering import parse
    body = (fence("{}") + "\n``` chart \n{}\n```\n\n~~~chart\n{}\n~~~\n\n"
            "```chart x\n{}\n```\n\n```json\n{}\n```\n\n> ```chart\n> {}\n> ```\n")
    assert len(charts.sources(parse(body))) == 4


def test_check_names_the_first_invalid_chart_by_its_place_in_the_body():
    from app.rendering import parse
    body = fence(source()) + "\nText.\n\n" + fence(source(series=[series("1")]))
    with pytest.raises(ChartError, match="^Chart 2: series 'Fall 2025' has 1 values"):
        charts.check(parse(body))
