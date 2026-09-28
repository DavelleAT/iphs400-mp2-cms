"""Checking a file uploaded to be a Report's attachment.

Only PDFs are accepted (spec #1, story 27). The filename's extension and the
browser's declared type must both say PDF, and then the bytes themselves must
look like a PDF: the browser's word is never enough. The uploaded filename is
kept only as a sanitized display name. Storage paths are built from the
Report's id, never from anything the uploader sent.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from fastapi import UploadFile

from app.content import ContentError

MIB = 1024 * 1024
MAX_BYTES = 20 * MIB
_DECLARED_TYPES = {"application/pdf", "application/x-pdf"}
# A PDF starts with this header, and its end-of-file marker sits at (or,
# allowing for trailing whitespace or junk, near) the end.
_HEADER = b"%PDF-"
_EOF_MARKER = b"%%EOF"
_EOF_WINDOW = 1024


@dataclass(frozen=True)
class Pdf:
    name: str   # sanitized, for display and the download's filename
    data: bytes


def sanitize_filename(stem: str) -> str:
    """A safe display name from the uploaded name (without its extension):
    ASCII letters, digits, hyphens, and underscores only, so no path
    separators, dots, quotes, or control characters survive."""
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", ascii_stem).strip("-_")[:100]
    return f"{safe or 'report'}.pdf"


def read_pdf(upload: UploadFile | None) -> Pdf | None:
    """The upload as a checked PDF, or None if no file was chosen. ContentError,
    with a message safe to show, if it is not an acceptable PDF."""
    if upload is None or not upload.filename:
        return None
    # A browser sends a bare name, but anyone can send a path.
    base = re.split(r"[\\/]", upload.filename)[-1]
    stem, dot, extension = base.rpartition(".")
    if not dot or extension.lower() != "pdf" or upload.content_type not in _DECLARED_TYPES:
        raise ContentError("Only PDF files can be attached.")
    data = upload.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ContentError(f"That file is over the {MAX_BYTES // MIB} MB limit.")
    if not (data.startswith(_HEADER) and _EOF_MARKER in data[-_EOF_WINDOW:]):
        raise ContentError("That file is not a valid PDF.")
    return Pdf(sanitize_filename(stem), data)
