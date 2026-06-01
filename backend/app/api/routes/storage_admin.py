"""Admin endpoints for inspecting/testing the file storage backend (Pack 149)
— thin HTTP shim (refactored 2026-05-25).

GET  /admin/storage/status     — current backend + config + smoke-test result
POST /admin/storage/test       — upload a probe file, fetch it back, delete

UI lives at /admin/storage. Configuration changes are NOT done via this UI —
they require editing `.env` + container recreate.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.dependencies.storage_admin import StorageAdminServiceDep
from app.models.user import User

router = APIRouter(prefix="/admin/storage", tags=["admin-storage"])


@router.get("/status")
async def storage_status(
    service: StorageAdminServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.status(user)


@router.post("/test")
async def storage_smoke_test(
    service: StorageAdminServiceDep,
    user: User = Depends(get_current_user),
):
    return await service.smoke_test(user)
