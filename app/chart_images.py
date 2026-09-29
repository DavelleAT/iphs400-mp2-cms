"""Chart images: the PNG, JPEG, or WebP pictures a Data Bite or Report shows in
its Markdown body as `image:<name>` (ADR-004).

An image belongs to one item, named here by its kind ("data-bites" or
"reports") and id, and is stored at settings.UPLOADS/images/<kind>/<id>/<name>,
outside site/. The files there are the record; there is no table. An image's
name is its upload's filename, sanitized and lowercased, so it is safe in a
path and in a URL, and uploading a name the item already has replaces that
image.

An upload is checked the way app.uploads checks a Report's PDF: the extension
and the browser's declared type must agree, and then the bytes must carry that
format's signature. There is no image library (pyproject.toml is fixed), so
the check is by signature, not by decoding. SVG is refused: it is a document
that can carry script.

Who may add or remove an item's images is decided by that item's module, not
here.
"""
from __future__ import annotations

import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from fastapi.responses import FileResponse

from app import settings, uploads
from app.content import ContentError

MIB = uploads.MIB
MAX_BYTES = 5 * MIB
MAX_PER_ITEM = 10
KINDS = {"data-bites": "Data Bite", "reports": "Report"}  # kind: noun, for messages
# How near the end a format's end marker must be, allowing for trailing bytes.
_TAIL = 1024


@dataclass(frozen=True)
class _Format:
    label: str
    media_type: str
    looks_valid: Callable[[bytes], bool]


def _png(data: bytes) -> bool:
    # The 8-byte signature, and the IEND chunk (with its fixed CRC) at the end.
    return data.startswith(b"\x89PNG\r\n\x1a\n") and b"IEND\xaeB`\x82" in data[-_TAIL:]


def _jpeg(data: bytes) -> bool:
    # Start-of-image, then end-of-image at the end.
    return data.startswith(b"\xff\xd8\xff") and b"\xff\xd9" in data[-_TAIL:]


def _webp(data: bytes) -> bool:
    # A RIFF container of type WEBP, holding at least as many bytes as it says.
    return (data[:4] == b"RIFF" and data[8:12] == b"WEBP"
            and int.from_bytes(data[4:8], "little") + 8 <= len(data))


_PNG = _Format("PNG", "image/png", _png)
_JPEG = _Format("JPEG", "image/jpeg", _jpeg)
_FORMATS = {"png": _PNG, "jpg": _JPEG, "jpeg": _JPEG, "webp": _Format("WebP", "image/webp", _webp)}
# What read() can name an image. Anything else, e.g. from a URL, names none.
_NAME = re.compile(r"[a-z0-9_-]+\.(?:png|jpe?g|webp)")


@dataclass(frozen=True)
class Image:
    name: str   # sanitized: safe in a path and a URL
    data: bytes


def read(upload: UploadFile | None) -> Image:
    """The upload as a checked image. ContentError, with a message safe to
    show, if no file was chosen or it is not an acceptable image."""
    if upload is None or not upload.filename:
        raise ContentError("Choose an image to upload.")
    stem, extension = uploads.split_filename(upload.filename)
    image_format = _FORMATS.get(extension)
    if image_format is None or upload.content_type != image_format.media_type:
        raise ContentError("Only PNG, JPEG, or WebP images can be uploaded.")
    data = upload.file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ContentError(f"That image is over the {MAX_BYTES // MIB} MB limit.")
    if not image_format.looks_valid(data):
        raise ContentError(f"That file is not a valid {image_format.label} image.")
    return Image(f"{uploads.safe_stem(stem, 'chart').lower()}.{extension}", data)


def response(path: Path) -> FileResponse:
    """A stored image, served as its type and never sniffed as anything else."""
    return FileResponse(path, media_type=_FORMATS[path.suffix[1:]].media_type,
                        headers={"X-Content-Type-Options": "nosniff"})


def _folder(kind: str, item_id: int) -> Path:
    """Where an item's images are stored. Built from fixed kinds and the id."""
    if kind not in KINDS:
        raise ValueError(kind)
    return settings.UPLOADS / "images" / kind / str(int(item_id))


def stored(kind: str, item_id: int) -> dict[str, Path]:
    """The item's images, {name: where it is stored}, by name."""
    folder = _folder(kind, item_id)
    if not folder.is_dir():
        return {}
    return {path.name: path for path in sorted(folder.iterdir())
            if _NAME.fullmatch(path.name) and path.is_file()}


def save(kind: str, item_id: int, image: Image) -> None:
    """Add the image to the item, or replace the one of the same name.
    ContentError if that would be one more than MAX_PER_ITEM."""
    existing = stored(kind, item_id)
    if image.name not in existing and len(existing) >= MAX_PER_ITEM:
        raise ContentError(f"This {KINDS[kind]} already has {MAX_PER_ITEM} images, the "
                           "most allowed. Delete one to add another.")
    uploads.write_atomically(_folder(kind, item_id) / image.name, image.data)


def remove(kind: str, item_id: int, name: str) -> bool:
    """False if the item has no image of that name."""
    path = stored(kind, item_id).get(name)
    if path is None:
        return False
    path.unlink(missing_ok=True)
    return True


def remove_all(kind: str, item_id: int) -> None:
    """Remove every image the item has. Raises if one can't be removed, rather
    than leave it for another item that is later given the same id."""
    folder = _folder(kind, item_id)
    if folder.exists():
        shutil.rmtree(folder)
