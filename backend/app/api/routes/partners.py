"""Integration Partners API — thin HTTP layer (refactored 2026-05-25)."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.security import require_permission
from app.dependencies.partners import PartnersServiceDep
from app.models.user import User
from app.schemas.partner import (
    IntegrationPartnerCreate, IntegrationPartnerListResponse,
    IntegrationPartnerRead, IntegrationPartnerUpdate,
    PartnerLinkPayload, PartnerResourcesResponse,
)


router = APIRouter(prefix="/partners", tags=["partners"])


@router.get("", response_model=IntegrationPartnerListResponse)
async def list_partners(
    service: PartnersServiceDep,
    q: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    _u: User = Depends(require_permission("integration_partners.read")),
):
    return await service.list_partners(q=q, status_filter=status_filter)


@router.post("", response_model=IntegrationPartnerRead, status_code=status.HTTP_201_CREATED)
async def create_partner(
    body: IntegrationPartnerCreate,
    service: PartnersServiceDep,
    user: User = Depends(require_permission("integration_partners.manage")),
):
    return await service.create_partner(body, created_by_id=user.id)


@router.get("/{partner_id}", response_model=IntegrationPartnerRead)
async def get_partner(
    partner_id: UUID,
    service: PartnersServiceDep,
    _u: User = Depends(require_permission("integration_partners.read")),
):
    return await service.get_partner(partner_id)


@router.patch("/{partner_id}", response_model=IntegrationPartnerRead)
async def update_partner(
    partner_id: UUID,
    body: IntegrationPartnerUpdate,
    service: PartnersServiceDep,
    _u: User = Depends(require_permission("integration_partners.manage")),
):
    return await service.update_partner(partner_id, body)


@router.delete("/{partner_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_partner(
    partner_id: UUID,
    service: PartnersServiceDep,
    _u: User = Depends(require_permission("integration_partners.manage")),
):
    await service.delete_partner(partner_id)


# ─── Linked resources ─────────────────────────────────────────────

@router.get("/{partner_id}/resources", response_model=PartnerResourcesResponse)
async def list_resources(
    partner_id: UUID,
    service: PartnersServiceDep,
    _u: User = Depends(require_permission("integration_partners.read")),
):
    return await service.list_resources(partner_id)


@router.post("/{partner_id}/links", status_code=status.HTTP_204_NO_CONTENT)
async def attach_resource(
    partner_id: UUID,
    body: PartnerLinkPayload,
    service: PartnersServiceDep,
    _u: User = Depends(require_permission("integration_partners.manage")),
):
    await service.attach_resource(partner_id, body)


@router.delete("/{partner_id}/links", status_code=status.HTTP_204_NO_CONTENT)
async def detach_resource(
    partner_id: UUID,
    body: PartnerLinkPayload,
    service: PartnersServiceDep,
    _u: User = Depends(require_permission("integration_partners.manage")),
):
    await service.detach_resource(partner_id, body)
