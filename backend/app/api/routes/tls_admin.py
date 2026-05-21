"""TLS certificate admin (Pack 150).

Endpoints (prefix /admin/tls, is_owner OR is_admin gate):

  GET   /admin/tls/status     — текущий сертификат: issuer, domain, expires, days_left
  POST  /admin/tls/upload     — загрузить cert+key PEM руками (из любого источника)
  POST  /admin/tls/letsencrypt — выпустить через certbot (HTTP-01 webroot challenge)
  PATCH /admin/tls/schedule   — toggle квартального авто-renewal

Файлы лежат в /app/certs (mounted на ./nginx/certs в nginx → /etc/nginx/certs:ro).
  - fullchain.pem  — публичный chain
  - privkey.pem    — приватный ключ
  - dev-fullchain.pem / dev-privkey.pem — legacy dev cert (fallback)
  - config.json    — метаданные (source: 'letsencrypt'|'manual', renewed_at, schedule_enabled)

Все операции в audit_log; loading/install — is_critical=true.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_chain import append_audit_entry
from app.core.security import get_current_user
from app.database import get_db
from app.models.user import User

log = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tls", tags=["tls-admin"])


# =====================================================================
# Paths
# =====================================================================
CERT_DIR = Path(os.environ.get("TLS_CERT_DIR", "/app/certs"))
CERT_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_PATH = CERT_DIR / "config.json"
CHALLENGE_DIR = Path(os.environ.get("TLS_ACME_WEBROOT", "/app/certs/.well-known"))
CHALLENGE_DIR.mkdir(parents=True, exist_ok=True)


# Pack 150: bootstrap — nginx ждёт fullchain.pem/privkey.pem. Если их
# ещё нет (свежий деплой, никогда не было LE), копируем из dev-*.pem
# чтобы nginx стартанул на dev-cert'е.
def _bootstrap_canonical_cert() -> None:
    cert = CERT_DIR / "fullchain.pem"
    key = CERT_DIR / "privkey.pem"
    if cert.exists() and key.exists():
        return
    dev_cert = CERT_DIR / "dev-fullchain.pem"
    dev_key = CERT_DIR / "dev-privkey.pem"
    if dev_cert.exists() and dev_key.exists():
        try:
            shutil.copy2(dev_cert, cert)
            shutil.copy2(dev_key, key)
            try:
                os.chmod(key, 0o600)
            except Exception:
                pass
            log.info("[tls_admin] bootstrap: seeded fullchain.pem from dev-fullchain.pem")
        except Exception as e:
            log.warning("[tls_admin] bootstrap failed: %s", e)


_bootstrap_canonical_cert()


# =====================================================================
# Auth
# =====================================================================
def _require_db_admin(user: User) -> None:
    if user.is_owner or bool(getattr(user, "is_admin", False)):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Доступ только для owner/admin")


# =====================================================================
# Config persistence
# =====================================================================
def _read_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {
            "source": None,
            "renewed_at": None,
            "schedule_enabled": False,
            "schedule_interval_days": 90,
            "last_le_attempt": None,
            "last_le_result": None,
            "domain": None,
            "email": None,
        }
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def _write_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, default=str))


# =====================================================================
# Cert introspection (uses cryptography lib)
# =====================================================================
def _parse_cert(pem_path: Path) -> dict[str, Any]:
    """Return issuer/subject/dates from PEM cert."""
    if not pem_path.exists():
        return {"present": False}
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        pem_bytes = pem_path.read_bytes()
        cert = x509.load_pem_x509_certificate(pem_bytes, default_backend())
        now = datetime.now(timezone.utc)
        not_after = cert.not_valid_after_utc
        not_before = cert.not_valid_before_utc
        days_left = max(0, (not_after - now).days)
        # SAN
        try:
            ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            sans = ext.value.get_values_for_type(x509.DNSName)
        except Exception:
            sans = []
        return {
            "present": True,
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "not_before": not_before.isoformat(),
            "not_after": not_after.isoformat(),
            "days_left": days_left,
            "expired": now > not_after,
            "san": sans,
            "size_bytes": len(pem_bytes),
            "mtime": datetime.fromtimestamp(pem_path.stat().st_mtime, timezone.utc).isoformat(),
        }
    except Exception as e:
        return {"present": True, "parse_error": str(e), "size_bytes": pem_path.stat().st_size}


def _candidate_paths() -> list[tuple[str, Path, Path]]:
    """Возвращает список (label, cert_path, key_path) кандидатов."""
    return [
        ("production",  CERT_DIR / "fullchain.pem",     CERT_DIR / "privkey.pem"),
        ("dev-fallback", CERT_DIR / "dev-fullchain.pem", CERT_DIR / "dev-privkey.pem"),
    ]


def _current_active() -> tuple[Optional[str], Optional[Path], Optional[Path]]:
    """Возвращает (label, cert, key) первого существующего варианта."""
    for label, cert, key in _candidate_paths():
        if cert.exists() and key.exists():
            return label, cert, key
    return None, None, None


# =====================================================================
# Schemas
# =====================================================================
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
    email: str = Field(..., min_length=5, max_length=254)
    staging: bool = False  # use LE staging endpoint (для тестов)


class ScheduleUpdate(BaseModel):
    schedule_enabled: bool
    schedule_interval_days: int = Field(90, ge=30, le=365)


# =====================================================================
# Audit helper
# =====================================================================
async def _audit(db: AsyncSession, user: User, request: Request, *,
                 action: str, payload: Optional[dict] = None,
                 notes: str = "", is_critical: bool = False) -> None:
    try:
        from app.core.rate_limit import _real_client_ip
        await append_audit_entry(
            db,
            actor_id=str(user.id),
            actor_email=user.email,
            action=action,
            entity_type="tls_admin",
            payload=payload,
            ip_address=_real_client_ip(request),
            user_agent=request.headers.get("user-agent", "")[:512],
            notes=notes,
            is_critical=is_critical,
        )
        await db.commit()
    except Exception as e:
        log.warning("[tls_admin] audit fail: %s", e)
        await db.rollback()


# =====================================================================
# Endpoints
# =====================================================================

@router.get("/status", response_model=CertStatus)
async def get_status(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CertStatus:
    _require_db_admin(current_user)

    label, cert_p, key_p = _current_active()
    info = _parse_cert(cert_p) if cert_p else {"present": False}
    cfg = _read_config()
    return CertStatus(
        active_label=label,
        cert_path=str(cert_p) if cert_p else None,
        key_path=str(key_p) if key_p else None,
        info=info,
        config=cfg,
    )


@router.post("/upload")
async def upload_cert(
    body: ManualUploadRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Установить cert+key из произвольного источника."""
    _require_db_admin(current_user)

    # Validate PEM формат через cryptography
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        from cryptography.hazmat.backends import default_backend
        cert = x509.load_pem_x509_certificate(body.cert_pem.encode(), default_backend())
        load_pem_private_key(body.key_pem.encode(), password=None, backend=default_backend())
    except Exception as e:
        raise HTTPException(400, f"PEM невалидный: {e}")

    # Backup existing
    cert_path = CERT_DIR / "fullchain.pem"
    key_path = CERT_DIR / "privkey.pem"
    backup_dir = CERT_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if cert_path.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(cert_path, backup_dir / f"fullchain-{ts}.pem")
        shutil.copy2(key_path, backup_dir / f"privkey-{ts}.pem")

    cert_path.write_text(body.cert_pem.strip() + "\n")
    key_path.write_text(body.key_pem.strip() + "\n")
    try:
        os.chmod(key_path, 0o600)
        os.chmod(cert_path, 0o644)
    except Exception:
        pass

    # Update config
    info = _parse_cert(cert_path)
    cfg = _read_config()
    cfg.update({
        "source": "manual",
        "renewed_at": datetime.now(timezone.utc).isoformat(),
        "domain": info.get("san", [None])[0] if info.get("san") else cfg.get("domain"),
    })
    _write_config(cfg)

    await _audit(db, current_user, request,
                 action="tls.cert_uploaded",
                 payload={"label": body.label, "subject": info.get("subject"),
                          "not_after": info.get("not_after"), "size": info.get("size_bytes")},
                 notes=f"Manual cert installed · {info.get('subject', 'unknown')}",
                 is_critical=True)

    return {
        "ok": True,
        "info": info,
        "reload_required": True,
        "reload_hint": "Выполните: docker exec uza-nginx nginx -s reload",
    }


