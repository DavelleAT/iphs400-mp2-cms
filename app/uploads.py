"""Checking a file uploaded to be a Report's attached file, and the pieces every
upload shares (app.chart_images uses them too): a safe name from the
uploaded one, and an atomic write.

Only PDFs are accepted (spec #1, story 27). The filename's extension and the
browser's declared type must both say PDF, and then the bytes themselves must
look like a PDF: the browser's word is never enough. The uploaded filename is
kept only as a sanitized display name. Storage paths are built from the
Report's id, never from anything the uploader sent.
"""
from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

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


def safe_stem(stem: str, fallback: str) -> str:
    """A safe name from an uploaded name's stem: ASCII letters, digits,
    hyphens, and underscores only, so no path separators, dots, quotes, or
    control characters survive. `fallback` if nothing does."""
    ascii_stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9_-]+", "-", ascii_stem).strip("-_")[:100] or fallback


def sanitize_filename(stem: str) -> str:
    """A safe display name for a Report's PDF, from the uploaded name (without
    its extension)."""
    return f"{safe_stem(stem, 'report')}.pdf"


def split_filename(filename: str) -> tuple[str, str]:
    """(stem, lowercased extension) of an uploaded filename; the extension is
    "" if there is none. A browser sends a bare name, but anyone can send a
    path, so only its last part counts."""
    base = re.split(r"[\\/]", filename)[-1]
    stem, dot, extension = base.rpartition(".")
    return (stem, extension.lower()) if dot else (base, "")


def read_pdf(upload: UploadFile | None) -> Pdf | None:
    """The upload as a checked PDF, or None if no file was chosen. ContentError,
    with a message safe to show, if it is not an acceptable PDF."""
    if upload is None or not upload.filename:
        return None
    stem, extension = split_filename(upload.filename)
    if extension != "pdf" or upload.content_type not in _DECLARED_TYPES:
        raise ContentError("Only PDF files can be attached.")
    data = upload.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ContentError(f"That file is over the {MAX_BYTES // MIB} MB limit.")
    if not (data.startswith(_HEADER) and _EOF_MARKER in data[-_EOF_WINDOW:]):
        raise ContentError("That file is not a valid PDF.")
    return Pdf(sanitize_filename(stem), data)


def write_atomically(path: Path, data: bytes) -> None:
    """Replace `path` in one step, so a failed write never leaves half a file.
    The temporary file ends in .part while it is written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
