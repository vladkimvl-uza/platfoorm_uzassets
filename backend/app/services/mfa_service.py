"""MFA service (Pack 13.0).

All operations on:
- Login challenges (one-shot 6-digit codes via Telegram)
- Telegram link flow (deep-link token → bot confirms → user has chat_id)
- Recovery codes (10 × XXXX-XXXX, bcrypt-hashed, one-time)
- Notification prefs

Code formats:
- Login code: 6 random digits, plaintext to TG, bcrypt-hashed in DB
- Link token: 12 url-safe chars, plaintext shown to user once, sha256 in DB
- Recovery code: 10 × "XXXX-XXXX" (8 hex chars + dash), bcrypt hash in DB

Security notes:
- Telegram chat_id is encrypted with Fernet (no plaintext in DB)
- Recovery codes hashed with bcrypt (one-way)
- Link tokens are sha256-hashed (we just need equality check, no need for bcrypt cost)
- Login code attempts capped at 5 per challenge → mark used_at = now to invalidate
"""
import hashlib
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Optional

import bcrypt
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_int, encrypt_int
from app.core.i18n import normalize_locale
from app.models.mfa import (
    MfaLoginChallenge,
    MfaMethod,
    OutboxStatus,
    OutboxType,
    TelegramOutbox,
    UserTelegramPref,
)
from app.models.user import User

# ── Constants ────────────────────────────────────────────────────────────

LOGIN_CODE_TTL_MINUTES = 5
LINK_TOKEN_TTL_MINUTES = 5
LOGIN_CODE_MAX_ATTEMPTS = 5
RECOVERY_CODES_COUNT = 10


# ── Hashing helpers ──────────────────────────────────────────────────────

