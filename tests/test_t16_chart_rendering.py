"""T16: Chart rendering (issue #19). Drawing (app.chart_drawing), the trusted
SVG boundary in app.rendering, and Charts on the Site preview, the public
page, and the export."""
from __future__ import annotations

import hashlib
import json
import re
from html.parser import HTMLParser

import pytest

from app import chart_drawing, charts, rendering
from app.chart_drawing import CLASSES, ELEMENTS, PALETTE, ChartDrawError
from app.publish import render_site
from app.rendering import CHART_NOT_SHOWN, ChartPlacementError, render_markdown
from tests.test_t07_public_site import crawl, published_bite, published_report
from tests.test_t08_publish import exported
from tests.test_t09_tables import content_body
from tests.test_t12_site_preview import preview
from tests.test_t16_charts import chart_data, fence, series

ATTRIBUTES = {"class", "viewBox", "role", "aria-labelledby", "aria-hidden", "id", "x", "y",
              "x1", "y1", "x2", "y2", "width", "height", "cx", "cy", "r", "points", "fill",
              "stroke", "stroke-width", "text-anchor", "scope"}
TITLE_ID = re.compile(r"chart-[0-9a-f]{32}-[0-9]+-title")


class Figure(HTMLParser):
    """A rendered figure, as html.parser reads it: every element with its
    attributes, and every piece of text content."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.starts: list[tuple[str, dict[str, str]]] = []
        self.texts: list[str] = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.starts.append((tag, {name: value or "" for name, value in attrs}))

    handle_startendtag = handle_starttag

    def handle_data(self, data):
        self.texts.append(data)

    @property
    def elements(self) -> set[str]:
        return {tag for tag, _ in self.starts}

    @property
    def attribute_names(self) -> set[str]:
        return {name for _, attrs in self.starts for name in attrs}

    def values(self, name: str) -> list[str]:
        return [attrs[name] for _, attrs in self.starts if name in attrs]

    def named(self, tag: str, **attributes: str) -> int:
        """How many `tag` elements there are, with these attribute values."""
        return sum(1 for element, attrs in self.starts if element == tag
                   and all(attrs.get(name) == value for name, value in attributes.items()))


def drawn(**override) -> str:
    """A body holding one Chart, rendered."""
    return str(render_markdown(fence(json.dumps(chart_data(**override)))))


def drawings(html: str) -> list[str]:
    """The figure's two SVGs, wide and phone, each as HTML."""
    found = re.findall(r'<svg class="(chart-svg(?:-phone)?)".*?</svg>', html, re.S)
    assert found == ["chart-svg", "chart-svg-phone"], found
    return re.findall(r'<svg class="chart-svg(?:-phone)?".*?</svg>', html, re.S)


def figure_of(**override) -> Figure:
    html = drawn(**override).strip()
    assert html.startswith('<figure class="chart-figure">') and html.endswith("</figure>"), html
    return Figure(html)


ALL_OPTIONAL = {"x_label": "Class", "y_label": "Students", "source": "Registrar, census date"}
FOUR = [series("1,200", "-5", "", "<10", name="A"), series("$3", "(4)", "n/a", "*", name="B"),
        series("2", "0", "—", "≤5", name="C"), series("-$1,000.5", "7", "8", "<=5", name="D")]
CHARTS = [
    *[pytest.param({"type": kind}, id=f"{kind}-one-series") for kind in charts.TYPES],
    *[pytest.param({"type": kind, "categories": ["A", "B", "C", "D"], "series": FOUR,
                    **ALL_OPTIONAL}, id=f"{kind}-four-series-negatives-missing-suppressed")
      for kind in charts.TYPES],
    pytest.param({"type": "line", "categories": [f"{2000 + i}" for i in range(60)],
                  "series": [series(*[str(900 + i) for i in range(60)])],
                  "unit": {"text": "students", "position": "suffix"}}, id="line-sixty-points"),
    pytest.param({"type": "bar", "categories": [f"Category {i}" for i in range(30)],
                  "series": [series(*["12%"] * 30)]}, id="bar-thirty-categories"),
    pytest.param({"type": "hbar", "series": [series("n/a", "—")]}, id="hbar-all-missing"),
]


