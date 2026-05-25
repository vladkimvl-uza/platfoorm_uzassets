"""Pure helpers + constants for Attachments."""
from __future__ import annotations

import mimetypes
import uuid as _uuid

from fastapi import HTTPException, UploadFile, status as http_status

from app.models.user import User


MAX_SIZE_BYTES = 25 * 1024 * 1024

ALLOWED_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "image/png", "image/jpeg", "image/webp",
    "application/zip", "application/x-zip-compressed",
    "text/plain", "text/csv",
}


def is_admin(user: User) -> bool:
    return bool(getattr(user, "is_owner", False) or getattr(user, "is_admin", False))


def validate_upload(file: UploadFile, size_bytes: int) -> str:
    if size_bytes > MAX_SIZE_BYTES:
        raise HTTPException(
            http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"file too large ({size_bytes} > {MAX_SIZE_BYTES})",
        )
    mime = (
        file.content_type
        or mimetypes.guess_type(file.filename or "")[0]
        or "application/octet-stream"
    )
    if mime not in ALLOWED_MIMES:
        raise HTTPException(
            http_status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"mime type '{mime}' is not allowed",
        )
    return mime


def make_key(prefix: str, *parts: str, filename: str) -> str:
    """Storage key with random UUID prefix (prevents enumeration + clash)."""
    safe_name = "".join(
        c for c in (filename or "file") if c.isalnum() or c in (".", "-", "_")
    )[:120]
    suffix = _uuid.uuid4().hex
    parts_clean = "/".join(p for p in parts if p)
    return f"{prefix}/{parts_clean}/{suffix}-{safe_name}"
