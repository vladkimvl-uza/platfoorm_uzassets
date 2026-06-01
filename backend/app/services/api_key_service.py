"""API key service (Pack 12.0).

Token format:  `uza_pk_{env}_{8-char prefix nonce}_{36-char secret body}`

- The full token is shown ONCE at creation time and never persists in storage.
- Only `prefix` (= "uza_pk_{env}_{8-char nonce}") and `hash_hmac` are stored.
- Verification: parse prefix → fetch row → HMAC the rest → constant-time compare.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime
from ipaddress import ip_address, ip_network
from typing import Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import KEY_PREFIX_LIVE, KEY_PREFIX_SANDBOX, ApiKey
from app.models.user import User


# Server-side HMAC key — loaded from a key file or required env var.
# In prod, the path defaults to /app/keys/audit_hmac.key (same secret used by
# audit chain — shared because both serve internal "tamper-evidence" purpose
# and rotating both together is acceptable). To use a separate key, set
# UZA_API_KEY_HMAC_SECRET (raw value, ≥ 32 bytes).
def _load_api_key_hmac() -> bytes:
    env_val = os.getenv("UZA_API_KEY_HMAC_SECRET", "")
    if env_val and len(env_val) >= 32:
        return env_val.encode("utf-8")
    secret_path = os.environ.get("AUDIT_HMAC_SECRET_PATH", "/app/keys/audit_hmac.key")
    if os.path.exists(secret_path):
        with open(secret_path, "rb") as f:
            secret = f.read().strip()
        if len(secret) >= 32:
            return secret
    raise RuntimeError(
        "API-key HMAC secret missing. Set UZA_API_KEY_HMAC_SECRET (≥32 bytes) "
        f"or mount a key file at {secret_path}."
    )

_HMAC_SECRET = _load_api_key_hmac()


# ════════════════════════════════════════════════════════════
#   Token generation
# ════════════════════════════════════════════════════════════

def _hmac_token(plaintext: str) -> str:
    """HMAC-SHA256(server_secret, plaintext). Hex-encoded."""
    return hmac.new(_HMAC_SECRET, plaintext.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_token(environment: str) -> tuple[str, str, str]:
    """Return (prefix, plaintext_token, hash_hmac).

    Prefix is what's stored & visible. Plaintext is shown once. Hash is what we store.
    """
    env_prefix = KEY_PREFIX_LIVE if environment == "production" else KEY_PREFIX_SANDBOX
    nonce  = secrets.token_urlsafe(6)[:8].replace("-", "x").replace("_", "y").lower()
    secret = secrets.token_urlsafe(27)  # ~36 chars

    prefix          = f"{env_prefix}{nonce}"
    plaintext_token = f"{prefix}_{secret}"
    hash_hmac       = _hmac_token(plaintext_token)
    return prefix, plaintext_token, hash_hmac


def parse_token_prefix(token: str) -> Optional[str]:
    """Extract prefix portion from a full token. Returns None if format is invalid."""
    if not (token.startswith(KEY_PREFIX_LIVE) or token.startswith(KEY_PREFIX_SANDBOX)):
        return None
    if "_" not in token:
        return None
    # Token = "uza_pk_live_xxxxxxxx_<secret>". Prefix = everything before the last underscore.
    parts = token.rsplit("_", 1)
    if len(parts) != 2 or len(parts[1]) < 16:
        return None
    return parts[0]


# ════════════════════════════════════════════════════════════
#   Verification
# ════════════════════════════════════════════════════════════

class ApiKeyAuthError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


async def verify_token(
    db: AsyncSession, token: str, *, client_ip: Optional[str] = None,
) -> tuple[ApiKey, User]:
    """Look up + verify an API key token.

    Returns (api_key_row, service_account_user). Raises ApiKeyAuthError on failure.
    Does NOT update last_used_at — that's done by middleware after success.
    """
    prefix = parse_token_prefix(token)
    if prefix is None:
        raise ApiKeyAuthError("invalid_format", "Token format is invalid")

    row = (await db.execute(
        select(ApiKey).where(ApiKey.prefix == prefix),
    )).scalars().first()
    if row is None:
        raise ApiKeyAuthError("not_found", "API key not recognised")

    expected = row.hash_hmac
    actual   = _hmac_token(token)
    if not hmac.compare_digest(expected, actual):
        raise ApiKeyAuthError("hash_mismatch", "API key signature mismatch")

    now = datetime.now(UTC)
    if row.revoked_at is not None:
        raise ApiKeyAuthError("revoked", f"Key was revoked at {row.revoked_at.isoformat()}")
    if row.expires_at is not None and now >= row.expires_at:
        raise ApiKeyAuthError("expired", "Key has expired")

    # IP allowlist
    if row.ip_allowlist and client_ip:
        try:
            client = ip_address(client_ip)
            allowed = False
            for cidr in row.ip_allowlist:
                try:
                    if client in ip_network(cidr, strict=False):
                        allowed = True
                        break
                except ValueError:
                    continue
            if not allowed:
                raise ApiKeyAuthError("ip_not_allowed", f"IP {client_ip} not in allowlist")
        except ValueError:
            pass  # Unparseable client IP → skip check, don't reject (e.g. unix socket)

    # Load the service account user (with roles + permissions for scope-vs-permission match)
    from sqlalchemy.orm import selectinload

    from app.models.user import Role
    user = (await db.execute(
        select(User)
        .where(User.id == row.service_account_id)
        .options(selectinload(User.roles).selectinload(Role.permissions)),
    )).scalars().first()
    if user is None:
        raise ApiKeyAuthError("orphan", "Service account user not found")
    if not user.is_active:
        raise ApiKeyAuthError("sa_disabled", "Service account is disabled")

    return row, user


def check_scope(key: ApiKey, required_permission: str) -> bool:
    """Return True if the key's scopes include the required permission code."""
    if not required_permission:
        return True
    return required_permission in (key.scopes or [])


