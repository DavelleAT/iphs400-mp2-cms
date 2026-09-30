"""What the Data Bite and Report routes share about a body posted from their
edit and create forms, with or without the Editor (app.editor)."""
from __future__ import annotations

from fastapi import HTTPException

from app import editor
from app.content import ContentError
from app.markdown_form import ImageName


def posted(body: str, body_html: str | None, body_dirty: str) -> editor.Posted:
    """The form's body fields: `body_html` and `body_dirty` only if the
    Editor's script ran; `body` is the textarea's Markdown."""
    return editor.Posted(body=body, body_html=body_html, body_dirty=body_dirty == "1")


def previewed(body: editor.Posted, stored: str | None, image_name: ImageName | None) -> str:
    """The body a Site preview shows for a post: what saving it would save.
    400 if it can't be saved."""
    try:
        return editor.saved_body(body, stored, image_name)
    except ContentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