@pytest.mark.parametrize("override", CHARTS)
def test_the_figure_uses_only_the_fixed_vocabulary(override):
    """The structural allowlist test (spec #14)."""
    figure = figure_of(**override)
    assert figure.elements <= ELEMENTS
    # html.parser lowercases names, as a browser's HTML parser reads them.
    assert figure.attribute_names <= {name.lower() for name in ATTRIBUTES}
    for name in ("fill", "stroke"):
        assert set(figure.values(name)) <= PALETTE, name
    assert set(figure.values("class")) <= CLASSES
    assert all(TITLE_ID.fullmatch(value) for value in figure.values("id"))
    assert all(TITLE_ID.fullmatch(value) for value in figure.values("aria-labelledby"))
    names = figure.attribute_names
    assert not names & {"href", "xlink:href", "style", "src"}
    assert not any(name.startswith("on") for name in names)


def test_the_vocabulary_is_the_specs():
    assert ELEMENTS == {"figure", "figcaption", "svg", "g", "title", "rect", "line", "polyline",
                        "circle", "text", "p", "small", "details", "summary", "table", "thead",
                        "tbody", "tr", "th", "td"}
    assert chart_drawing.ATTRIBUTES == ATTRIBUTES


HOSTILE = ["<script>alert(1)</script>", '"><svg onload=alert(1)>', "javascript:alert(1)",
           "</title><script>x</script>", "Tom & Jerry &amp; <b>"]


@pytest.mark.parametrize("hostile", HOSTILE)
def test_hostile_writer_strings_are_only_escaped_text(hostile):
    html = drawn(type="line", title=hostile, x_label=hostile[:60], y_label=hostile[:60],
                 source=hostile, unit={"text": hostile[:20], "position": "suffix"},
                 categories=[hostile[:60], "Senior"],
                 series=[series("<10", "≤5", name=hostile[:40]), series("1", "2", name="B")])
    figure = Figure(html)
    assert figure.elements <= ELEMENTS
    assert not any(hostile[:20] in value for _, attrs in figure.starts for value in attrs.values())
    text = "".join(figure.texts)
    assert hostile in text and hostile[:20] in text
    assert "<script" not in html and "<b>" not in html and "<svg onload" not in html


def test_a_placeholder_typed_by_the_writer_is_inert_text():
    typed = "chart-0123456789abcdef0123456789abcdef-0"
    html = str(render_markdown(f"{typed}\n\n" + fence(json.dumps(chart_data()))))
    assert html.startswith(f"<p>{typed}</p>")
    assert html.count("<figure") == 1


def test_a_writer_who_somehow_typed_the_nonce_gets_a_loud_failure(monkeypatch):
    """Missing, extra, or leftover placeholders raise, never render partly."""
    monkeypatch.setattr(rendering.secrets, "token_hex", lambda n: "f" * 32)
    for extra in (f"chart-{'f' * 32}-0", f"chart-{'f' * 32}-1", f"x chart-{'f' * 32}-0 y"):
        with pytest.raises(ChartPlacementError):
            render_markdown(f"{extra}\n\n" + fence(json.dumps(chart_data())))


def test_a_placeholder_nh3_lost_fails_loudly(monkeypatch):
    monkeypatch.setattr(rendering.nh3, "clean", lambda html, **_: "<p>gone</p>")
    with pytest.raises(ChartPlacementError):
        render_markdown(fence(json.dumps(chart_data())))


def test_two_charts_get_distinct_placeholders_and_each_render_a_fresh_nonce(monkeypatch):
    nonces = iter(["a" * 32, "b" * 32])
    monkeypatch.setattr(rendering.secrets, "token_hex", lambda n: next(nonces))
    body = fence(json.dumps(chart_data(title="One"))) + "\n" + fence(json.dumps(chart_data(title="Two")))
    env = {"nonce": rendering.secrets.token_hex(16), "charts": []}
    html = rendering._MARKDOWN.render(body, env)
    assert html == f"<p>chart-{'a' * 32}-0</p>\n<p>chart-{'a' * 32}-1</p>\n"
    rendered = str(render_markdown(body))
    assert rendered.index(">One<") < rendered.index(">Two<")
    key = hashlib.sha256(body.encode()).hexdigest()[:32]
    assert re.findall(r'id="([^"]+)"', rendered) == [f"chart-{key}-0-title", f"chart-{key}-1-title"]


def test_an_invalid_chart_renders_only_the_fixed_text():
    for source in ("{", json.dumps(chart_data(type="pie")), '{"title": "<script>x</script>"}'):
        assert str(render_markdown(fence(source))) == f"<p>{CHART_NOT_SHOWN}</p>\n"


