"""Fernet symmetric encryption for sensitive fields (Pack 13.0).

Stores: telegram_chat_id, telegram_link_token raw value (we also hash for verify),
future TOTP secrets. Recovery codes use bcrypt hash (one-way), not Fernet.

Configuration:
    MFA_ENCRYPTION_KEY env var — base64 Fernet key (urlsafe, 32 bytes raw).
    Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'

Key rotation:
    Set MFA_ENCRYPTION_KEY to "NEW_KEY,OLD_KEY" (comma-separated, newest first).
    MultiFernet tries each in order on decrypt; encrypt always uses the first key.
    Re-encrypt over time via background job, then drop OLD_KEY.
"""
import os
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class EncryptionNotConfigured(RuntimeError):
    """Raised when MFA_ENCRYPTION_KEY is missing — fail fast at first use."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet | MultiFernet:
    keys = os.getenv("MFA_ENCRYPTION_KEY", "").strip()
    if not keys:
        raise EncryptionNotConfigured(
            "MFA_ENCRYPTION_KEY env var is empty. "
            "Generate a key: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' "
            "and add to backend .env"
        )
    key_list = [k.strip() for k in keys.split(",") if k.strip()]
    fernets = [Fernet(k.encode()) for k in key_list]
    if len(fernets) == 1:
        return fernets[0]
    return MultiFernet(fernets)


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────

def encrypt(value: Optional[str]) -> Optional[bytes]:
    """Encrypt a string; returns None for None input."""
    if value is None:
        return None
    return _fernet().encrypt(value.encode("utf-8"))


def decrypt(token: Optional[bytes]) -> Optional[str]:
    """Decrypt a Fernet token; returns None for None input.

    Raises cryptography.fernet.InvalidToken if the value was encrypted with
    a key that's no longer in MFA_ENCRYPTION_KEY (rotation gone bad).
    """
    if token is None:
        return None
    # memoryview / bytes from psycopg2 sometimes come as `memoryview` — coerce
    if isinstance(token, memoryview):
        token = bytes(token)
    return _fernet().decrypt(token).decode("utf-8")


def encrypt_int(value: Optional[int]) -> Optional[bytes]:
    """Encrypt an integer (Telegram chat_id, etc)."""
    if value is None:
        return None
    return encrypt(str(value))


def decrypt_int(token: Optional[bytes]) -> Optional[int]:
    """Decrypt an integer token; returns None for None input."""
    if token is None:
        return None
    return int(decrypt(token))


def try_decrypt(token: Optional[bytes]) -> Optional[str]:
    """Best-effort decrypt — returns None on InvalidToken instead of raising.

    Use for non-critical paths where a corrupted/rotated token shouldn't crash
    the whole request (e.g. listing users whose mfa state may be old).
    """
    try:
        return decrypt(token)
    except (InvalidToken, EncryptionNotConfigured, Exception):
        return None


# ────────────────────────────────────────────────────────────────────────────
# JSON-list helpers (P2-3, P2-4) — wrap a list of strings as a single Fernet
# blob. Used for password_history (bcrypt-hash list) and mfa_recovery_codes
# (bcrypt-hash list). Both are already one-way hashes, but wrapping in
# Fernet adds defense-in-depth against backup-on-disk theft.
# ────────────────────────────────────────────────────────────────────────────
import json


def encrypt_json_list(items: Optional[list[str]]) -> Optional[bytes]:
    """Serialize a list of strings to JSON and Fernet-encrypt the blob.
    Returns None for None or empty list (don't waste a blob on []).
    """
    if not items:
        return None
    return _fernet().encrypt(json.dumps(items, separators=(",", ":")).encode("utf-8"))


def decrypt_json_list(token: Optional[bytes]) -> Optional[list[str]]:
    """Decrypt a Fernet token previously produced by encrypt_json_list."""
    if token is None:
        return None
    if isinstance(token, memoryview):
        token = bytes(token)
    raw = _fernet().decrypt(token).decode("utf-8")
    val = json.loads(raw)
    if not isinstance(val, list):
        raise ValueError(f"decrypt_json_list got non-list: {type(val)}")
    return val


def try_decrypt_json_list(token: Optional[bytes]) -> Optional[list[str]]:
    """Best-effort decrypt — returns None on any error (rotation gone bad,
    corruption, missing key). Caller falls back to legacy plaintext column.
    """
    try:
        return decrypt_json_list(token)
    except Exception:
        return None
