"""Pure helpers + constants for Attachments."""
from __future__ import annotations

import io
import mimetypes
import uuid as _uuid
import zipfile

from fastapi import HTTPException, UploadFile
from fastapi import status as http_status

from app.models.user import User

MAX_SIZE_BYTES = 25 * 1024 * 1024
# Анти-zip-бомба: лимиты распакованного размера и степени сжатия.
MAX_UNCOMPRESSED_BYTES = 600 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200

ALLOWED_MIMES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    # Макро-Excel (.xlsm) и бинарный (.xlsb) — zip-контейнеры OOXML; отдаются
    # только на скачивание (signed URL), на сервере не исполняются.
    "application/vnd.ms-excel.sheet.macroEnabled.12",
    "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "image/png", "image/jpeg", "image/webp",
    "application/zip", "application/x-zip-compressed",
    "text/plain", "text/csv",
}

# Сигнатуры (magic bytes) — проверка, что СОДЕРЖИМОЕ соответствует заявленному
# MIME (защита от подмены типа: напр. .exe, переименованного в .pdf).
_ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")  # zip + OOXML (docx/xlsx/pptx)
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"            # legacy doc/xls/ppt (OLE2)
_OOXML_MIMES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
    "application/vnd.ms-excel.sheet.binary.macroEnabled.12",
}
_ZIP_MIMES = {"application/zip", "application/x-zip-compressed"} | _OOXML_MIMES
_OLE_MIMES = {"application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint"}
_SIGNATURES = {
    "application/pdf": (b"%PDF",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}
_TEXT_MIMES = {"text/plain", "text/csv"}


def is_admin(user: User) -> bool:
    return bool(getattr(user, "is_owner", False) or getattr(user, "is_admin", False))


def _content_matches(mime: str, data: bytes) -> bool:
    """magic-байты содержимого соответствуют заявленному MIME?"""
    if not data:
        return False
    head = data[:16]
    if mime in _ZIP_MIMES:
        return head.startswith(_ZIP_MAGIC)
    if mime in _OLE_MIMES:
        return head.startswith(_OLE_MAGIC)
    if mime == "image/webp":
        return head[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if mime in _TEXT_MIMES:
        return b"\x00" not in data[:512]  # текст не должен содержать NUL-байты
    sigs = _SIGNATURES.get(mime)
    if sigs:
        return head.startswith(sigs)
    return True  # неизвестный (но разрешённый) тип — сигнатуру не проверяем


def _zip_bomb_safe(data: bytes) -> bool:
    """Для zip-содержимого — распакованный размер и ratio в пределах."""
    if not data[:4].startswith(_ZIP_MAGIC):
        return True  # не zip
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            infos = zf.infolist()
            total_uncompressed = sum(i.file_size for i in infos)
            total_compressed = sum(i.compress_size for i in infos) or 1
    except Exception:
        return True  # битый zip отсечёт проверка сигнатуры / парсер приложения
    if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
        return False
    if total_uncompressed / total_compressed > MAX_COMPRESSION_RATIO:
        return False
    return True


def validate_upload(file: UploadFile, data: bytes) -> str:
    """Валидация загрузки: размер → разрешённый MIME → соответствие содержимого
    (magic-байты) → защита от zip-бомбы. Возвращает проверенный MIME."""
    size_bytes = len(data)
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
    if not _content_matches(mime, data):
        raise HTTPException(
            http_status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "file content does not match the declared type",
        )
    if not _zip_bomb_safe(data):
        raise HTTPException(
            http_status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "archive too large when decompressed (possible zip bomb)",
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
