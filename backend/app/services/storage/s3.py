"""S3-compatible backend. Works with AWS S3, MinIO, uzcloud Object Storage.

Configuration via env (see __init__.py for full list).

Notes:
  - All ops use aiobotocore (async) — no thread-pool overhead.
  - Server-side encryption: enable via STORAGE_S3_SSE=AES256 in env.
  - Bucket should have public access BLOCKED — all reads go through
    signed URLs (5 min TTL by default).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from .base import StorageBackend, StorageError, StoredObject

log = logging.getLogger(__name__)


class S3Storage(StorageBackend):
    def __init__(
        self,
        endpoint_url: str,
        bucket: str,
        region: str,
        access_key: str,
        secret_key: str,
        force_path_style: bool = True,
    ):
        if not bucket or not access_key or not secret_key:
            raise StorageError("S3 backend requires bucket + access/secret key")
        self.endpoint_url = endpoint_url or None  # None for AWS-native
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.force_path_style = force_path_style
        self.sse = os.environ.get("STORAGE_S3_SSE", "").strip() or None

    def _client_kwargs(self):
        kw = dict(
            region_name=self.region,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
        )
        if self.endpoint_url:
            kw["endpoint_url"] = self.endpoint_url
        return kw

    async def upload(self, key: str, data: bytes, *, mime_type: Optional[str] = None) -> StoredObject:
        from aiobotocore.session import get_session
        sess = get_session()
        async with sess.create_client("s3", **self._client_kwargs()) as client:
            put_kwargs = dict(Bucket=self.bucket, Key=key, Body=data)
            if mime_type:
                put_kwargs["ContentType"] = mime_type
            if self.sse:
                put_kwargs["ServerSideEncryption"] = self.sse
            await client.put_object(**put_kwargs)
        return StoredObject(key=key, size_bytes=len(data), mime_type=mime_type)

    async def download(self, key: str) -> bytes:
        from aiobotocore.session import get_session
        from botocore.exceptions import ClientError
        sess = get_session()
        async with sess.create_client("s3", **self._client_kwargs()) as client:
            try:
                resp = await client.get_object(Bucket=self.bucket, Key=key)
            except ClientError as e:
                raise StorageError(f"S3 get failed: {e}")
            body = await resp["Body"].read()
        return body

    async def delete(self, key: str) -> None:
        from aiobotocore.session import get_session
        sess = get_session()
        async with sess.create_client("s3", **self._client_kwargs()) as client:
            await client.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        from aiobotocore.session import get_session
        from botocore.exceptions import ClientError
        sess = get_session()
        async with sess.create_client("s3", **self._client_kwargs()) as client:
            try:
                await client.head_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError:
                return False

    async def signed_url(self, key: str, ttl_seconds: int = 300) -> str:
        from aiobotocore.session import get_session
        sess = get_session()
        async with sess.create_client("s3", **self._client_kwargs()) as client:
            url = await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=int(ttl_seconds),
            )
        return url
