"""File storage abstraction (Pack 149).

Pick backend via env:
  STORAGE_BACKEND=local   — files on disk under STORAGE_LOCAL_ROOT (dev default)
  STORAGE_BACKEND=s3      — S3-compatible object storage (prod)

Env vars (s3 mode):
  STORAGE_S3_ENDPOINT_URL    — e.g. https://s3.uzcloud.uz
  STORAGE_S3_BUCKET          — bucket name
  STORAGE_S3_REGION          — region code (default: us-east-1)
  STORAGE_S3_ACCESS_KEY      — IAM access key id
  STORAGE_S3_SECRET_KEY      — IAM secret access key
  STORAGE_S3_FORCE_PATH_STYLE — "true" for non-AWS S3 (MinIO, uzcloud)

Usage:
    from app.services.storage import get_storage
    s = get_storage()
    key = await s.upload("attachments/<co>/<year>/<task_id>/<uuid>.<ext>",
                          data=b"...", mime_type="application/pdf")
    url = await s.signed_url(key, ttl_seconds=300)
"""
from __future__ import annotations

import os
from functools import lru_cache

from .base import StorageBackend, StorageError
from .local import LocalStorage
from .s3 import S3Storage


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    """Resolve and cache the configured storage backend."""
    backend = (os.environ.get("STORAGE_BACKEND") or "local").lower()
    if backend == "s3":
        return S3Storage(
            endpoint_url=os.environ.get("STORAGE_S3_ENDPOINT_URL", ""),
            bucket=os.environ.get("STORAGE_S3_BUCKET", ""),
            region=os.environ.get("STORAGE_S3_REGION", "us-east-1"),
            access_key=os.environ.get("STORAGE_S3_ACCESS_KEY", ""),
            secret_key=os.environ.get("STORAGE_S3_SECRET_KEY", ""),
            force_path_style=(os.environ.get("STORAGE_S3_FORCE_PATH_STYLE", "true").lower() == "true"),
        )
    return LocalStorage(
        root=os.environ.get("STORAGE_LOCAL_ROOT", "/app/uploads"),
    )


__all__ = ["StorageBackend", "StorageError", "get_storage"]
