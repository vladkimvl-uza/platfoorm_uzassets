"""Admin endpoints for inspecting/testing the file storage backend (Pack 149).

GET  /admin/storage/status     — current backend + config + smoke-test result
POST /admin/storage/test       — upload a probe file, fetch it back, delete

UI lives at /admin/storage. Configuration changes are NOT done via this UI —
they require editing `.env` + container recreate. The UI shows the current
state so admin can verify the storage is wired correctly.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.security import _has_permission
from app.models.user import User
from app.services.storage import get_storage, StorageError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/storage", tags=["admin-storage"])


def _require_admin(user: User):
    if user.is_owner:
        return
    if _has_permission(user, "companies.edit") or _has_permission(user, "tasks.manage"):
        return
    raise HTTPException(http_status.HTTP_403_FORBIDDEN,
                        "Permission required: companies.edit or tasks.manage")


def _redact(s: str) -> str:
    if not s or len(s) < 8:
        return "***" if s else ""
    return s[:4] + "…" + s[-4:]


@router.get("/status")
async def storage_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return current storage backend + redacted config (no secrets)."""
    _require_admin(user)
    backend_env = (os.environ.get("STORAGE_BACKEND") or "local").lower()
    cfg = {
        "backend": backend_env,
        "local_root": os.environ.get("STORAGE_LOCAL_ROOT") or "/app/uploads",
        "s3_endpoint": os.environ.get("STORAGE_S3_ENDPOINT_URL") or "",
        "s3_bucket": os.environ.get("STORAGE_S3_BUCKET") or "",
        "s3_region": os.environ.get("STORAGE_S3_REGION") or "us-east-1",
        "s3_access_key": _redact(os.environ.get("STORAGE_S3_ACCESS_KEY") or ""),
        "s3_force_path_style": (os.environ.get("STORAGE_S3_FORCE_PATH_STYLE", "true").lower() == "true"),
        "s3_sse": os.environ.get("STORAGE_S3_SSE") or "",
    }
    # Probe storage init
    init_ok = True
    init_err: str | None = None
    try:
        storage = get_storage()
        info = type(storage).__name__
    except Exception as e:
        init_ok = False
        init_err = str(e)
        info = None

    return {
        "config": cfg,
        "backend_class": info,
        "init_ok": init_ok,
        "init_error": init_err,
        "now": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/test")
async def storage_smoke_test(
    user: User = Depends(get_current_user),
):
    """Upload a small probe blob, fetch it back, delete. Reports per-step
    latency and any errors. Use to verify S3 config end-to-end without
    relying on the attachments UI.
    """
    _require_admin(user)
    storage = get_storage()
    probe_data = b"UzAssets storage probe " + secrets.token_hex(16).encode()
    key = f"_probe/{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}.txt"

    steps: list[dict] = []

    def _step(name: str, ok: bool, ms: float, error: str | None = None, **extra):
        steps.append({"step": name, "ok": ok, "ms": round(ms, 1), "error": error, **extra})

    import time
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
        _step("signed_url", True, (time.perf_counter() - t2) * 1000, sample=url[:80])
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
