"""Data Bites: short, dated Markdown items.

Any Analyst or Director may create, edit, publish, and unpublish any Data Bite,
and add or remove its chart images (shift continuity, ADR-003, ADR-004); only
a Director may delete one, which the routes enforce. Editing never changes the
author or created_at. Deleting a Data Bite deletes its images.

Public-facing code reads Data Bites only through `list_published` and
`get_published`, so a draft cannot leak through it.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app import chart_images
from app.content import ContentTable

_TABLE = ContentTable("data_bites", "Data Bite", "data-bite")
_IMAGES = "data-bites"  # the chart_images kind

get = _TABLE.get
list_all = _TABLE.list_all
count_by_status = _TABLE.count_by_status
set_status = _TABLE.set_status
get_published = _TABLE.get_published


def create(title: str, slug: str, body: str, author_id: int, *, summary: str = "") -> int:
    """Create a draft. It starts with no images, even if a deleted Data Bite
    that had its id left some behind (SQLite may reuse the highest id)."""
    return _TABLE.create(title, slug, body, author_id, summary=summary,
                         also=lambda conn, bite_id: chart_images.remove_all(_IMAGES, bite_id))


def update(bite_id: int, title: str, slug: str, body: str, *, summary: str = "",
           base: str | None = None) -> bool:
    """Edit title, slug, body, and Summary. False if there is no such Data
    Bite; StaleItem if it has changed since `base` (ContentTable.update)."""
    return _TABLE.update(bite_id, title, slug, body, summary=summary, base=base)


def list_published() -> list[sqlite3.Row]:
    """The public-facing query: published Data Bites only, newest first."""
    return _TABLE.list_published("c.created_at DESC, c.id DESC")


def delete(bite_id: int) -> bool:
    """Delete the Data Bite and its images. False if there is no such Data Bite."""
    if not _TABLE.delete(bite_id):
        return False
    chart_images.remove_all(_IMAGES, bite_id)
    return True


def images(bite_id: int) -> dict[str, Path]:
    """The Data Bite's chart images, {name: where it is stored}, by name."""
    return chart_images.stored(_IMAGES, bite_id)


def add_image(bite_id: int, image: chart_images.Image) -> bool:
    """Add a chart image, or replace the one of the same name. False if there
    is no such Data Bite; ContentError if it already has the most allowed."""
    return _TABLE.touch(bite_id, also=lambda conn, item_id: chart_images.save(
        _IMAGES, item_id, image))


def remove_image(bite_id: int, name: str) -> bool:
    """False if there is no such Data Bite or it has no image of that name."""
    if name not in images(bite_id) or not _TABLE.touch(bite_id):
        return False
    return chart_images.remove(_IMAGES, bite_id, name)
