"""The Jinja environment the admin console renders with."""
from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app import settings
from app.auth import csrf_token
from app.users import ROLE_LABELS

templates = Jinja2Templates(directory=str(settings.TEMPLATES))
templates.env.globals["csrf_token"] = csrf_token
templates.env.filters["role_label"] = ROLE_LABELS.get