@router.post("/letsencrypt")
async def run_letsencrypt(
    body: LetsEncryptRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Запустить certbot через subprocess. Webroot challenge через nginx /.well-known/acme-challenge."""
    _require_db_admin(current_user)

    # Validate certbot installed
    if not shutil.which("certbot"):
        raise HTTPException(
            500,
            "certbot не установлен в backend-контейнере. "
            "Добавьте `certbot` в backend/Dockerfile (apt-get install certbot), "
            "пересоберите образ. Альтернатива: используйте manual upload.",
        )

    domain = body.domain.strip().lower()
    email = body.email.strip().lower()
    le_dir = CERT_DIR / "letsencrypt"
    le_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "certbot", "certonly",
        "--non-interactive",
        "--agree-tos",
        "--email", email,
        "-d", domain,
        "--webroot",
        "-w", str(CHALLENGE_DIR.parent),  # webroot — родитель /.well-known
        "--config-dir", str(le_dir / "config"),
        "--work-dir",   str(le_dir / "work"),
        "--logs-dir",   str(le_dir / "logs"),
        "--keep-until-expiring",
    ]
    if body.staging:
        cmd.append("--staging")

    cfg = _read_config()
    cfg["last_le_attempt"] = datetime.now(timezone.utc).isoformat()
    cfg["domain"] = domain
    cfg["email"] = email

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        code = proc.returncode
        stdout_s = stdout.decode("utf-8", errors="replace")
        stderr_s = stderr.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        raise HTTPException(504, "certbot выполнялся больше 120s — прерван")
    except Exception as e:
        raise HTTPException(500, f"certbot execution failed: {e}")

    cfg["last_le_result"] = {"code": code, "stdout_tail": stdout_s[-2000:], "stderr_tail": stderr_s[-2000:]}

    if code == 0:
        # certbot пишет в config-dir/live/<domain>/{fullchain,privkey}.pem — копируем в CERT_DIR
        le_live = le_dir / "config" / "live" / domain
        cert_src = le_live / "fullchain.pem"
        key_src = le_live / "privkey.pem"
        if cert_src.exists() and key_src.exists():
            backup_dir = CERT_DIR / "backups"
            backup_dir.mkdir(exist_ok=True)
            cert_dst = CERT_DIR / "fullchain.pem"
            key_dst = CERT_DIR / "privkey.pem"
            if cert_dst.exists():
                ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                shutil.copy2(cert_dst, backup_dir / f"fullchain-{ts}.pem")
                shutil.copy2(key_dst, backup_dir / f"privkey-{ts}.pem")
            # certbot использует симлинки — читаем содержимое реальных файлов
            cert_dst.write_text(cert_src.resolve().read_text())
            key_dst.write_text(key_src.resolve().read_text())
            try:
                os.chmod(key_dst, 0o600)
                os.chmod(cert_dst, 0o644)
            except Exception:
                pass
            cfg["source"] = "letsencrypt"
            cfg["renewed_at"] = datetime.now(timezone.utc).isoformat()

    _write_config(cfg)

    info = _parse_cert(CERT_DIR / "fullchain.pem") if code == 0 else {}

    await _audit(db, current_user, request,
                 action="tls.letsencrypt_renew",
                 payload={"domain": domain, "email": email, "staging": body.staging,
                          "exit_code": code, "subject": info.get("subject")},
                 notes=f"LE {'OK' if code == 0 else 'FAILED'} · {domain}"
                       + (f" · subject={info.get('subject', '')}" if code == 0 else f" · code={code}"),
                 is_critical=True)

    if code != 0:
        raise HTTPException(
            400,
            f"certbot failed (exit {code}). stderr: {stderr_s[-500:]}",
        )

    return {
        "ok": True,
        "info": info,
        "stdout_tail": stdout_s[-1000:],
        "reload_required": True,
        "reload_hint": "Выполните: docker exec uza-nginx nginx -s reload",
    }


@router.patch("/schedule")
async def update_schedule(
    body: ScheduleUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Квартальный auto-renew. APScheduler-job проверяет config.json раз в день."""
    _require_db_admin(current_user)

    cfg = _read_config()
    cfg["schedule_enabled"] = body.schedule_enabled
    cfg["schedule_interval_days"] = body.schedule_interval_days
    _write_config(cfg)

    await _audit(db, current_user, request,
                 action="tls.schedule_changed",
                 payload={"enabled": body.schedule_enabled, "interval_days": body.schedule_interval_days},
                 notes=f"TLS auto-renew = {body.schedule_enabled} ({body.schedule_interval_days} days)")

    return {"ok": True, "config": cfg}