async def record_call(
    db: AsyncSession, key: ApiKey, *, client_ip: Optional[str], success: bool,
) -> None:
    """Update telemetry counters. Caller commits."""
    key.total_calls = (key.total_calls or 0) + 1
    if not success:
        key.failed_calls = (key.failed_calls or 0) + 1
    key.last_used_at = datetime.now(UTC)
    if client_ip:
        key.last_used_ip = client_ip


# ════════════════════════════════════════════════════════════
#   Create / Revoke
# ════════════════════════════════════════════════════════════

async def create_api_key(
    db: AsyncSession, *,
    service_account_id: UUID,
    name: str,
    description: Optional[str],
    scopes: list[str],
    environment: str,
    rate_limit_per_minute: int,
    ip_allowlist: Optional[list[str]],
    expires_at: Optional[datetime],
    created_by_id: UUID,
) -> tuple[ApiKey, str]:
    """Create a new key. Returns (row, plaintext_token).

    plaintext_token must be returned to the caller and shown ONCE.
    """
    prefix, plaintext, hash_hex = generate_token(environment)
    now = datetime.now(UTC)

    row = ApiKey(
        created_at=now, updated_at=now,
        service_account_id=service_account_id,
        created_by_id=created_by_id,
        name=name, description=description,
        prefix=prefix, hash_hmac=hash_hex,
        scopes=list(scopes or []),
        environment=environment,
        rate_limit_per_minute=rate_limit_per_minute,
        ip_allowlist=ip_allowlist,
        expires_at=expires_at,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row, plaintext


async def revoke_api_key(
    db: AsyncSession, key: ApiKey, *, revoked_by_id: UUID, reason: Optional[str],
) -> ApiKey:
    if key.revoked_at:
        return key  # idempotent
    key.revoked_at = datetime.now(UTC)
    key.revoked_by_id = revoked_by_id
    key.revoke_reason = reason
    key.updated_at = key.revoked_at
    await db.commit()
    await db.refresh(key)
    return key


async def keys_count_for_service_account(db: AsyncSession, sa_id: UUID) -> int:
    return int((await db.execute(
        select(func.count(ApiKey.id)).where(and_(
            ApiKey.service_account_id == sa_id,
            ApiKey.revoked_at.is_(None),
        )),
    )).scalar_one() or 0)
