"""TLS auto-renewal scheduler (Pack 150).

Раз в день проверяет config.json в /app/certs и если:
  - schedule_enabled = true
  - текущий cert ближе чем 30 дней к expiry OR с последнего renewal прошло
    больше schedule_interval_days (по дефолту 90 — квартал)

то запускает certbot с сохранёнными domain/email.

Стартует из app.main при наличии scheduler.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


CERT_DIR = Path(os.environ.get("TLS_CERT_DIR", "/app/certs"))
CONFIG_PATH = CERT_DIR / "config.json"
CHALLENGE_WEBROOT = Path(os.environ.get("TLS_ACME_WEBROOT", "/app/certs/.well-known")).parent


def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except Exception:
        return {}


def _write_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, default=str))


def _days_left_in_cert() -> int | None:
    cert = CERT_DIR / "fullchain.pem"
    if not cert.exists():
        return None
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        c = x509.load_pem_x509_certificate(cert.read_bytes(), default_backend())
        delta = c.not_valid_after_utc - datetime.now(timezone.utc)
        return delta.days
    except Exception as e:
        log.warning("[tls_scheduler] parse error: %s", e)
        return None


async def maybe_renew() -> None:
    """Вызывается каждые 24h. Проверяет нужно ли renew."""
    cfg = _read_config()
    if not cfg.get("schedule_enabled"):
        return

    domain = cfg.get("domain")
    email  = cfg.get("email")
    if not domain or not email:
        log.info("[tls_scheduler] skip — domain/email не заданы")
        return

    interval_days = int(cfg.get("schedule_interval_days", 90))
    last_renew = cfg.get("renewed_at")
    days_since_renew = 9999
    if last_renew:
        try:
            renewed_dt = datetime.fromisoformat(last_renew.replace("Z", "+00:00"))
            days_since_renew = (datetime.now(timezone.utc) - renewed_dt).days
        except Exception:
            pass

    days_left = _days_left_in_cert() or 0
    should_renew = (days_since_renew >= interval_days) or (days_left < 30)

    if not should_renew:
        log.info(
            "[tls_scheduler] skip — days_since_renew=%d, days_left=%d, interval=%d",
            days_since_renew, days_left, interval_days,
        )
        return

    if not shutil.which("certbot"):
        log.warning("[tls_scheduler] certbot binary missing — skip auto-renew")
        return

    log.info("[tls_scheduler] starting renewal for %s (days_left=%d, interval=%d)",
             domain, days_left, interval_days)

    le_dir = CERT_DIR / "letsencrypt"
    cmd = [
        "certbot", "certonly",
        "--non-interactive", "--agree-tos",
        "--email", email,
        "-d", domain,
        "--webroot", "-w", str(CHALLENGE_WEBROOT),
        "--config-dir", str(le_dir / "config"),
        "--work-dir",   str(le_dir / "work"),
        "--logs-dir",   str(le_dir / "logs"),
        "--keep-until-expiring",
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        code = proc.returncode
    except Exception as e:
        log.error("[tls_scheduler] certbot exec failed: %s", e)
        cfg["last_le_attempt"] = datetime.now(timezone.utc).isoformat()
        cfg["last_le_result"] = {"code": -1, "error": str(e)}
        _write_config(cfg)
        return

    cfg["last_le_attempt"] = datetime.now(timezone.utc).isoformat()
    cfg["last_le_result"] = {
        "code": code,
        "stdout_tail": (stdout or b"").decode("utf-8", errors="replace")[-2000:],
        "stderr_tail": (stderr or b"").decode("utf-8", errors="replace")[-2000:],
    }

    if code == 0:
        le_live = le_dir / "config" / "live" / domain
        cert_src = le_live / "fullchain.pem"
        key_src = le_live / "privkey.pem"
        if cert_src.exists() and key_src.exists():
            (CERT_DIR / "fullchain.pem").write_text(cert_src.resolve().read_text())
            (CERT_DIR / "privkey.pem").write_text(key_src.resolve().read_text())
            try:
                os.chmod(CERT_DIR / "privkey.pem", 0o600)
                os.chmod(CERT_DIR / "fullchain.pem", 0o644)
            except Exception:
                pass
            cfg["source"] = "letsencrypt"
            cfg["renewed_at"] = datetime.now(timezone.utc).isoformat()
            log.info("[tls_scheduler] renewal SUCCESS for %s", domain)
        else:
            log.error("[tls_scheduler] cert files not found at %s", le_live)
    else:
        log.warning("[tls_scheduler] certbot exit %s for %s", code, domain)

    _write_config(cfg)


_TASK = None  # type: ignore
_STOP = None  # type: ignore
DAILY_INTERVAL_SEC = 24 * 3600


async def _loop() -> None:
    """Background asyncio loop — раз в 24h вызывает maybe_renew."""
    while True:
        try:
            await maybe_renew()
        except Exception as e:  # noqa: BLE001
            log.warning("[tls_scheduler] tick failed: %s", e)
        try:
            await asyncio.wait_for(_STOP.wait(), timeout=DAILY_INTERVAL_SEC)  # type: ignore
            break  # stop requested
        except asyncio.TimeoutError:
            continue


def start_tls_renewal_scheduler() -> None:
    """Стартует daily background-task. Вызывается из app startup.

    With uvicorn --workers N, lifespan runs N times. Without a lock, certbot
    would be invoked N times per tick — Let's Encrypt rate-limits at 5/cert/hour,
    so 4 workers × daily call burns the budget quickly. Postgres advisory lock
    ensures only one worker actually runs the renewal loop.
    """
    global _TASK, _STOP
    if _TASK is not None and not _TASK.done():
        return  # already running
    _STOP = asyncio.Event()

    async def _start_with_lock() -> None:
        from app.core.scheduler_lock import try_acquire_scheduler_lock
        held = await try_acquire_scheduler_lock("tls_renewal")
        if not held:
            log.info("[tls_scheduler] another worker holds the lock — this worker stays idle")
            return
        await _loop()

    _TASK = asyncio.create_task(_start_with_lock(), name="tls_renewal_loop")
    log.info("[tls_scheduler] daily renewal task spawned (lock acquisition deferred)")
