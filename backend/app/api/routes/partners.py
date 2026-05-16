"""Integration partners + audit log routes (Pack 12.4)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_permission
from app.database import get_db
from app.models.api_key import ApiKey
from app.models.external_api import ExternalApi
from app.models.partner import IntegrationPartner
from app.models.user import User
from app.models.webhook import WebhookSubscription
from app.schemas.partner import (
    IntegrationPartnerCreate, IntegrationPartnerListResponse,
    IntegrationPartnerRead, IntegrationPartnerUpdate,
    PartnerLinkedResource, PartnerLinkPayload, PartnerResourcesResponse,
)


router = APIRouter(prefix="/partners", tags=["partners"])


# ════════════════════════════════════════════════════════════
#   Helpers
# ════════════════════════════════════════════════════════════

async def _populate_counts(db: AsyncSession, p: IntegrationPartner) -> IntegrationPartnerRead:
    out = IntegrationPartnerRead.model_validate(p)
    out.service_accounts_count = int((await db.execute(
        select(func.count(User.id)).where(and_(
            User.partner_id == p.id, User.is_service_account.is_(True),
        )),
    )).scalar_one() or 0)
    out.api_keys_count = int((await db.execute(
        select(func.count(ApiKey.id)).join(User, ApiKey.service_account_id == User.id).where(
            User.partner_id == p.id,
        ),
    )).scalar_one() or 0)
    out.webhooks_count = int((await db.execute(
        select(func.count(WebhookSubscription.id)).where(WebhookSubscription.partner_id == p.id),
    )).scalar_one() or 0)
    out.external_apis_count = int((await db.execute(
        select(func.count(ExternalApi.id)).where(ExternalApi.partner_id == p.id),
    )).scalar_one() or 0)
    return out


# ════════════════════════════════════════════════════════════
#   Partner CRUD
# ════════════════════════════════════════════════════════════

@router.get("", response_model=IntegrationPartnerListResponse)
async def list_partners(
    q: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("integration_partners.read")),
):
    base = select(IntegrationPartner)
    if q:
        like = f"%{q.lower()}%"
        base = base.where(or_(
            IntegrationPartner.slug.ilike(like),
            IntegrationPartner.name.ilike(like),
            IntegrationPartner.legal_name.ilike(like),
        ))
    if status_filter:
        base = base.where(IntegrationPartner.status == status_filter)
    rows = (await db.execute(base.order_by(IntegrationPartner.name))).scalars().all()
    items = [await _populate_counts(db, p) for p in rows]
    return IntegrationPartnerListResponse(items=items, total=len(items))


@router.post("", response_model=IntegrationPartnerRead, status_code=status.HTTP_201_CREATED)
async def create_partner(
    body: IntegrationPartnerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission("integration_partners.manage")),
):
    exists = (await db.execute(
        select(IntegrationPartner).where(IntegrationPartner.slug == body.slug),
    )).scalars().first()
    if exists:
        raise HTTPException(409, f"Slug already taken: {body.slug}")

    now = datetime.now(timezone.utc)
    p = IntegrationPartner(
        created_at=now, updated_at=now,
        slug=body.slug, name=body.name, legal_name=body.legal_name,
        description=body.description,
        kind=body.kind, status=body.status, tier=body.tier,
        contacts=[c.model_dump() for c in body.contacts] if body.contacts else None,
        tags=body.tags,
        contract_ref=body.contract_ref,
        contract_start=body.contract_start, contract_end=body.contract_end,
        owner_id=body.owner_id, created_by_id=user.id,
        notes=body.notes,
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return await _populate_counts(db, p)


@router.get("/{partner_id}", response_model=IntegrationPartnerRead)
async def get_partner(
    partner_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("integration_partners.read")),
):
    p = await db.get(IntegrationPartner, partner_id)
    if not p:
        raise HTTPException(404, "Partner not found")
    return await _populate_counts(db, p)


@router.patch("/{partner_id}", response_model=IntegrationPartnerRead)
async def update_partner(
    partner_id: UUID,
    body: IntegrationPartnerUpdate,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("integration_partners.manage")),
):
    p = await db.get(IntegrationPartner, partner_id)
    if not p:
        raise HTTPException(404, "Partner not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        if k == "contacts" and v is not None:
            p.contacts = [c.model_dump() if hasattr(c, "model_dump") else c for c in v]
        else:
            setattr(p, k, v)
    p.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(p)
    return await _populate_counts(db, p)


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_partner(
    partner_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("integration_partners.manage")),
):
    p = await db.get(IntegrationPartner, partner_id)
    if not p:
        raise HTTPException(404, "Partner not found")
    await db.delete(p)
    await db.commit()


# ════════════════════════════════════════════════════════════
#   Linked resources
# ════════════════════════════════════════════════════════════

@router.get("/{partner_id}/resources", response_model=PartnerResourcesResponse)
async def list_resources(
    partner_id: UUID,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("integration_partners.read")),
):
    p = await db.get(IntegrationPartner, partner_id)
    if not p:
        raise HTTPException(404, "Partner not found")

    sas = (await db.execute(
        select(User).where(and_(User.partner_id == partner_id, User.is_service_account.is_(True))),
    )).scalars().all()
    apis = (await db.execute(
        select(ExternalApi).where(ExternalApi.partner_id == partner_id),
    )).scalars().all()
    whs = (await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.partner_id == partner_id),
    )).scalars().all()

    return PartnerResourcesResponse(
        partner_id=partner_id,
        service_accounts=[
            PartnerLinkedResource(
                resource_type="service_account",
                resource_id=u.id,
                label=u.full_name or u.email,
                extra={"email": u.email, "is_active": u.is_active},
            ) for u in sas
        ],
        external_apis=[
            PartnerLinkedResource(
                resource_type="external_api",
                resource_id=a.id,
                label=a.name,
                extra={"slug": a.slug, "status": a.status},
            ) for a in apis
        ],
        webhooks=[
            PartnerLinkedResource(
                resource_type="webhook",
                resource_id=w.id,
                label=w.name,
                extra={"target_url": w.target_url, "is_active": w.is_active},
            ) for w in whs
        ],
    )


@router.post("/{partner_id}/links", status_code=status.HTTP_204_NO_CONTENT)
async def attach_resource(
    partner_id: UUID,
    body: PartnerLinkPayload,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("integration_partners.manage")),
):
    p = await db.get(IntegrationPartner, partner_id)
    if not p:
        raise HTTPException(404, "Partner not found")

    if body.resource_type == "service_account":
        u = await db.get(User, body.resource_id)
        if u is None or not u.is_service_account:
            raise HTTPException(404, "Service account not found")
        u.partner_id = partner_id
    elif body.resource_type == "external_api":
        a = await db.get(ExternalApi, body.resource_id)
        if a is None:
            raise HTTPException(404, "External API not found")
        a.partner_id = partner_id
    elif body.resource_type == "webhook":
        w = await db.get(WebhookSubscription, body.resource_id)
        if w is None:
            raise HTTPException(404, "Webhook subscription not found")
        w.partner_id = partner_id
    await db.commit()


@router.delete("/{partner_id}/links", status_code=status.HTTP_204_NO_CONTENT)
async def detach_resource(
    partner_id: UUID,
    body: PartnerLinkPayload,
    db: AsyncSession = Depends(get_db),
    _u: User = Depends(require_permission("integration_partners.manage")),
):
    if body.resource_type == "service_account":
        u = await db.get(User, body.resource_id)
        if u and u.partner_id == partner_id:
            u.partner_id = None
    elif body.resource_type == "external_api":
        a = await db.get(ExternalApi, body.resource_id)
        if a and a.partner_id == partner_id:
            a.partner_id = None
    elif body.resource_type == "webhook":
        w = await db.get(WebhookSubscription, body.resource_id)
        if w and w.partner_id == partner_id:
            w.partner_id = None
    await db.commit()


# ════════════════════════════════════════════════════════════
#   Audit log is in a separate router file: app/api/routes/audit.py
# ════════════════════════════════════════════════════════════
