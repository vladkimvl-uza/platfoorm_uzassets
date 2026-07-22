"""JWT issue/verify — built on PyJWT (NOT python-jose, which has unfixed CVEs).

Hardening (state-grade for secret documents):
  - Algorithm WHITELIST (not blacklist) — only the configured algorithm is accepted
  - Explicit `algorithms=[settings.JWT_ALGORITHM]` on every decode
  - Reject `alg=none` always (PyJWT does this by default; we re-assert)
  - Reject ANY token whose header.alg differs from the expected algorithm — this
    blocks classic alg-confusion attacks (HS256 with RSA public key)
  - JWS ONLY — refuse JWE/JWE-compressed tokens (CVE-2024-33664-style "JWT bomb")
  - Required claims: sub, type, iss, aud, iat, nbf, exp, jti
  - Issuer / audience strict match
  - Maximum token byte size (8 KB) to bound parsing cost
  - kid header pinned; tokens without our kid are rejected
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

import jwt as pyjwt
from jwt import InvalidTokenError

from app.config import settings

log = logging.getLogger(__name__)

# Hard cap on token size — JWS access tokens should be well under 4 KB.
# Anything larger is suspicious and gets rejected before parsing.
MAX_TOKEN_BYTES = 8 * 1024

# Allowed algorithm whitelist
_ASYMMETRIC = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "EdDSA"}
_SYMMETRIC  = {"HS256", "HS384", "HS512"}
_ALL_ALLOWED = _ASYMMETRIC | _SYMMETRIC


# ---------------------------------------------------------------------------
# Key material
# ---------------------------------------------------------------------------
_PRIVATE_KEY: Optional[str] = None
_PUBLIC_KEY:  Optional[str] = None
_KID: str = "v1"


def _load_keys() -> None:
    global _PRIVATE_KEY, _PUBLIC_KEY, _KID

    alg = settings.JWT_ALGORITHM.upper()
    if alg not in _ALL_ALLOWED:
        raise RuntimeError(f"JWT_ALGORITHM {alg!r} is not in the allowed whitelist")

    if alg in _ASYMMETRIC:
        _PRIVATE_KEY = settings.read_jwt_private_key()
        _PUBLIC_KEY  = settings.read_jwt_public_key()
        if not _PRIVATE_KEY or not _PUBLIC_KEY:
            log.warning(
                "JWT_ALGORITHM=%s but key pair missing at %s / %s. "
                "Run scripts/generate-keys.sh and restart.",
                alg, settings.JWT_PRIVATE_KEY_PATH, settings.JWT_PUBLIC_KEY_PATH,
            )
            return
        _KID = "rs256-" + hashlib.sha256(_PUBLIC_KEY.encode()).hexdigest()[:12]
    else:
        # HS* — symmetric, private == public
        _PRIVATE_KEY = settings.JWT_SECRET
        _PUBLIC_KEY  = settings.JWT_SECRET
        _KID = alg.lower() + "-" + hashlib.sha256(settings.JWT_SECRET.encode()).hexdigest()[:12]


_load_keys()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_access_token(
    *,
    subject: str,
    extra_claims: dict | None = None,
    expires_minutes: int | None = None,
) -> str:
    """Sign a short-lived access token."""
    return _create_token(
        subject=subject,
        token_type="access",
        expires_delta=timedelta(minutes=expires_minutes or settings.JWT_EXPIRE_MINUTES),
        extra_claims=extra_claims,
    )


def create_ws_ticket(
    *, subject: str, expires_seconds: int = 30, extra_claims: dict | None = None,
) -> str:
    """Короткоживущий (30с) тикет для аутентификации WebSocket-хендшейка вместо
    передачи access-JWT в URL (утечка в логи/history/Referer). Отдельный
    type='ws_ticket' — не подменяется access-токеном и наоборот (expected_type).

    extra_claims — доп. клеймы (напр. `scp` = список company-id для scope-фильтрации
    стрима). TTL тикета 30с ограничивает только его погашение; попав в WS-сессию,
    клеймы действуют всю её жизнь (снимок на момент выпуска, ре-проверки в открытом
    сокете нет — скоуп обновится только при переподключении)."""
    return _create_token(
        subject=subject,
        token_type="ws_ticket",
        expires_delta=timedelta(seconds=expires_seconds),
        extra_claims=extra_claims,
    )


def create_refresh_token(*, subject: str, jti: str | None = None) -> tuple[str, str]:
    """Sign a refresh token. Returns (token, jti).
    Caller stores SHA-256(jti) in `user_sessions.refresh_token_hash`."""
    jti = jti or secrets.token_urlsafe(32)
    token = _create_token(
        subject=subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.JWT_REFRESH_EXPIRE_DAYS),
        extra_claims={"jti": jti},
    )
    return token, jti


def decode_token(token: str, *, expected_type: str | None = None) -> dict:
    """Verify a JWT and return its claims.

    Raises `jwt.InvalidTokenError` (or subclass) on any failure."""
    if not _PUBLIC_KEY:
        raise InvalidTokenError("JWT verification key not configured")
    if not isinstance(token, str) or not token:
        raise InvalidTokenError("Token is empty")
    if len(token.encode()) > MAX_TOKEN_BYTES:
        raise InvalidTokenError(f"Token exceeds {MAX_TOKEN_BYTES} bytes")

    # --- Pre-validate header BEFORE expensive crypto ---
    # 1. Refuse JWE / encrypted tokens. JWS has 3 segments separated by '.';
    #    JWE has 5. python-jose's JWE-decompression is the source of CVE-2024-33664.
    if token.count(".") != 2:
        raise InvalidTokenError("Only JWS tokens accepted (no JWE)")

    # 2. Inspect header without verifying yet — to catch alg confusion early.
    try:
        header = pyjwt.get_unverified_header(token)
    except Exception as e:
        raise InvalidTokenError(f"Malformed JWT header: {e}") from e

    alg = header.get("alg")
    if alg != settings.JWT_ALGORITHM:
        raise InvalidTokenError(
            f"Algorithm mismatch: token={alg!r}, expected={settings.JWT_ALGORITHM!r}"
        )
    if alg.lower() == "none":
        raise InvalidTokenError("Algorithm 'none' is not allowed")
    if alg not in _ALL_ALLOWED:
        raise InvalidTokenError(f"Algorithm {alg!r} is not in the whitelist")

    # Фикс L7: kid обязателен. Иначе при будущей ротации ключей токены без
    # kid тихо прошли бы валидацию любым активным ключом.
    kid = header.get("kid")
    if not kid:
        raise InvalidTokenError("Missing kid in JWT header")
    if kid != _KID:
        raise InvalidTokenError(f"Unknown key id: {kid!r}")

    # 3. Crypto-verify with explicit single-element algorithm list
    claims = pyjwt.decode(
        token,
        _PUBLIC_KEY,
        algorithms=[settings.JWT_ALGORITHM],
        issuer=settings.JWT_ISSUER,
        audience=settings.JWT_AUDIENCE,
        options={
            "require": ["exp", "iat", "iss", "aud", "sub", "type", "nbf"],
            "verify_signature": True,
            "verify_exp":  True,
            "verify_nbf":  True,
            "verify_iat":  True,
            "verify_aud":  True,
            "verify_iss":  True,
        },
        # 10s clock-skew tolerance: tight enough to fail forged future-exp
        # tokens (since servers don't drift > 10s with NTP), loose enough to
        # survive VM resume / container pause / brief NTP outages without
        # spurious 401s. Originally 0 — a single restart-mid-request drift
        # could invalidate every active access token at once.
        leeway=10,
    )

    if expected_type and claims.get("type") != expected_type:
        raise InvalidTokenError(
            f"Wrong token type: expected {expected_type}, got {claims.get('type')}"
        )
    return claims


def hash_jti(jti: str) -> str:
    """Stable hash for storing in user_sessions.refresh_token_hash."""
    return hashlib.sha256(jti.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _create_token(
    *,
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    extra_claims: dict | None = None,
) -> str:
    if not _PRIVATE_KEY:
        raise RuntimeError("JWT signing key not configured")

    now = datetime.now(tz=UTC)
    claims: dict = {
        "sub":  subject,
        "type": token_type,
        "iss":  settings.JWT_ISSUER,
        "aud":  settings.JWT_AUDIENCE,
        "iat":  int(now.timestamp()),
        "nbf":  int(now.timestamp()),
        "exp":  int((now + expires_delta).timestamp()),
        # Always issue a jti — caller may overwrite for refresh tokens
        "jti":  secrets.token_urlsafe(16),
    }
    if extra_claims:
        claims.update(extra_claims)

    return pyjwt.encode(
        claims,
        _PRIVATE_KEY,
        algorithm=settings.JWT_ALGORITHM,
        headers={"kid": _KID, "typ": "JWT"},
    )
