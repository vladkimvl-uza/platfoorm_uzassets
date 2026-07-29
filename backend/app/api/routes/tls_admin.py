"""TLS certificate admin API — thin HTTP layer (refactored 2026-05-25).

Endpoints (prefix /admin/tls, is_owner OR is_admin gate):
  GET   /admin/tls/status       — current cert info + config
  POST  /admin/tls/upload       — manual PEM upload (cert + key)
  POST  /admin/tls/letsencrypt  — issue via certbot (HTTP-01 webroot)
  PATCH /admin/tls/schedule     — toggle quarterly auto-renewal

File operations + certbot invocation live in TlsAdminService (no DB).
Audit logging stays in route — it needs the request actor IP/UA.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.security import get_current_user
from app.database import get_db
from app.dependencies.tls_admin import TlsAdminServiceDep
from app.models.user import User
from app.services.tls_admin.service import (
    bootstrap_canonical_cert,
    ensure_dirs,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/tls", tags=["tls-admin"])


# Bootstrap on import (so nginx can find PEMs even before first request)
ensure_dirs()
bootstrap_canonical_cert()


# ─── auth ─────────────────────────────────────────────────────────

def _require_db_admin(user: User) -> None:
    """Владелец или платформенный администратор (роль admin).

    Раньше проверялось поле `user.is_admin`, КОТОРОГО НЕ СУЩЕСТВУЕТ ни в модели
    User, ни в таблице users — getattr всегда давал False, и управлять
    TLS-сертификатом мог ИСКЛЮЧИТЕЛЬНО владелец. Отказ был тихим: ни ошибки,
    ни записи в лог. Сверяемся с единой точкой is_super_admin, как весь
    остальной бэкенд.
    """
    from app.core.security import is_super_admin
    if is_super_admin(user):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступ только для owner/admin")


# ─── pydantic ─────────────────────────────────────────────────────

class CertStatus(BaseModel):
    active_label: Optional[str] = None
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    info: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)


class ManualUploadRequest(BaseModel):
    cert_pem: str = Field(..., min_length=100, max_length=200_000)
    key_pem:  str = Field(..., min_length=100, max_length=200_000)
    label: str = "manual"


class LetsEncryptRequest(BaseModel):
    domain: str = Field(..., min_length=3, max_length=253)
    email:  str = Field(..., min_length=5, max_length=254)
    staging: bool = False


class ScheduleUpdate(BaseModel):
    schedule_enabled: bool
    schedule_interval_days: int = Field(90, ge=30, le=365)


# ─── audit helper ─────────────────────────────────────────────────

async def _audit(
    db: AsyncSession, user: User, request: Request, *,
    action: str, payload: Optional[dict] = None,
    notes: str = "", is_critical: bool = False,
) -> None:
    try:
        from app.core.rate_limit import _real_client_ip
        await append_audit_entry(
            db,
            actor_id=str(user.id), actor_email=user.email,
            action=action, entity_type="tls_admin",
            payload=payload,
            ip_address=_real_client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:512],
            notes=notes, is_critical=is_critical,
        )
        await db.commit()
    except Exception as e:
        log.warning("[tls_admin] audit fail: %s", e)
        await db.rollback()


# ─── endpoints ────────────────────────────────────────────────────

@router.get("/status", response_model=CertStatus)
async def get_status(
    service: TlsAdminServiceDep,
    current_user: User = Depends(get_current_user),
) -> CertStatus:
    _require_db_admin(current_user)
    data = service.get_status()
    return CertStatus(**data)


@router.post("/upload")
async def upload_cert(
    body: ManualUploadRequest,
    request: Request,
    service: TlsAdminServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_db_admin(current_user)
    info = service.upload_cert(cert_pem=body.cert_pem, key_pem=body.key_pem)
    await _audit(
        db, current_user, request,
        action="tls.cert_uploaded",
        payload={
            "label": body.label, "subject": info.get("subject"),
            "not_after": info.get("not_after"),
            "size": info.get("size_bytes"),
        },
        notes=f"Manual cert installed · {info.get('subject', 'unknown')}",
        is_critical=True,
    )
    return {
        "ok": True, "info": info,
        "reload_required": True,
        "reload_hint": "Выполните: docker exec uza-nginx nginx -s reload",
    }


@router.post("/letsencrypt")
async def run_letsencrypt(
    body: LetsEncryptRequest,
    request: Request,
    service: TlsAdminServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run certbot via webroot challenge."""
    _require_db_admin(current_user)
    try:
        info, stdout_tail = await service.run_letsencrypt(
            domain=body.domain, email=body.email, staging=body.staging,
        )
    except HTTPException:
        # Service raised — audit failure too (read latest from config)
        await _audit(
            db, current_user, request,
            action="tls.letsencrypt_renew",
            payload={"domain": body.domain.strip().lower(),
                     "email": body.email.strip().lower(),
                     "staging": body.staging, "exit_code": "fail"},
            notes=f"LE FAILED · {body.domain}",
            is_critical=True,
        )
        raise

    await _audit(
        db, current_user, request,
        action="tls.letsencrypt_renew",
        payload={
            "domain": body.domain.strip().lower(),
            "email": body.email.strip().lower(),
            "staging": body.staging,
            "exit_code": 0,
            "subject": info.get("subject"),
        },
        notes=f"LE OK · {body.domain} · subject={info.get('subject', '')}",
        is_critical=True,
    )
    return {
        "ok": True, "info": info,
        "stdout_tail": stdout_tail,
        "reload_required": True,
        "reload_hint": "Выполните: docker exec uza-nginx nginx -s reload",
    }


@router.patch("/schedule")
async def update_schedule(
    body: ScheduleUpdate,
    request: Request,
    service: TlsAdminServiceDep,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_db_admin(current_user)
    cfg = service.update_schedule(
        enabled=body.schedule_enabled,
        interval_days=body.schedule_interval_days,
    )
    await _audit(
        db, current_user, request,
        action="tls.schedule_changed",
        payload={"enabled": body.schedule_enabled,
                 "interval_days": body.schedule_interval_days},
        notes=f"TLS auto-renew = {body.schedule_enabled} ({body.schedule_interval_days} days)",
    )
    return {"ok": True, "config": cfg}
