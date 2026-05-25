"""Storage backend introspection + smoke-test (Pack 149).

No DB access — operates purely on the global `get_storage()` singleton and
environment configuration. Service exists for consistency + future tests.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status as http_status

from app.core.security import _has_permission
from app.models.user import User
from app.services.storage import get_storage, StorageError


log = logging.getLogger(__name__)


def _require_admin(user: User) -> None:
    if user.is_owner:
        return
    if (_has_permission(user, "companies.edit")
        or _has_permission(user, "tasks.manage")):
        return
    raise HTTPException(
        http_status.HTTP_403_FORBIDDEN,
        "Permission required: companies.edit or tasks.manage",
    )


def _redact(s: str) -> str:
    if not s or len(s) < 8:
        return "***" if s else ""
    return s[:4] + "…" + s[-4:]


@dataclass
class StorageAdminService:
    async def status(self, user: User) -> dict:
        _require_admin(user)
        backend_env = (os.environ.get("STORAGE_BACKEND") or "local").lower()
        cfg = {
            "backend": backend_env,
            "local_root": os.environ.get("STORAGE_LOCAL_ROOT") or "/app/uploads",
            "s3_endpoint": os.environ.get("STORAGE_S3_ENDPOINT_URL") or "",
            "s3_bucket": os.environ.get("STORAGE_S3_BUCKET") or "",
            "s3_region": os.environ.get("STORAGE_S3_REGION") or "us-east-1",
            "s3_access_key": _redact(os.environ.get("STORAGE_S3_ACCESS_KEY") or ""),
            "s3_force_path_style": (
                os.environ.get("STORAGE_S3_FORCE_PATH_STYLE", "true").lower() == "true"
            ),
            "s3_sse": os.environ.get("STORAGE_S3_SSE") or "",
        }
        init_ok = True
        init_err: Optional[str] = None
        info: Optional[str] = None
        try:
            storage = get_storage()
            info = type(storage).__name__
        except Exception as e:
            init_ok = False
            init_err = str(e)
        return {
            "config": cfg,
            "backend_class": info,
            "init_ok": init_ok,
            "init_error": init_err,
            "now": datetime.now(timezone.utc).isoformat(),
        }

    async def smoke_test(self, user: User) -> dict:
        _require_admin(user)
        storage = get_storage()
        probe_data = b"UzAssets storage probe " + secrets.token_hex(16).encode()
        key = (
            f"_probe/{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
            f"-{secrets.token_hex(4)}.txt"
        )

        steps: list[dict] = []

        def _step(name: str, ok: bool, ms: float, error: Optional[str] = None, **extra):
            steps.append({"step": name, "ok": ok, "ms": round(ms, 1),
                          "error": error, **extra})

        t0 = time.perf_counter()
        try:
            obj = await storage.upload(key, probe_data, mime_type="text/plain")
            _step("upload", True, (time.perf_counter() - t0) * 1000,
                  key=key, size=obj.size_bytes)
        except StorageError as e:
            _step("upload", False, (time.perf_counter() - t0) * 1000, error=str(e))
            return {"ok": False, "steps": steps, "key": key}

        t1 = time.perf_counter()
        try:
            fetched = await storage.download(key)
            match = fetched == probe_data
            _step("download", True, (time.perf_counter() - t1) * 1000,
                  match=match, bytes=len(fetched))
        except StorageError as e:
            _step("download", False, (time.perf_counter() - t1) * 1000, error=str(e))

        t2 = time.perf_counter()
        try:
            url = await storage.signed_url(key, ttl_seconds=60)
            _step("signed_url", True, (time.perf_counter() - t2) * 1000,
                  sample=url[:80])
        except Exception as e:
            _step("signed_url", False, (time.perf_counter() - t2) * 1000, error=str(e))

        t3 = time.perf_counter()
        try:
            await storage.delete(key)
            _step("delete", True, (time.perf_counter() - t3) * 1000)
        except Exception as e:
            _step("delete", False, (time.perf_counter() - t3) * 1000, error=str(e))

        overall_ok = all(s["ok"] for s in steps)
        return {
            "ok": overall_ok,
            "steps": steps,
            "key": key,
            "backend_class": type(storage).__name__,
        }
