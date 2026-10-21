"""S1: the direct-URL access matrix (SECURITY-CHECKLIST #10, MP2 rubric D3).

The routes come from the app's router, not a hand-written list: every route
whose dependency tree includes `require_director`, whether on the route or
on its router, is Director-only. A new route marked the same way is tested
here with no edit. For each one, an Analyst gets 403 and an anonymous visitor
is sent to login.
"""
from __future__ import annotations

import re

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute

from app import data_bites, reports
from app.auth import require_director
from app.main import create_app
from tests.conftest import DEMO_USERS, csrf_from, user_id


def _depends_on(dependant, marker) -> bool:
    return any(dep.call is marker or _depends_on(dep, marker)
               for dep in dependant.dependencies)


def _every_route(routes):
    """The app's routes, with included routers opened up: FastAPI 0.141 keeps
    each include_router() as one wrapper holding its original router."""
    for route in routes:
        if hasattr(route, "original_router"):
            yield from _every_route(route.original_router.routes)
        else:
            yield route


def director_only_routes(app: FastAPI) -> list[tuple[str, str]]:
    """(method, path) for every route that depends on require_director."""
    return sorted((method, route.path)
                  for route in _every_route(app.routes)
                  if isinstance(route, APIRoute) and _depends_on(route.dependant, require_director)
                  for method in route.methods)


ROUTES = director_only_routes(create_app())


@pytest.fixture
def seeded_ids(client_as) -> dict[str, str]:
    """A real id for each path parameter, so a route answers 403, not 404 or 422."""
    director = client_as("admin")
    author = int(user_id(director, DEMO_USERS["editor"]["email"]))
    return {
        "bite_id": str(data_bites.create("Matrix bite", "matrix-bite", "Body.", author)),
        "report_id": str(reports.create("Matrix report", "matrix-report", "Body.", author)),
        "user_id": str(author),
    }


def _url(path: str, ids: dict[str, str]) -> str:
    # An id parameter no fixture knows still gets a well-formed integer: the
    # access check runs before the route looks anything up.
    return re.sub(r"\{(\w+)(?::\w+)?\}", lambda m: ids.get(m.group(1), "1"), path)


def test_the_routes_are_generated_from_the_router():
    # Not the list under test (that is ROUTES, from the router): a floor of
    # known Director-only routes, one or two per router, so a route that loses
    # its marker drops out of ROUTES and fails here instead of going untested.
    for known in [("GET", "/admin/users"), ("POST", "/admin/users/{user_id}/role"),
                  ("GET", "/admin/homepage"), ("POST", "/admin/homepage"),
                  ("GET", "/admin/data-bites/{bite_id}/delete"),
                  ("GET", "/admin/reports/{report_id}/delete"),
                  ("POST", "/admin/reports/{report_id}/publish")]:
        assert known in ROUTES, f"{known} is no longer Director-only"
    assert len(ROUTES) >= 12


def test_a_new_route_marked_the_same_way_is_collected_with_no_edit():
    app = create_app()
    app.add_api_route("/admin/scratch-check", lambda: "ok",
                      dependencies=[Depends(require_director)])
    assert ("GET", "/admin/scratch-check") in director_only_routes(app)
    assert ("GET", "/admin/scratch-check") not in ROUTES


@pytest.mark.parametrize("method, path", ROUTES)
def test_an_analyst_is_refused(client_as, seeded_ids, method, path):
    analyst = client_as("editor")
    # The Analyst's own valid CSRF token, so a 403 here is the access check,
    # not the CSRF check.
    data = {"csrf_token": csrf_from(analyst.get("/admin").text)} if method == "POST" else None
    response = analyst.request(method, _url(path, seeded_ids), data=data,
                               follow_redirects=False)
    assert response.status_code == 403 or (
        response.status_code in (302, 303) and response.headers["location"] != "/admin/"
    ), f"{method} {path} answered {response.status_code}"
    assert "CSRF" not in response.text


@pytest.mark.parametrize("method, path", ROUTES)
def test_an_anonymous_visitor_is_sent_to_login(client, seeded_ids, method, path):
    response = client.request(method, _url(path, seeded_ids), follow_redirects=False)
    assert response.status_code in (302, 303, 307), f"{method} {path} answered {response.status_code}"
    assert response.headers["location"].endswith("/login")