def _hash_bcrypt(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def _check_bcrypt(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _hash_sha256(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


# ── Code generators ──────────────────────────────────────────────────────

def _gen_login_code() -> str:
    """6-digit numeric code, leading zeros preserved."""
    return f"{secrets.randbelow(1_000_000):06d}"


def _gen_link_token() -> str:
    """12-char url-safe token for deep-link in /start ABC123XYZ456."""
    return secrets.token_urlsafe(9)[:12].upper().replace("_", "X").replace("-", "Y")


def _gen_recovery_code() -> str:
    """One recovery code: XXXX-XXXX (hex)."""
    raw = secrets.token_hex(4).upper()  # 8 hex chars
    return f"{raw[:4]}-{raw[4:]}"


def generate_recovery_codes() -> list[str]:
    """Generate 10 fresh codes; caller is responsible for hashing+storing."""
    return [_gen_recovery_code() for _ in range(RECOVERY_CODES_COUNT)]


# ── Telegram outbox enqueue ──────────────────────────────────────────────

# ── Login challenge flow ─────────────────────────────────────────────────

async def verify_login_challenge(
    db: AsyncSession, challenge_id: str, code: str,
) -> bool:
    """Verify a 6-digit code. Increments attempts; marks used if successful.

    Returns True on first valid match, False otherwise.
    """
    import asyncio
    now = datetime.now(UTC)
    result = await db.execute(
        select(MfaLoginChallenge).where(MfaLoginChallenge.id == challenge_id)
    )
    ch: Optional[MfaLoginChallenge] = result.scalar_one_or_none()
    if ch is None:
        return False
    if ch.used_at is not None:
        return False
    if ch.expires_at < now:
        return False
    if ch.attempts >= LOGIN_CODE_MAX_ATTEMPTS:
        return False

    # Exponential backoff against brute force. Per-challenge sleep BEFORE
    # the bcrypt check so an attacker burning through 5 attempts is
    # serialized (1+2+4+8s = 15s lockout on top of bcrypt cost).
    if ch.attempts > 0:
        delay = min(2 ** (ch.attempts - 1), 30)  # 1s, 2s, 4s, 8s, 16s; cap 30
        await asyncio.sleep(delay)

    ch.attempts += 1
    if not _check_bcrypt(code, ch.code_hashed):
        await db.flush()
        return False

    ch.used_at = now
    await db.flush()
    return True


def get_recovery_codes(user: User) -> list[str]:
    """Read recovery code hashes from encrypted column first, fall back to
    legacy plaintext-array column for users not yet lazy-migrated.
    """
    from app.core.encryption import try_decrypt_json_list
    enc = getattr(user, "mfa_recovery_codes_enc", None)
    if enc:
        decoded = try_decrypt_json_list(enc)
        if decoded is not None:
            return list(decoded)
    return list(getattr(user, "mfa_recovery_codes_hashed", None) or [])


def set_recovery_codes(user: User, codes: list[str] | None) -> None:
    """Write recovery code hashes to encrypted column; clear legacy column.
    Pass None or empty list to clear both. Falls back to legacy column write
    if encryption isn't configured (shouldn't happen in prod — startup check
    guards this).
    """
    from app.core.encryption import encrypt_json_list
    if not codes:
        user.mfa_recovery_codes_enc = None
        user.mfa_recovery_codes_hashed = None
        return
    try:
        user.mfa_recovery_codes_enc = encrypt_json_list(codes)
        user.mfa_recovery_codes_hashed = None
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(
            "recovery codes Fernet encrypt failed, falling back to legacy: %s", e,
        )
        user.mfa_recovery_codes_hashed = codes
        user.mfa_recovery_codes_enc = None


async def verify_recovery_code(db: AsyncSession, user: User, code: str) -> bool:
    """Verify a recovery code; if valid, removes that hash from the user's list.

    Returns True if accepted (and one code consumed), False otherwise.
    """
    code = code.strip().upper()
    hashes = get_recovery_codes(user)
    matched_idx: Optional[int] = None
    for i, h in enumerate(hashes):
        if _check_bcrypt(code, h):
            matched_idx = i
            break
    if matched_idx is None:
        return False
    hashes.pop(matched_idx)
    set_recovery_codes(user, hashes)
    await db.flush()
    return True


# ── Telegram link flow ───────────────────────────────────────────────────

def get_chat_id(user: User) -> Optional[int]:
    """Decrypt the user's Telegram chat_id, or None if not linked."""
    enc = getattr(user, "telegram_chat_id_encrypted", None)
    if not enc:
        return None
    try:
        return decrypt_int(enc)
    except Exception:
        return None


# ── Notification prefs ───────────────────────────────────────────────────

async def get_or_create_pref(db: AsyncSession, user_id: str) -> UserTelegramPref:
    """Return the row for user_id; create with defaults if absent."""
    result = await db.execute(
        select(UserTelegramPref).where(UserTelegramPref.user_id == user_id)
    )
    pref: Optional[UserTelegramPref] = result.scalar_one_or_none()
    if pref is None:
        pref = UserTelegramPref(user_id=user_id, updated_at=datetime.now(UTC))
        db.add(pref)
        await db.flush()
    return pref


async def update_pref(
    db: AsyncSession, user_id: str, **changes
) -> UserTelegramPref:
    pref = await get_or_create_pref(db, user_id)
    for k, v in changes.items():
        if v is not None and hasattr(pref, k):
            setattr(pref, k, v)
    pref.updated_at = datetime.now(UTC)
    await db.flush()
    return pref


# Map full Notification.type → UserTelegramPref column name.
# Keep in sync with telegram_notify_hook.TYPE_TO_PREF_FIELD.
_NOTIFICATION_TYPE_TO_PREF_FIELD: dict[str, str] = {
    # Moderation cluster
    "moderation.pending":          "type_moderation",
    "moderation.approved":         "type_moderation",
    "moderation.rejected":         "type_moderation",
    "moderation.review_requested": "type_moderation",
    "moderation.escalated":        "type_moderation",
    "moderation.expired":          "type_moderation",
    # Interactions
    "mention":         "type_mentions",
    "assignment":      "type_assignments",
    "comment.replied": "type_mentions",
    "comment.created": "type_mentions",
    "comment.updated": "type_mentions",
    "comment.deleted": "type_mentions",
    # Deadlines
    "deadline.approaching": "type_deadlines",
    "deadline.missed":      "type_deadlines",
    # KPI / audit / RBAC
    "kpi.target.missed":   "type_system",
    "kpi.achieved":        "type_system",
    "audit.security_flag": "type_system",
    "rbac.changed":        "type_system",
    # System
    "system.announcement":    "type_system",
    "data.imported":          "type_system",
    "report.ready":           "type_system",
    "broadcast.announcement": "type_broadcasts",
}

# Short keys → pref column. Kept for legacy callers.
_SHORT_KEY_TO_PREF_FIELD: dict[str, str] = {
    "assignment":  "type_assignments",
    "assignments": "type_assignments",
    "mention":     "type_mentions",
    "mentions":    "type_mentions",
    "deadline":    "type_deadlines",
    "deadlines":   "type_deadlines",
    "moderation":  "type_moderation",
    "broadcast":   "type_broadcasts",
    "broadcasts":  "type_broadcasts",
    "system":      "type_system",
}

_PREF_FIELDS = {
    "type_assignments", "type_mentions", "type_deadlines",
    "type_moderation", "type_broadcasts", "type_system",
}


def _resolve_pref_field(
    *, pref_field: Optional[str], notification_type: Optional[str],
) -> Optional[str]:
    """Pick the correct UserTelegramPref boolean column to check."""
    if pref_field and pref_field in _PREF_FIELDS:
        return pref_field
    if notification_type:
        # Try full key (e.g. "comment.replied"), then short alias.
        if notification_type in _NOTIFICATION_TYPE_TO_PREF_FIELD:
            return _NOTIFICATION_TYPE_TO_PREF_FIELD[notification_type]
        if notification_type in _SHORT_KEY_TO_PREF_FIELD:
            return _SHORT_KEY_TO_PREF_FIELD[notification_type]
    return None


def _in_quiet_hours(pref: UserTelegramPref) -> bool:
    """Check current time against pref's tz; handles wrap-around (22→07)."""
    try:
        import zoneinfo
        tz = zoneinfo.ZoneInfo(pref.timezone or "Asia/Tashkent")
    except Exception:
        return False
    now = datetime.now(tz).time()
    s, e = pref.quiet_hours_start, pref.quiet_hours_end
    if s <= e:
        return s <= now <= e
    # Wrap-around (e.g. 22:00–07:00)
    return now >= s or now <= e


# ── Status helper ────────────────────────────────────────────────────────

def build_status(user: User) -> dict:
    method = getattr(user, "mfa_method", None) or MfaMethod.NONE
    if hasattr(method, "value"):
        method = method.value
    codes = get_recovery_codes(user)
    return {
        "enabled": bool(getattr(user, "mfa_enabled", False)),
        "method": method,
        "telegram_linked": bool(getattr(user, "telegram_chat_id_encrypted", None)),
        "telegram_username": getattr(user, "telegram_username", None),
        "telegram_linked_at": getattr(user, "telegram_linked_at", None),
        "recovery_codes_remaining": len(codes),
        "recovery_codes_total": RECOVERY_CODES_COUNT,
    }
