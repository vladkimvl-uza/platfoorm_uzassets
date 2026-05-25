"""Use cases for API Keys + Service Accounts admin.

Naming `api_keys_admin/` to coexist with existing
`app/services/api_key_service.py` (core: create_api_key,
revoke_api_key, keys_count_for_service_account, key verification
used by auth middleware). Refactor only touches CRUD + catalog +
audit listing; the core service stays untouched.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status as http_status

from app.models.api_key import KEY_ENVIRONMENTS
from app.models.user import User
from app.schemas.api_key import (
    ApiKeyAuditEntry, ApiKeyAuditResponse,
    ApiKeyCreate, ApiKeyCreated, ApiKeyListResponse, ApiKeyRead, ApiKeyRevoke, ApiKeyUpdate,
    ServiceAccountCreate, ServiceAccountListResponse, ServiceAccountRead, ServiceAccountUpdate,
)
from app.services import api_key_service as core
from app.uow.ports import UnitOfWorkABC


class ApiKeysAdminService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    # ─── catalog ──────────────────────────────────────────────────

    async def catalog(self) -> dict:
        async with self.uow:
            r = self.uow.api_keys
            total = await r.count_total_keys()
            active = await r.count_active_keys()
            sa_total = await r.count_service_accounts()
        return {
            "environments": KEY_ENVIRONMENTS,
            "counts": {
                "total": total, "active": active,
                "revoked": total - active, "service_accounts": sa_total,
            },
        }

    # ─── service accounts ─────────────────────────────────────────

    async def list_service_accounts(
        self, *, q: Optional[str],
    ) -> ServiceAccountListResponse:
        async with self.uow:
            rows = await self.uow.api_keys.list_service_accounts(q=q)
            items: list[ServiceAccountRead] = []
            for u in rows:
                kc = await core.keys_count_for_service_account(
                    self.uow._session, u.id,  # type: ignore[attr-defined]
                )
                d = ServiceAccountRead.model_validate(u)
                d.keys_count = kc
                items.append(d)
        return ServiceAccountListResponse(items=items, total=len(items))

    async def create_service_account(
        self, body: ServiceAccountCreate, *, actor_id: UUID,
    ) -> ServiceAccountRead:
        async with self.uow:
            exists = await self.uow.api_keys.get_user_by_email(str(body.email))
            if exists:
                raise HTTPException(409, "Email already taken")
            now = datetime.now(timezone.utc)
            sa = User(
                email=str(body.email), full_name=body.full_name,
                password_hash=None,
                is_active=True, is_service_account=True,
                service_account_description=body.description,
                service_account_owner_id=body.owner_id or actor_id,
                created_at=now, updated_at=now,
            )
            self.uow.api_keys.add(sa)
            await self.uow.api_keys.flush()
            await self.uow.api_keys.refresh(sa)
            out = ServiceAccountRead.model_validate(sa)
            out.keys_count = 0
            return out

    async def update_service_account(
        self, sa_id: UUID, body: ServiceAccountUpdate,
    ) -> ServiceAccountRead:
        async with self.uow:
            sa = await self.uow.api_keys.get_service_account(sa_id)
            if not sa:
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
            await self.uow.api_keys.flush()
            await self.uow.api_keys.refresh(sa)
            out = ServiceAccountRead.model_validate(sa)
            out.keys_count = await core.keys_count_for_service_account(
                self.uow._session, sa.id,  # type: ignore[attr-defined]
            )
            return out

    async def delete_service_account(self, sa_id: UUID) -> None:
        """Soft-deactivate + revoke all its active keys."""
        async with self.uow:
            sa = await self.uow.api_keys.get_service_account(sa_id)
            if not sa:
                raise HTTPException(404, "Service account not found")
            sa.is_active = False
            sa.updated_at = datetime.now(timezone.utc)
            keys = await self.uow.api_keys.list_active_keys_for_sa(sa_id)
            now = datetime.now(timezone.utc)
            for k in keys:
                k.revoked_at = now
                k.revoke_reason = "service account deleted"
            await self.uow.api_keys.flush()

    # ─── api keys ─────────────────────────────────────────────────

    async def list_keys(
        self, *, service_account_id: Optional[UUID], include_revoked: bool,
    ) -> ApiKeyListResponse:
        async with self.uow:
            rows = await self.uow.api_keys.list_keys(
                service_account_id=service_account_id,
                include_revoked=include_revoked,
            )
        return ApiKeyListResponse(
            items=[ApiKeyRead.model_validate(r) for r in rows],
            total=len(rows),
        )

    async def get_key(self, key_id: UUID) -> ApiKeyRead:
        async with self.uow:
            row = await self.uow.api_keys.get_key(key_id)
            if not row:
                raise HTTPException(404, "Key not found")
            return ApiKeyRead.model_validate(row)

    async def create_key(
        self, body: ApiKeyCreate, *, created_by_id: UUID,
    ) -> tuple[ApiKeyCreated, dict]:
        """Returns (created, event_payload) — caller emits webhook."""
        async with self.uow:
            sa = await self.uow.api_keys.get_service_account(body.service_account_id)
            if not sa:
                raise HTTPException(404, "Service account not found")
            if not sa.is_active:
                raise HTTPException(400, "Service account is disabled")
            if body.scopes:
                existing = await self.uow.api_keys.existing_permission_codes(body.scopes)
                bad = set(body.scopes) - existing
                if bad:
                    raise HTTPException(400, f"Unknown scopes: {sorted(bad)}")

            row, plaintext = await core.create_api_key(
                self.uow._session,  # type: ignore[attr-defined]
                service_account_id=body.service_account_id,
                name=body.name,
                description=body.description,
                scopes=body.scopes,
                environment=body.environment,
                rate_limit_per_minute=body.rate_limit_per_minute,
                ip_allowlist=body.ip_allowlist,
                expires_at=body.expires_at,
                created_by_id=created_by_id,
            )
            out = ApiKeyCreated.model_validate(row)
            out.plaintext_token = plaintext
            event_payload = {
                "key_id": str(row.id),
                "service_account_id": str(row.service_account_id),
                "name": row.name,
                "environment": row.environment,
                "scopes": row.scopes,
                "created_by_id": str(created_by_id),
            }
            return out, event_payload

    async def update_key(self, key_id: UUID, body: ApiKeyUpdate) -> ApiKeyRead:
        async with self.uow:
            row = await self.uow.api_keys.get_key(key_id)
            if not row:
                raise HTTPException(404, "Key not found")
            if row.revoked_at:
                raise HTTPException(400, "Cannot edit revoked key")
            data = body.model_dump(exclude_unset=True)
            if "scopes" in data and data["scopes"] is not None:
                existing = await self.uow.api_keys.existing_permission_codes(data["scopes"])
                bad = set(data["scopes"]) - existing
                if bad:
                    raise HTTPException(400, f"Unknown scopes: {sorted(bad)}")
            for k, v in data.items():
                setattr(row, k, v)
            row.updated_at = datetime.now(timezone.utc)
            await self.uow.api_keys.flush()
            await self.uow.api_keys.refresh(row)
            return ApiKeyRead.model_validate(row)

    async def revoke_key(
        self, key_id: UUID, body: ApiKeyRevoke, *, revoked_by_id: UUID,
    ) -> tuple[ApiKeyRead, dict]:
        async with self.uow:
            row = await self.uow.api_keys.get_key(key_id)
            if not row:
                raise HTTPException(404, "Key not found")
            row = await core.revoke_api_key(
                self.uow._session,  # type: ignore[attr-defined]
                row, revoked_by_id=revoked_by_id, reason=body.reason,
            )
            event_payload = {
                "key_id": str(row.id),
                "service_account_id": str(row.service_account_id),
                "revoked_by_id": str(revoked_by_id),
                "reason": body.reason,
            }
            return ApiKeyRead.model_validate(row), event_payload

    # ─── audit ────────────────────────────────────────────────────

    async def key_audit(self, key_id: UUID, *, limit: int) -> ApiKeyAuditResponse:
        async with self.uow:
            rows = await self.uow.api_keys.list_key_audit(key_id, limit=limit)
        return ApiKeyAuditResponse(
            items=[ApiKeyAuditEntry.model_validate(r) for r in rows],
            total=len(rows),
        )
