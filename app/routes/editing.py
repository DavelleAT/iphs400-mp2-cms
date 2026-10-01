"""What the Data Bite and Report routes share about a body posted from their
edit and create forms, with or without the Editor (app.editor)."""
from __future__ import annotations

import sqlite3

from fastapi import Form, HTTPException, Request

from app import editor, site_links
from app.content import ContentError, StaleItem
from app.markdown_form import ImageName
from app.templating import templates


def posted(body: str = Form(""), body_html: str | None = Form(None),
           body_dirty: str = Form("0")) -> editor.Posted:
    """The form's body fields, as a route dependency: `body_html` and
    `body_dirty` only if the Editor's script ran; `body` is the textarea's
    Markdown."""
    return editor.Posted(body=body, body_html=body_html, body_dirty=body_dirty == "1")


def image_links(request: Request, route: str, **item_id: int) -> editor.ImageLinks:
    """How the Editor shows an item's chart images: from `route`, the admin
    route that serves them, draft or not."""
    image = str(request.app.url_path_for(route, name="x", **item_id))
    return editor.image_links(image.removesuffix("x"))


def body_images(links: editor.ImageLinks, names) -> list[dict]:
    """The item's chart images, for the Editor's "Insert image" to list:
    each one's name, and the admin src it is shown from."""
    return [{"name": name, "src": links.src(name)} for name in names]


def error_for(exc: ContentError | None) -> dict:
    """A refused save's message for its page: `error`, and `error_field`, the
    field it is shown beside, or None to show it above the form."""
    return {"error": None if exc is None else str(exc),
            "error_field": None if exc is None else exc.field}


def refused_status(exc: ContentError) -> int:
    """A refused save's status: 409 if the item changed since its form was
    opened, else 400."""
    return 409 if isinstance(exc, StaleItem) else 400


def previewed(body: editor.Posted, stored: str | None, image_name: ImageName | None) -> str:
    """The body a Site preview shows for a post: what saving it would save.
    400 if it can't be saved."""
    try:
        return editor.saved_body(body, stored, image_name)
    except ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


def site_links_for(body: str) -> dict:
    """What the Editor's link dialog and markers need, for a form whose full
    body is `body`: every item it may link to, and the state of each site
    link in the body that won't be a link on the site."""
    return {"site_items": site_links.choices(), "link_states": site_links.unresolved(body)}


def confirm_delete(request: Request, user: sqlite3.Row, item: sqlite3.Row, kind: str, *,
                   back: str):
    """The page before a delete (Director only), which posts to its own
    path: the items whose bodies link to `item`, a `kind` of item, and whose
    links will be their text once it is gone. The delete isn't blocked."""
    noun = site_links.NOUNS[kind]
    return templates.TemplateResponse(
        request, "admin/confirm_delete.html",
        {"title": f"Delete {noun}", "home_path": "/admin", "user": user, "noun": noun,
         "item": item, "action": request.url.path, "back": back,
         "linked_from": site_links.linked_from(site_links.reference(kind, item["ref"]))})