def test_only_a_chart_fence_is_drawn():
    html = str(render_markdown("```json\n" + json.dumps(chart_data()) + "\n```\n"))
    assert "<figure" not in html and "<code" in html


def test_the_same_body_renders_the_same_bytes_and_another_body_another_id():
    body = fence(json.dumps(chart_data()))
    assert str(render_markdown(body)) == str(render_markdown(body))
    ids = {re.search(r'id="([^"]+)"', str(render_markdown(text)))[1]
           for text in (body, body + "\nMore.\n")}
    assert len(ids) == 2


# Drawing.

@pytest.mark.parametrize("kind", ["bar", "hbar"])
def test_a_bar_chart_starts_at_zero(kind):
    html = drawn(type=kind, series=[series("900", "950")])
    ticks = re.findall(r'class="chart-tick"[^>]*>([^<]*)<', html)
    assert ticks[0] == "0"
    baseline = re.search(r'class="chart-baseline" x1="([\d.]+)" y1="([\d.]+)"', html)
    rects = re.findall(r'<rect class="chart-series-1" x="([\d.]+)" y="([\d.]+)" width="([\d.]+)"'
                       r' height="([\d.]+)"', html)
    for x, y, width, height in rects:
        if kind == "bar":
            assert float(y) + float(height) == pytest.approx(float(baseline[2]))
        else:
            assert float(x) == pytest.approx(float(baseline[1]))
    assert "not zero" not in html


def test_a_bar_chart_with_negatives_spans_zero_with_bars_either_side():
    html = drawn(series=[series("-50", "100")])
    ticks = re.findall(r'class="chart-tick"[^>]*>([^<]*)<', html)
    assert ticks[0].startswith("-") and "0" in ticks


def test_a_line_chart_above_zero_says_where_it_starts():
    html = drawn(type="line", series=[series("900", "950")],
                 unit={"text": "$", "position": "prefix"})
    assert '<p class="chart-note"><small>The vertical axis starts at $900, not zero.</small></p>' in html


def test_a_line_chart_near_zero_starts_at_zero_and_says_nothing():
    html = drawn(type="line", series=[series("10", "100")])
    assert re.findall(r'class="chart-tick"[^>]*>([^<]*)<', html)[0] == "0"
    assert "not zero" not in html


def test_the_privacy_note_appears_once_however_many_values_are_suppressed():
    html = drawn(categories=["A", "B", "C"],
                 series=[series("*", "<10", "5", name="One"), series("≤5", "<=3", "6", name="Two")])
    assert html.count("Some values are suppressed for privacy.") == 1
    assert "suppressed" not in drawn()


def test_missing_and_suppressed_values_draw_no_mark():
    html = drawn(categories=["A", "B", "C", "D"], series=[series("1", "", "<10", "n/a")])
    for svg in drawings(html):
        assert Figure(svg).named("rect") == 1


def test_a_missing_value_breaks_a_line_into_runs():
    html = drawn(type="line", categories=list("ABCDEF"),
                 series=[series("1", "2", "—", "4", "5", "*")])
    for svg in drawings(html):
        assert svg.count("<polyline") == 2
        assert svg.count("<circle") == 4


def test_a_lone_point_between_gaps_gets_a_marker_on_a_crowded_line():
    values = ["5"] * 30
    values[10:13] = ["", "7", ""]
    html = drawn(type="line", categories=[str(i) for i in range(30)], series=[series(*values)])
    for svg in drawings(html):
        assert svg.count("<circle") == 1


def test_values_are_labelled_as_typed():
    html = drawn(series=[series("1,200.50", "$5")], unit={"text": "$", "position": "prefix"})
    for svg in drawings(html):
        assert re.findall(r'class="chart-value"[^>]*>([^<]*)<', svg) == ["1,200.50", "$5"]


def test_a_legend_only_for_two_or_more_series():
    assert "chart-legend" not in drawn()
    two = drawn(series=[series("1", "2", name="Fall"), series("3", "4", name="Spring")])
    for svg in drawings(two):
        assert svg.count('class="chart-legend"') == 3


def test_show_the_data_keeps_the_original_notation():
    html = drawn(categories=["A", "B", "C", "D", "E", "F", "G"],
                 series=[series("1,200", "$4.50", "(3.2)", "<10", "n/a", "—", "")],
                 unit={"text": "$", "position": "prefix"})
    figure = Figure(html)
    table = html[html.index("<table>"):]
    assert re.findall(r"<td>([^<]*)</td>", table) == ["1,200", "$4.50", "(3.2)", "&lt;10", "n/a",
                                                      "—", ""]
    assert "<summary>Show the data</summary>" in html
    assert figure.named("th", scope="col") == 2 and figure.named("th", scope="row") == 7


