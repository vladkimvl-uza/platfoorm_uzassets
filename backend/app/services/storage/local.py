"""Local-disk storage. Used in dev and as fallback if S3 unavailable.

Keys are flattened to filesystem paths under STORAGE_LOCAL_ROOT. The
signed_url() method returns an internal endpoint-relative URL — the
download endpoint must verify the JWT signature before serving the file.

Security:
  - Path traversal blocked via _safe_key()
  - File mode 0o600 (owner-only read)
  - Subdirectory permissions 0o700
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
from pathlib import Path
from time import time
from typing import Optional

from .base import StorageBackend, StorageError, StoredObject

_KEY_SAFE = re.compile(r"^[A-Za-z0-9_\-/.]+$")


def _safe_key(key: str) -> str:
    if not key or len(key) > 1024:
        raise StorageError("invalid key (empty or too long)")
    if ".." in key or key.startswith("/"):
        raise StorageError("invalid key (path traversal)")
    if not _KEY_SAFE.match(key):
        raise StorageError(f"invalid key chars: {key!r}")
    return key


def _hmac_sig(key: str, exp_unix: int, secret: bytes) -> str:
    msg = f"{key}|{exp_unix}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:32]


class LocalStorage(StorageBackend):
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except PermissionError:
            pass
        # Re-use audit HMAC key for signed local URLs — separate key recommended
        # in real deploys via STORAGE_URL_SIGNING_SECRET env var.
        secret = os.environ.get("STORAGE_URL_SIGNING_SECRET", "").encode()
        if not secret:
            # Fall back to audit key (already required to exist on disk in prod).
            try:
                with open(os.environ.get("AUDIT_HMAC_SECRET_PATH", "/app/keys/audit_hmac.key"), "rb") as f:
                    secret = f.read().strip()
            except FileNotFoundError:
                secret = b"dev-only-signing-secret-DO-NOT-USE-IN-PROD"
        self._sig_secret = secret

    def _full(self, key: str) -> Path:
        return self.root / _safe_key(key)

    async def upload(self, key: str, data: bytes, *, mime_type: Optional[str] = None) -> StoredObject:
        p = self._full(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(p.parent, 0o700)
        except PermissionError:
            pass

        def _write():
            with open(p, "wb") as f:
                f.write(data)
            try:
                os.chmod(p, 0o600)
            except PermissionError:
                pass

        await asyncio.get_event_loop().run_in_executor(None, _write)
        return StoredObject(key=key, size_bytes=len(data), mime_type=mime_type)

    async def download(self, key: str) -> bytes:
        p = self._full(key)
        if not p.exists():
            raise StorageError(f"not found: {key}")
        def _read():
            with open(p, "rb") as f:
                return f.read()
        return await asyncio.get_event_loop().run_in_executor(None, _read)

    async def delete(self, key: str) -> None:
        p = self._full(key)
        if p.exists():
            await asyncio.get_event_loop().run_in_executor(None, p.unlink)

    async def exists(self, key: str) -> bool:
        return self._full(key).exists()

    async def signed_url(self, key: str, ttl_seconds: int = 300) -> str:
        _safe_key(key)
        exp = int(time()) + int(ttl_seconds)
        sig = _hmac_sig(key, exp, self._sig_secret)
        return f"/api/attachments/raw/{key}?exp={exp}&sig={sig}"

    def verify_signed(self, key: str, exp: int, sig: str) -> bool:
        if time() > exp:
            return False
        expected = _hmac_sig(_safe_key(key), exp, self._sig_secret)
        return hmac.compare_digest(expected, sig)
