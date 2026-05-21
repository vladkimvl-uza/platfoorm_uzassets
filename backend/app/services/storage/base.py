"""Storage backend ABC."""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional


class StorageError(RuntimeError):
    pass


@dataclass
class StoredObject:
    key: str
    size_bytes: int
    mime_type: Optional[str]


class StorageBackend(abc.ABC):
    """Abstract storage backend. All paths use forward-slash keys.

    Implementations MUST be safe to call from async code (use thread pool
    if the underlying client is sync — e.g. boto3 → run_in_executor).
    """

    @abc.abstractmethod
    async def upload(
        self,
        key: str,
        data: bytes,
        *,
        mime_type: Optional[str] = None,
    ) -> StoredObject:
        """Store bytes under `key`. Overwrites if exists. Returns metadata."""

    @abc.abstractmethod
    async def download(self, key: str) -> bytes:
        """Fetch the entire object. Raises StorageError if missing."""

    @abc.abstractmethod
    async def delete(self, key: str) -> None:
        """Remove object. No-op if missing."""

    @abc.abstractmethod
    async def exists(self, key: str) -> bool:
        ...

    @abc.abstractmethod
    async def signed_url(self, key: str, ttl_seconds: int = 300) -> str:
        """Time-limited URL for direct browser download.

        Local backend returns an internal /attachments/{key}?sig=... URL that
        an authenticated endpoint validates; S3 returns a presigned URL.
        """
