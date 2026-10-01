"""Homepage settings: the homepage's headline, the accent that ends it, its
intro, and up to four Key figures (spec #22).

They are settings, not content: one row, no Draft, edited by the Director
only (the routes enforce that), and on the public site from the next
`cms publish`, like a change to the nav. Everything is plain text, escaped
where it is shown. A fresh database is seeded with SAMPLE, so a new site has
a homepage to look at; the Director replaces its figures with real ones.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from dataclasses import asdict, dataclass

from app import db
from app.content import one_line

FIGURES_MAX = 4
# Each field's limit in characters, the Key figures' by part.
LIMITS = {"headline": 80, "headline_accent": 60, "intro": 300,
          "value": 16, "label": 40, "note": 40}


class SettingsError(ValueError):
    """A setting broke a rule; the message is safe to show. `field` is the
    form field it is about, e.g. "intro" or "figure_label_2"."""

    def __init__(self, message: str, field: str):
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class KeyFigure:
    value: str  # e.g. "1,805"
    label: str  # what it counts, e.g. "Students enrolled"
    note: str   # optional: when or of whom, e.g. "Fall 2026 census"


@dataclass(frozen=True)
class Homepage:
    headline: str
    headline_accent: str  # shown after the headline, in bright purple
    intro: str
    key_figures: tuple[KeyFigure, ...]


SAMPLE = Homepage(
    headline="The college's numbers,", headline_accent="the day they're final.",
    intro="Enrollment, retention, outcomes and survey results from Kenyon's "
          "Office of Institutional Research.",
    key_figures=(KeyFigure("1,805", "Students enrolled", "Fall 2026 census"),
                 KeyFigure("91%", "First-year retention", "Class entering 2025"),
                 KeyFigure("10:1", "Student–faculty ratio", "Fall 2026"),
                 KeyFigure("87%", "Six-year graduation", "Class entering 2020")))

def _row(settings: Homepage) -> tuple[str, str, str, str]:
    return (settings.headline, settings.headline_accent, settings.intro,
            json.dumps([asdict(figure) for figure in settings.key_figures]))


def seed(conn: sqlite3.Connection) -> None:
    """Put SAMPLE in the table if it has no row yet (db.init_db)."""
    conn.execute("INSERT OR IGNORE INTO homepage"
                 " (id, headline, headline_accent, intro, key_figures)"
                 " VALUES (1, ?, ?, ?, ?)", _row(SAMPLE))


def get() -> Homepage:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM homepage WHERE id = 1").fetchone()
    return Homepage(row["headline"], row["headline_accent"], row["intro"],
                    tuple(KeyFigure(**figure) for figure in json.loads(row["key_figures"])))


def _text(form: Mapping[str, str], field: str, limit: str, what: str) -> str:
    """A field's text as saved, its runs of whitespace as single spaces."""
    text = one_line(str(form.get(field, "")))
    if len(text) > LIMITS[limit]:
        raise SettingsError(f"Keep {what} to {LIMITS[limit]} characters or fewer; "
                            f"it has {len(text)}.", field)
    return text


def from_form(form: Mapping[str, str]) -> Homepage:
    """The settings a posted form gives: headline, headline_accent, intro,
    and figure_value_<n>, figure_label_<n>, figure_note_<n> for n from 1 to
    FIGURES_MAX. A blank Key figure row is dropped and the rest close up; a
    row with a value needs a label, and the other way round. SettingsError
    on the first field that breaks a rule."""
    headline = _text(form, "headline", "headline", "the headline")
    if not headline:
        raise SettingsError("Enter a headline.", "headline")
    accent = _text(form, "headline_accent", "headline_accent", "the accent")
    intro = _text(form, "intro", "intro", "the intro")
    figures = []
    for n in range(1, FIGURES_MAX + 1):
        value, label, note = (_text(form, f"figure_{part}_{n}", part, f"a figure's {part}")
                              for part in ("value", "label", "note"))
        if not (value or label or note):
            continue
        if not value:
            raise SettingsError("Enter the figure itself, e.g. 1,805.", f"figure_value_{n}")
        if not label:
            raise SettingsError("Say what the figure counts, e.g. Students enrolled.",
                                f"figure_label_{n}")
        figures.append(KeyFigure(value, label, note))
    return Homepage(headline, accent, intro, tuple(figures))


def form_of(settings: Homepage) -> dict[str, str]:
    """`settings` as the edit form's fields, the inverse of from_form; a
    row past its Key figures is blank."""
    form = {"headline": settings.headline, "headline_accent": settings.headline_accent,
            "intro": settings.intro}
    for n in range(1, FIGURES_MAX + 1):
        figure = (settings.key_figures[n - 1] if n <= len(settings.key_figures)
                  else KeyFigure("", "", ""))
        form.update({f"figure_value_{n}": figure.value, f"figure_label_{n}": figure.label,
                     f"figure_note_{n}": figure.note})
    return form


def save(settings: Homepage) -> None:
    with db.connect() as conn:
        conn.execute("UPDATE homepage SET headline = ?, headline_accent = ?, intro = ?,"
                     " key_figures = ?, updated_at = datetime('now') WHERE id = 1",
                     _row(settings))
