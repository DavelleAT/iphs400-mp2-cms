"""The Chart builder's live drawing (spec #14, T17). The Editor's "Insert
chart" dialog posts the Chart it holds, as the grammar's JSON, and gets back
its errors by field, or its drawing by T16's server rendering.
Any signed-in user may use it; it saves nothing."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form
from fastapi.responses import JSONResponse

from app import chart_drawing, charts
from app.auth import current_user, require_csrf

router = APIRouter(prefix="/admin/charts", dependencies=[Depends(current_user)])


def _message(error: charts.ChartError) -> str:
    """An error as the dialog shows it, beside its field or cell: the cell
    is the place, so the message needn't name it."""
    return error.short[:1].upper() + error.short[1:]


@router.post("/preview", dependencies=[Depends(require_csrf)])
def preview_chart(chart: str = Form("")):
    """`chart`'s errors, each with its field (app.charts), and the type it
    would be better as; if it has none, its drawing and its canonical form,
    which the dialog inserts into the body."""
    problems = charts.problems(chart)
    drawing = canonical = None
    if not problems:
        parsed = charts.parse(chart)
        canonical = parsed.canonical()
        # Its title's id needs only to be unique on the admin page.
        drawing = chart_drawing.draw(parsed, secrets.token_hex(16), 0)
    return JSONResponse({
        "errors": [{"field": error.field, "message": _message(error)} for error in problems],
        "drawing": drawing, "chart": canonical, "suggestion": charts.suggestion(chart)})
