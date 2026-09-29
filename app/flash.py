"""Confirmations: a one-line success message that survives the redirect after a
state-changing admin action.

A route calls confirm() after the action succeeds and before it redirects. The
message waits in the session (a signed cookie, so it must never hold anything
sensitive: pass fixed text, not titles, emails, or filenames) until the next
admin page renders it, once, through the confirmation() template global.
"""
from __future__ import annotations

from fastapi import Request
from jinja2 import pass_context

_KEY = "confirmation"

# Publishing changes a row's status, not the exported site; say so.
SITE_NOTE = " The public site updates at the next cms publish."


def confirm(request: Request, message: str) -> None:
    request.session[_KEY] = message


@pass_context
def confirmation(context) -> str | None:
    """The waiting message, removed so it shows once. Admin pages only: the
    base template calls this only when a signed-in user is in the context."""
    return context["request"].session.pop(_KEY, None)