def test_each_chart_is_drawn_wide_and_for_a_phone_and_the_stylesheet_swaps_them(client):
    wide, phone = drawings(drawn())
    assert 'viewBox="0 0 520 ' in wide and 'viewBox="0 0 360 ' in phone
    css = client.get("/style.css").text
    assert re.search(r"\.chart-svg-phone\s*\{\s*display:\s*none;\s*\}", css)
    assert re.search(r"@media \(max-width: 30rem\) \{ \.chart-svg \{ display: none; \} "
                     r"\.chart-svg-phone \{ display: block; \} \}", css)


def test_a_phone_drawing_shortens_long_labels_to_fit():
    long = "A category name of exactly sixty characters, to be shortened"
    wide, phone = drawings(drawn(type="hbar", categories=[long, "Senior"]))
    shown = [re.findall(r'class="chart-category"[^>]*>([^<]*)<', svg)[0] for svg in (wide, phone)]
    assert all(label.endswith("…") and long.startswith(label[:-1]) for label in shown)
    assert len(shown[1]) < len(shown[0])


def test_the_svg_is_an_image_named_by_the_title():
    html = drawn(title="Fall enrollment")
    [title_id] = re.findall(r'<figcaption class="chart-title" id="([^"]+)">Fall enrollment<', html)
    assert TITLE_ID.fullmatch(title_id)
    assert html.count(f'role="img" aria-labelledby="{title_id}"') == 2


def test_the_drawing_refuses_anything_outside_its_vocabulary():
    with pytest.raises(ChartDrawError):
        chart_drawing._element("script")
    with pytest.raises(ChartDrawError):
        chart_drawing._element("rect", {"style": "fill:red"})
    with pytest.raises(ChartDrawError):
        chart_drawing._element("rect", {"fill": "url(#x)"})
    with pytest.raises(ChartDrawError):
        chart_drawing._element("rect", {"class": "chart-figure other"})
    with pytest.raises(ChartDrawError):
        chart_drawing._element("figcaption", {"id": "chart-x-0-title"})
    for bad in (float("nan"), float("inf"), "10", True):
        with pytest.raises(ChartDrawError):
            chart_drawing._element("rect", {"x": bad})


# On every page.

CHART_BODY = "Enrollment by class.\n\n" + fence(json.dumps(chart_data()))


@pytest.mark.parametrize("kind, publish", [("data-bites", published_bite),
                                           ("reports", published_report)])
def test_charts_show_on_the_public_page_the_export_and_the_site_preview(
        client_as, client, tmp_path, kind, publish):
    writer = client_as("admin")
    item_id = publish(writer, body=CHART_BODY)
    path = f"{kind}/{'fall-enrollment' if kind == 'data-bites' else 'factbook'}.html"
    live = client.get(f"/{path}").text
    assert '<figure class="chart-figure">' in content_body(live)
    site = exported(render_site(tmp_path / "site"))
    assert site[path].decode() == live
    shown = preview(writer, kind, item_id, title="Factbook", slug="factbook", body=CHART_BODY)
    assert shown.status_code == 200
    assert '<figure class="chart-figure">' in content_body(shown.text)


def test_the_export_is_still_the_live_site_with_charts(client_as, client, tmp_path):
    analyst = client_as("editor")
    published_bite(analyst, body=CHART_BODY)
    published_bite(analyst, slug="two", title="Two charts", body=CHART_BODY + "\n" + CHART_BODY)
    site = exported(render_site(tmp_path / "site"))
    live = {path.removeprefix("/"): content for path, content in crawl(client).items()}
    assert set(site) == set(live)
    for path, content in site.items():
        assert content == live[path], path


def test_the_editor_shows_a_chart_as_a_locked_block_drawn(client_as):
    from tests.test_t03_data_bites import create_bite
    from tests.test_t13_editor_routes import edit_page, editor_content, textarea
    analyst = client_as("editor")
    item_id = create_bite(analyst, body=CHART_BODY)
    page = edit_page(analyst, "data-bites", item_id)
    content = editor_content(page)
    assert 'data-locked="locked-0"' in content and "chart-figure" in content
    assert '"version"' not in page and "locked-0" in textarea(page)
