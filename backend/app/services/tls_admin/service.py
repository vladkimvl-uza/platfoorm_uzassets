"""TLS certificate admin operations.

Pure filesystem + subprocess service (no DB). Audit logging stays in
route file because it uses the raw AsyncSession + actor IP/UA from
the request.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

log = logging.getLogger(__name__)


CERT_DIR = Path(os.environ.get("TLS_CERT_DIR", "/app/certs"))
CHALLENGE_DIR = Path(os.environ.get("TLS_ACME_WEBROOT", "/app/certs/.well-known"))
CONFIG_PATH = CERT_DIR / "config.json"


def ensure_dirs() -> None:
    CERT_DIR.mkdir(parents=True, exist_ok=True)
    CHALLENGE_DIR.mkdir(parents=True, exist_ok=True)


def bootstrap_canonical_cert() -> None:
    """If fullchain.pem/privkey.pem missing, seed from dev-* fallback."""
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
            log.info("[tls] bootstrap: seeded fullchain.pem from dev-fullchain.pem")
        except Exception as e:
            log.warning("[tls] bootstrap failed: %s", e)


# ─── config persistence ───────────────────────────────────────────

def read_config() -> dict[str, Any]:
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


def write_config(cfg: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, default=str))


# ─── cert introspection ───────────────────────────────────────────

def parse_cert(pem_path: Path) -> dict[str, Any]:
    if not pem_path.exists():
        return {"present": False}
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        pem_bytes = pem_path.read_bytes()
        cert = x509.load_pem_x509_certificate(pem_bytes, default_backend())
        now = datetime.now(UTC)
        not_after = cert.not_valid_after_utc
        not_before = cert.not_valid_before_utc
        days_left = max(0, (not_after - now).days)
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
            "mtime": datetime.fromtimestamp(pem_path.stat().st_mtime, UTC).isoformat(),
        }
    except Exception as e:
        return {"present": True, "parse_error": str(e), "size_bytes": pem_path.stat().st_size}


def _candidate_paths() -> list[tuple[str, Path, Path]]:
    return [
        ("production",   CERT_DIR / "fullchain.pem",     CERT_DIR / "privkey.pem"),
        ("dev-fallback", CERT_DIR / "dev-fullchain.pem", CERT_DIR / "dev-privkey.pem"),
    ]


def current_active() -> tuple[Optional[str], Optional[Path], Optional[Path]]:
    for label, cert, key in _candidate_paths():
        if cert.exists() and key.exists():
            return label, cert, key
    return None, None, None


# ─── operations ───────────────────────────────────────────────────

class TlsAdminService:
    """File/process operations; no DB."""

    def get_status(self) -> dict:
        label, cert_p, key_p = current_active()
        info = parse_cert(cert_p) if cert_p else {"present": False}
        cfg = read_config()
        return {
            "active_label": label,
            "cert_path": str(cert_p) if cert_p else None,
            "key_path": str(key_p) if key_p else None,
            "info": info,
            "config": cfg,
        }

    def upload_cert(
        self, *, cert_pem: str, key_pem: str,
    ) -> dict:
        """Validate + write cert/key, backup existing. Returns info dict."""
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            x509.load_pem_x509_certificate(cert_pem.encode(), default_backend())
            load_pem_private_key(key_pem.encode(), password=None, backend=default_backend())
        except Exception as e:
            raise HTTPException(400, f"PEM невалидный: {e}")

        cert_path = CERT_DIR / "fullchain.pem"
        key_path = CERT_DIR / "privkey.pem"
        backup_dir = CERT_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        if cert_path.exists():
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(cert_path, backup_dir / f"fullchain-{ts}.pem")
            shutil.copy2(key_path, backup_dir / f"privkey-{ts}.pem")

        cert_path.write_text(cert_pem.strip() + "\n")
        key_path.write_text(key_pem.strip() + "\n")
        try:
            os.chmod(key_path, 0o600)
            os.chmod(cert_path, 0o644)
        except Exception:
            pass

        info = parse_cert(cert_path)
        cfg = read_config()
        cfg.update({
            "source": "manual",
            "renewed_at": datetime.now(UTC).isoformat(),
            "domain": info.get("san", [None])[0] if info.get("san") else cfg.get("domain"),
        })
        write_config(cfg)
        return info

    async def run_letsencrypt(
        self, *, domain: str, email: str, staging: bool,
    ) -> tuple[dict, str]:
        """Run certbot certonly. Returns (info, stdout_tail).
        Raises HTTPException on failure."""
        if not shutil.which("certbot"):
            raise HTTPException(
                500,
                "certbot не установлен в backend-контейнере. "
                "Добавьте `certbot` в backend/Dockerfile (apt-get install certbot), "
                "пересоберите образ. Альтернатива: используйте manual upload.",
            )

        domain = domain.strip().lower()
        email = email.strip().lower()
        le_dir = CERT_DIR / "letsencrypt"
        le_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "certbot", "certonly",
            "--non-interactive", "--agree-tos",
            "--email", email,
            "-d", domain,
            "--webroot",
            "-w", str(CHALLENGE_DIR.parent),
            "--config-dir", str(le_dir / "config"),
            "--work-dir",   str(le_dir / "work"),
            "--logs-dir",   str(le_dir / "logs"),
            "--keep-until-expiring",
        ]
        if staging:
            cmd.append("--staging")

        cfg = read_config()
        cfg["last_le_attempt"] = datetime.now(UTC).isoformat()
        cfg["domain"] = domain
        cfg["email"] = email

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            code = proc.returncode
            stdout_s = stdout.decode("utf-8", errors="replace")
            stderr_s = stderr.decode("utf-8", errors="replace")
        except TimeoutError:
            raise HTTPException(504, "certbot выполнялся больше 120s — прерван")
        except Exception as e:
            raise HTTPException(500, f"certbot execution failed: {e}")

        cfg["last_le_result"] = {
            "code": code,
            "stdout_tail": stdout_s[-2000:],
            "stderr_tail": stderr_s[-2000:],
        }

        info: dict[str, Any] = {}
        if code == 0:
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
                cert_dst.write_text(cert_src.resolve().read_text())
                key_dst.write_text(key_src.resolve().read_text())
                try:
                    os.chmod(key_dst, 0o600)
                    os.chmod(cert_dst, 0o644)
                except Exception:
                    pass
                cfg["source"] = "letsencrypt"
                cfg["renewed_at"] = datetime.now(UTC).isoformat()
            info = parse_cert(CERT_DIR / "fullchain.pem")

        write_config(cfg)

        if code != 0:
            raise HTTPException(
                400,
                f"certbot failed (exit {code}). stderr: {stderr_s[-500:]}",
            )

        return info, stdout_s[-1000:]

    def update_schedule(self, *, enabled: bool, interval_days: int) -> dict:
        cfg = read_config()
        cfg["schedule_enabled"] = enabled
        cfg["schedule_interval_days"] = interval_days
        write_config(cfg)
        return cfg
