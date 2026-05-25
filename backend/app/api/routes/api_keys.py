"""API Keys + Service Accounts API — thin HTTP layer (refactored 2026-05-25).

Core `app/services/api_key_service.py` (create_api_key, revoke_api_key,
keys_count_for_service_account, key verification used by auth middleware)
is NOT touched — admin layer delegates to it.

Webhook event emission stays in route (post-commit best-effort).
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_permission
from app.database import get_db
from app.dependencies.api_keys import ApiKeysServiceDep
from app.models.user import User
from app.schemas.api_key import (
    ApiKeyAuditResponse, ApiKeyCreate, ApiKeyCreated, ApiKeyListResponse,
    ApiKeyRead, ApiKeyRevoke, ApiKeyUpdate,
    ServiceAccountCreate, ServiceAccountListResponse, ServiceAccountRead,
    ServiceAccountUpdate,
)


router = APIRouter(prefix="/api-keys", tags=["api-keys"])
log = logging.getLogger(__name__)


async def _emit(db: AsyncSession, event_name: str, payload: dict) -> None:
    try:
        from app.services.webhook_service import emit_event
        await emit_event(db, event_name, payload)
    except Exception:
        log.warning("emit %s failed", event_name, exc_info=True)


# ─── Catalog ──────────────────────────────────────────────────────

@router.get("/catalog")
async def catalog(
    service: ApiKeysServiceDep,
    _u: User = Depends(require_permission("api_keys.read")),
):
    return await service.catalog()


# ─── Service Accounts CRUD ────────────────────────────────────────

@router.get("/service-accounts", response_model=ServiceAccountListResponse)
async def list_service_accounts(
    service: ApiKeysServiceDep,
    q: Optional[str] = Query(None),
    _u: User = Depends(require_permission("api_keys.read")),
):
    return await service.list_service_accounts(q=q)


@router.post("/service-accounts", response_model=ServiceAccountRead,
             status_code=status.HTTP_201_CREATED)
async def create_service_account(
    body: ServiceAccountCreate,
    service: ApiKeysServiceDep,
    user: User = Depends(require_permission("api_keys.manage")),
):
    return await service.create_service_account(body, actor_id=user.id)


@router.patch("/service-accounts/{sa_id}", response_model=ServiceAccountRead)
async def update_service_account(
    sa_id: UUID,
    body: ServiceAccountUpdate,
    service: ApiKeysServiceDep,
    _u: User = Depends(require_permission("api_keys.manage")),
):
    return await service.update_service_account(sa_id, body)


@router.delete("/service-accounts/{sa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_account(
    sa_id: UUID,
    service: ApiKeysServiceDep,
    _u: User = Depends(require_permission("api_keys.manage")),
):
    await service.delete_service_account(sa_id)


# ─── API Keys CRUD ────────────────────────────────────────────────

@router.get("", response_model=ApiKeyListResponse)
async def list_keys(
    service: ApiKeysServiceDep,
    service_account_id: Optional[UUID] = Query(None),
    include_revoked: bool = Query(True),
    _u: User = Depends(require_permission("api_keys.read")),
):
    return await service.list_keys(
        service_account_id=service_account_id, include_revoked=include_revoked,
    )


@router.get("/{key_id}", response_model=ApiKeyRead)
async def get_key(
    key_id: UUID,
    service: ApiKeysServiceDep,
    _u: User = Depends(require_permission("api_keys.read")),
):
    return await service.get_key(key_id)


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreate,
    service: ApiKeysServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("api_keys.manage")),
):
    out, event_payload = await service.create_key(body, created_by_id=user.id)
    await _emit(db, "api_key.created", event_payload)
    return out


@router.patch("/{key_id}", response_model=ApiKeyRead)
async def update_key(
    key_id: UUID,
    body: ApiKeyUpdate,
    service: ApiKeysServiceDep,
    _u: User = Depends(require_permission("api_keys.manage")),
):
    return await service.update_key(key_id, body)


@router.post("/{key_id}/revoke", response_model=ApiKeyRead)
async def revoke_key(
    key_id: UUID,
    body: ApiKeyRevoke,
    service: ApiKeysServiceDep,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("api_keys.manage")),
):
    out, event_payload = await service.revoke_key(key_id, body, revoked_by_id=user.id)
    await _emit(db, "api_key.revoked", event_payload)
    return out


# ─── Audit log per key ────────────────────────────────────────────

@router.get("/{key_id}/audit", response_model=ApiKeyAuditResponse)
async def key_audit(
    key_id: UUID,
    service: ApiKeysServiceDep,
    limit: int = Query(100, ge=1, le=500),
    _u: User = Depends(require_permission("api_keys.read")),
):
    return await service.key_audit(key_id, limit=limit)
