"""T17: Chart builder (issue #20). The route the builder draws its live
chart with: it requires login and CSRF, saves nothing, draws with T16's
server rendering, and returns T16's errors as field-level messages."""
from __future__ import annotations

import json
import re

import pytest

from app import chart_drawing, chart_svg, charts, data_bites, reports
from app.rendering import render_markdown
from tests.conftest import csrf_from
from tests.test_t16_charts import fence, series, source

PATH = "/admin/charts/preview"


def preview(c, text: str, *, with_csrf: bool = True):
    data = {"chart": text}
    if with_csrf:
        data["csrf_token"] = csrf_from(c.get("/admin").text)
    return c.post(PATH, data=data, follow_redirects=False)


def answer(c, text: str) -> dict:
    response = preview(c, text)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    return response.json()


@pytest.fixture
def analyst(client_as):
    return client_as("editor")


def test_it_requires_login(client):
    response = client.post(PATH, data={"chart": source()}, follow_redirects=False)
    assert (response.status_code, response.headers["location"]) == (303, "/login")


def test_it_requires_a_csrf_token(analyst):
    assert preview(analyst, source(), with_csrf=False).status_code == 403


@pytest.mark.parametrize("role", ["editor", "admin"])
def test_a_valid_chart_is_drawn_as_the_public_page_draws_it(client_as, role):
    text = source(type="line", categories=["2023", "2024", "2025"],
                  series=[series("91%", "<10", "", name=f"S{i}") for i in range(4)])
    found = answer(client_as(role), text)
    assert found["errors"] == []
    assert found["chart"] == charts.parse(text).canonical()
    public = str(render_markdown(fence(found["chart"]))).strip()

    def without_ids(html: str) -> str:
        return re.sub(r"chart-[0-9a-f]{32}-[0-9]+-title", "ID", html)

    assert without_ids(found["drawing"]) == without_ids(public)
    assert chart_svg.TITLE_ID.search(found["drawing"])


def test_each_error_comes_back_with_its_field(analyst):
    found = answer(analyst, source(title="", series=[series("482", "abc", name="Fall")]))
    assert found["drawing"] is None and found["chart"] is None
    assert found["errors"] == [
        {"field": "title", "message": "Can't be blank"},
        {"field": "series.0.values.1", "message": "'abc' isn't a number"}]


def test_a_whole_chart_error_comes_back_with_its_field(analyst):
    found = answer(analyst, source(series=[series("$1", "2%")]))
    assert found["errors"] == [{"field": "series.0.values.1",
                                "message": "'2%' is in %, but the chart's units are $"}]


def test_an_error_in_no_one_field_has_none(analyst):
    found = answer(analyst, "{")
    assert [error["field"] for error in found["errors"]] == [None]
    assert found["errors"][0]["message"].startswith("Its data can't be read")


def test_a_long_category_suggests_a_horizontal_bar_chart_even_with_errors(analyst):
    text = source(title="", categories=["First-year", "Students living off campus"])
    assert answer(analyst, text)["suggestion"] == "hbar"
    assert answer(analyst, source())["suggestion"] is None


def test_writer_text_is_only_escaped_text_in_the_drawing(analyst):
    hostile = '"><svg onload=alert(1)></title>&'
    found = answer(analyst, source(title=hostile, source="<script>x</script>"))
    assert "<script>" not in found["drawing"] and "<svg onload" not in found["drawing"]
    assert "&lt;script&gt;x&lt;/script&gt;" in found["drawing"]
    assert "&quot;&gt;&lt;svg onload=alert(1)&gt;&lt;/title&gt;&amp;" in found["drawing"]


def test_it_saves_nothing(analyst, tmp_path):
    before = ([dict(row) for row in data_bites.list_all()],
              [dict(row) for row in reports.list_all()])
    answer(analyst, source())
    answer(analyst, source(title=""))
    after = ([dict(row) for row in data_bites.list_all()],
             [dict(row) for row in reports.list_all()])
    assert before == after


def test_a_missing_chart_field_is_an_error_not_a_crash(analyst):
    token = csrf_from(analyst.get("/admin").text)
    response = analyst.post(PATH, data={"csrf_token": token}, follow_redirects=False)
    assert response.status_code == 200
    assert [error["field"] for error in response.json()["errors"]] == [None]


def test_the_answer_is_json_the_page_can_trust(analyst):
    """Everything but the drawing is data; the drawing is only T16's."""
    found = answer(analyst, source())
    assert set(found) == {"errors", "drawing", "chart", "suggestion"}
    assert json.loads(found["chart"])["title"] == "Fall enrollment by class"


@pytest.mark.parametrize("path", ["/admin/data-bites", "/admin/reports"])
def test_the_editor_is_told_where_to_draw_charts(analyst, path):
    from tests.test_t03_data_bites import create_bite
    pages = [analyst.get(f"{path}/new").text]  # the create form's own page (T22)
    if path == "/admin/data-bites":
        pages.append(analyst.get(f"{path}/{create_bite(analyst)}").text)
    for page in pages:
        assert f'data-chart-preview="{PATH}"' in page
