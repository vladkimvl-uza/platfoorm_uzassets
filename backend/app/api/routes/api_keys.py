"""API Keys + Service Accounts CRUD (Pack 12.0)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user, require_permission
from app.database import get_db
from app.models.api_key import ApiKey, KEY_ENVIRONMENTS
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.api_key import (
    ApiKeyAuditEntry, ApiKeyAuditResponse,
    ApiKeyCreate, ApiKeyCreated, ApiKeyListResponse, ApiKeyRead, ApiKeyRevoke, ApiKeyUpdate,
    ServiceAccountCreate, ServiceAccountListResponse, ServiceAccountRead, ServiceAccountUpdate,
)
from app.services import api_key_service as svc


router = APIRouter(prefix="/api-keys", tags=["api-keys"])


# ════════════════════════════════════════════════════════════
#   Catalog: list of environments + counts
# ════════════════════════════════════════════════════════════

@router.get("/catalog")
async def catalog(
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("api_keys.read")),
):
    """Static catalog + live counts for the dashboard top-bar."""
    total = int((await db.execute(select(func.count(ApiKey.id)))).scalar_one() or 0)
    active = int((await db.execute(
        select(func.count(ApiKey.id)).where(and_(
            ApiKey.revoked_at.is_(None),
            or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > datetime.now(timezone.utc)),
        )),
    )).scalar_one() or 0)
    sa_total = int((await db.execute(
        select(func.count(User.id)).where(User.is_service_account.is_(True)),
    )).scalar_one() or 0)

    return {
        "environments": KEY_ENVIRONMENTS,
        "counts": {"total": total, "active": active, "revoked": total - active,
                   "service_accounts": sa_total},
    }


# ════════════════════════════════════════════════════════════
#   Service Accounts CRUD
# ════════════════════════════════════════════════════════════

@router.get("/service-accounts", response_model=ServiceAccountListResponse)
async def list_service_accounts(
    q: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("api_keys.read")),
):
    base = select(User).where(User.is_service_account.is_(True))
    if q:
        like = f"%{q}%"
        base = base.where(or_(User.email.ilike(like), User.full_name.ilike(like)))
    rows = (await db.execute(base.order_by(User.created_at.desc()))).scalars().all()

    items: list[ServiceAccountRead] = []
    for u in rows:
        kc = await svc.keys_count_for_service_account(db, u.id)
        d = ServiceAccountRead.model_validate(u)
        d.keys_count = kc
        items.append(d)
    return ServiceAccountListResponse(items=items, total=len(items))


@router.post("/service-accounts", response_model=ServiceAccountRead, status_code=status.HTTP_201_CREATED)
async def create_service_account(
    body: ServiceAccountCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("api_keys.manage")),
):
    # Email uniqueness
    exists = (await db.execute(select(User).where(User.email == str(body.email)))).scalars().first()
    if exists:
        raise HTTPException(409, "Email already taken")

    now = datetime.now(timezone.utc)
    sa = User(
        email=str(body.email),
        full_name=body.full_name,
        password_hash=None,  # SAs never log in via password
        is_active=True,
        is_service_account=True,
        service_account_description=body.description,
        service_account_owner_id=body.owner_id or user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(sa)
    await db.commit()
    await db.refresh(sa)
    out = ServiceAccountRead.model_validate(sa)
    out.keys_count = 0
    return out


@router.patch("/service-accounts/{sa_id}", response_model=ServiceAccountRead)
async def update_service_account(
    sa_id: UUID,
    body: ServiceAccountUpdate,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("api_keys.manage")),
):
    sa = await db.get(User, sa_id)
    if sa is None or not sa.is_service_account:
        raise HTTPException(404, "Service account not found")

    data = body.model_dump(exclude_unset=True)
    if "description" in data:
        sa.service_account_description = data["description"]
    if "owner_id" in data:
        sa.service_account_owner_id = data["owner_id"]
    if "full_name" in data:
        sa.full_name = data["full_name"]
    if "is_active" in data:
        sa.is_active = data["is_active"]
    sa.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(sa)
    out = ServiceAccountRead.model_validate(sa)
    out.keys_count = await svc.keys_count_for_service_account(db, sa.id)
    return out


@router.delete("/service-accounts/{sa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service_account(
    sa_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("api_keys.manage")),
):
    sa = await db.get(User, sa_id)
    if sa is None or not sa.is_service_account:
        raise HTTPException(404, "Service account not found")
    # Soft-deactivate instead of hard-delete: keeps audit log intact
    sa.is_active = False
    sa.updated_at = datetime.now(timezone.utc)
    # Revoke all its keys
    keys = (await db.execute(
        select(ApiKey).where(and_(ApiKey.service_account_id == sa_id, ApiKey.revoked_at.is_(None))),
    )).scalars().all()
    now = datetime.now(timezone.utc)
    for k in keys:
        k.revoked_at = now
        k.revoke_reason = "service account deleted"
    await db.commit()


# ════════════════════════════════════════════════════════════
#   API Keys CRUD
# ════════════════════════════════════════════════════════════

@router.get("", response_model=ApiKeyListResponse)
async def list_keys(
    service_account_id: Optional[UUID] = Query(None),
    include_revoked: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("api_keys.read")),
):
    base = select(ApiKey)
    if service_account_id is not None:
        base = base.where(ApiKey.service_account_id == service_account_id)
    if not include_revoked:
        base = base.where(ApiKey.revoked_at.is_(None))
    rows = (await db.execute(base.order_by(ApiKey.created_at.desc()))).scalars().all()
    return ApiKeyListResponse(
        items=[ApiKeyRead.model_validate(r) for r in rows],
        total=len(rows),
    )


@router.get("/{key_id}", response_model=ApiKeyRead)
async def get_key(
    key_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("api_keys.read")),
):
    row = await db.get(ApiKey, key_id)
    if not row:
        raise HTTPException(404, "Key not found")
    return ApiKeyRead.model_validate(row)


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("api_keys.manage")),
):
    # Validate service account exists and is a SA
    sa = await db.get(User, body.service_account_id)
    if sa is None or not sa.is_service_account:
        raise HTTPException(404, "Service account not found")
    if not sa.is_active:
        raise HTTPException(400, "Service account is disabled")

    # Validate scopes are real permission codes
    if body.scopes:
        from app.models.user import Permission
        existing = (await db.execute(
            select(Permission.code).where(Permission.code.in_(body.scopes)),
        )).scalars().all()
        bad = set(body.scopes) - set(existing)
        if bad:
            raise HTTPException(400, f"Unknown scopes: {sorted(bad)}")

    row, plaintext = await svc.create_api_key(
        db,
        service_account_id=body.service_account_id,
        name=body.name,
        description=body.description,
        scopes=body.scopes,
        environment=body.environment,
        rate_limit_per_minute=body.rate_limit_per_minute,
        ip_allowlist=body.ip_allowlist,
        expires_at=body.expires_at,
        created_by_id=user.id,
    )

    # Pack 12.1: emit webhook event (does NOT include the plaintext token — only metadata)
    try:
        from app.services.webhook_service import emit_event
        await emit_event(db, "api_key.created", {
            "key_id": str(row.id),
            "service_account_id": str(row.service_account_id),
            "name": row.name,
            "environment": row.environment,
            "scopes": row.scopes,
            "created_by_id": str(user.id),
        })
    except Exception:
        pass  # Event emission must never break the primary operation

    out = ApiKeyCreated.model_validate(row)
    out.plaintext_token = plaintext
    return out


@router.patch("/{key_id}", response_model=ApiKeyRead)
async def update_key(
    key_id: UUID,
    body: ApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("api_keys.manage")),
):
    row = await db.get(ApiKey, key_id)
    if not row:
        raise HTTPException(404, "Key not found")
    if row.revoked_at:
        raise HTTPException(400, "Cannot edit revoked key")

    data = body.model_dump(exclude_unset=True)
    if "scopes" in data and data["scopes"] is not None:
        from app.models.user import Permission
        existing = (await db.execute(
            select(Permission.code).where(Permission.code.in_(data["scopes"])),
        )).scalars().all()
        bad = set(data["scopes"]) - set(existing)
        if bad:
            raise HTTPException(400, f"Unknown scopes: {sorted(bad)}")

    for k, v in data.items():
        setattr(row, k, v)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return ApiKeyRead.model_validate(row)


@router.post("/{key_id}/revoke", response_model=ApiKeyRead)
async def revoke_key(
    key_id: UUID,
    body: ApiKeyRevoke,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("api_keys.manage")),
):
    row = await db.get(ApiKey, key_id)
    if not row:
        raise HTTPException(404, "Key not found")
    row = await svc.revoke_api_key(db, row, revoked_by_id=user.id, reason=body.reason)

    # Pack 12.1: emit webhook event
    try:
        from app.services.webhook_service import emit_event
        await emit_event(db, "api_key.revoked", {
            "key_id": str(row.id),
            "service_account_id": str(row.service_account_id),
            "revoked_by_id": str(user.id),
            "reason": body.reason,
        })
    except Exception:
        pass

    return ApiKeyRead.model_validate(row)


# ════════════════════════════════════════════════════════════
#   Audit log per key
# ════════════════════════════════════════════════════════════

@router.get("/{key_id}/audit", response_model=ApiKeyAuditResponse)
async def key_audit(
    key_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("api_keys.read")),
):
    rows = (await db.execute(
        select(AuditLog).where(AuditLog.api_key_id == key_id)
        .order_by(AuditLog.created_at.desc()).limit(limit),
    )).scalars().all()
    return ApiKeyAuditResponse(
        items=[ApiKeyAuditEntry.model_validate(r) for r in rows],
        total=len(rows),
    )
