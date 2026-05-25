"""Persistence helpers for the audit-log admin route.

Most queries already live in `app.services.audit_service` (core, untouched).
This repo only covers single-event lookup; everything else delegates.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_event(self, event_id: UUID) -> Optional[AuditLog]:
        return (await self._session.execute(
            select(AuditLog).where(AuditLog.id == event_id)
        )).scalar_one_or_none()
