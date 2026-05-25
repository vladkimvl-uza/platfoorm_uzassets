"""Use cases for Integration Partners."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException

from app.models.partner import IntegrationPartner
from app.schemas.partner import (
    IntegrationPartnerCreate, IntegrationPartnerListResponse,
    IntegrationPartnerRead, IntegrationPartnerUpdate,
    PartnerLinkedResource, PartnerLinkPayload, PartnerResourcesResponse,
)
from app.uow.ports import UnitOfWorkABC


class PartnersService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def _populate_counts(self, p: IntegrationPartner) -> IntegrationPartnerRead:
        out = IntegrationPartnerRead.model_validate(p)
        out.service_accounts_count = await self.uow.partners.count_service_accounts(p.id)
        out.api_keys_count         = await self.uow.partners.count_api_keys(p.id)
        out.webhooks_count         = await self.uow.partners.count_webhooks(p.id)
        out.external_apis_count    = await self.uow.partners.count_external_apis(p.id)
        return out

    # ─── partner CRUD ─────────────────────────────────────────────

    async def list_partners(
        self,
        *,
        q: Optional[str],
        status_filter: Optional[str],
    ) -> IntegrationPartnerListResponse:
        async with self.uow:
            rows = await self.uow.partners.list_partners(q=q, status_filter=status_filter)
            items = [await self._populate_counts(p) for p in rows]
        return IntegrationPartnerListResponse(items=items, total=len(items))

    async def create_partner(
        self,
        body: IntegrationPartnerCreate,
        *,
        created_by_id: UUID,
    ) -> IntegrationPartnerRead:
        async with self.uow:
            exists = await self.uow.partners.get_by_slug(body.slug)
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
                owner_id=body.owner_id, created_by_id=created_by_id,
                notes=body.notes,
            )
            self.uow.partners.add(p)
            await self.uow.partners.flush()
            await self.uow.partners.refresh(p)
            return await self._populate_counts(p)

    async def get_partner(self, partner_id: UUID) -> IntegrationPartnerRead:
        async with self.uow:
            p = await self.uow.partners.get(partner_id)
            if not p:
                raise HTTPException(404, "Partner not found")
            return await self._populate_counts(p)

    async def update_partner(
        self,
        partner_id: UUID,
        body: IntegrationPartnerUpdate,
    ) -> IntegrationPartnerRead:
        async with self.uow:
            p = await self.uow.partners.get(partner_id)
            if not p:
                raise HTTPException(404, "Partner not found")
            data = body.model_dump(exclude_unset=True)
            for k, v in data.items():
                if k == "contacts" and v is not None:
                    p.contacts = [
                        c.model_dump() if hasattr(c, "model_dump") else c for c in v
                    ]
                else:
                    setattr(p, k, v)
            p.updated_at = datetime.now(timezone.utc)
            await self.uow.partners.flush()
            await self.uow.partners.refresh(p)
            return await self._populate_counts(p)

    async def delete_partner(self, partner_id: UUID) -> None:
        async with self.uow:
            p = await self.uow.partners.get(partner_id)
            if not p:
                raise HTTPException(404, "Partner not found")
            await self.uow.partners.delete(p)
            await self.uow.partners.flush()

    # ─── linked resources ─────────────────────────────────────────

    async def list_resources(self, partner_id: UUID) -> PartnerResourcesResponse:
        async with self.uow:
            p = await self.uow.partners.get(partner_id)
            if not p:
                raise HTTPException(404, "Partner not found")
            sas  = await self.uow.partners.list_partner_service_accounts(partner_id)
            apis = await self.uow.partners.list_partner_external_apis(partner_id)
            whs  = await self.uow.partners.list_partner_webhooks(partner_id)

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
                    resource_id=a.id, label=a.name,
                    extra={"slug": a.slug, "status": a.status},
                ) for a in apis
            ],
            webhooks=[
                PartnerLinkedResource(
                    resource_type="webhook",
                    resource_id=w.id, label=w.name,
                    extra={"target_url": w.target_url, "is_active": w.is_active},
                ) for w in whs
            ],
        )

    async def attach_resource(self, partner_id: UUID, body: PartnerLinkPayload) -> None:
        async with self.uow:
            p = await self.uow.partners.get(partner_id)
            if not p:
                raise HTTPException(404, "Partner not found")
            if body.resource_type == "service_account":
                u = await self.uow.partners.get_service_account(body.resource_id)
                if u is None or not u.is_service_account:
                    raise HTTPException(404, "Service account not found")
                u.partner_id = partner_id
            elif body.resource_type == "external_api":
                a = await self.uow.partners.get_external_api(body.resource_id)
                if a is None:
                    raise HTTPException(404, "External API not found")
                a.partner_id = partner_id
            elif body.resource_type == "webhook":
                w = await self.uow.partners.get_webhook(body.resource_id)
                if w is None:
                    raise HTTPException(404, "Webhook subscription not found")
                w.partner_id = partner_id
            await self.uow.partners.flush()

    async def detach_resource(self, partner_id: UUID, body: PartnerLinkPayload) -> None:
        async with self.uow:
            if body.resource_type == "service_account":
                u = await self.uow.partners.get_service_account(body.resource_id)
                if u and u.partner_id == partner_id:
                    u.partner_id = None
            elif body.resource_type == "external_api":
                a = await self.uow.partners.get_external_api(body.resource_id)
                if a and a.partner_id == partner_id:
                    a.partner_id = None
            elif body.resource_type == "webhook":
                w = await self.uow.partners.get_webhook(body.resource_id)
                if w and w.partner_id == partner_id:
                    w.partner_id = None
            await self.uow.partners.flush()
