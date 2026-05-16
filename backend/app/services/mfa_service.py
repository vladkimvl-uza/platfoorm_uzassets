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
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import bcrypt
from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_int, decrypt_int, encrypt, decrypt
from app.models.mfa import (
    MfaLoginChallenge, MfaMethod, OutboxStatus, OutboxType,
    TelegramOutbox, UserTelegramPref,
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

async def enqueue_telegram_message(
    db: AsyncSession,
    user_id: str,
    msg_type: OutboxType,
    payload: dict,
    inline_buttons: Optional[list[dict]] = None,
) -> TelegramOutbox:
    """Insert a row into telegram_outbox; uza-tg-bot worker picks it up.

    payload structure depends on msg_type — see services/telegram_format.py
    (which the bot worker reads to render the actual message).
    """
    row = TelegramOutbox(
        user_id=user_id,
        type=msg_type,
        status=OutboxStatus.PENDING,
        payload=payload,
        inline_buttons=inline_buttons,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return row


# ── Login challenge flow ─────────────────────────────────────────────────

async def emit_login_challenge(
    db: AsyncSession, user: User, ip: Optional[str] = None, ua: Optional[str] = None,
) -> Tuple[MfaLoginChallenge, str]:
    """Create a 6-digit code, store hash, enqueue to TG outbox.

    Returns (challenge_row, plaintext_code) — only ever returned during this call.
    Frontend should NEVER see the plaintext_code; it's enqueued straight to TG.

    Raises ValueError if user has no telegram_chat_id or 2FA isn't telegram-based.
    """
    if not getattr(user, "telegram_chat_id_encrypted", None):
        raise ValueError("User has no linked Telegram chat")
    if not getattr(user, "mfa_enabled", False):
        raise ValueError("User does not have MFA enabled")

    code = _gen_login_code()
    now = datetime.now(timezone.utc)
    challenge = MfaLoginChallenge(
        user_id=user.id,
        code_hashed=_hash_bcrypt(code),
        created_at=now,
        expires_at=now + timedelta(minutes=LOGIN_CODE_TTL_MINUTES),
        ip_address=ip[:64] if ip else None,
        user_agent=ua[:256] if ua else None,
    )
    db.add(challenge)
    await db.flush()

    # Enqueue MFA code message — the bot worker will format and deliver
    await enqueue_telegram_message(
        db, user.id, OutboxType.MFA_CODE,
        payload={
            "code": code,
            "ttl_minutes": LOGIN_CODE_TTL_MINUTES,
            "ip": ip,
            "user_agent": (ua or "")[:128],
            "challenge_id": str(challenge.id),
        },
    )
    return challenge, code


async def verify_login_challenge(
    db: AsyncSession, challenge_id: str, code: str,
) -> bool:
    """Verify a 6-digit code. Increments attempts; marks used if successful.

    Returns True on first valid match, False otherwise.
    """
    now = datetime.now(timezone.utc)
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

    ch.attempts += 1
    if not _check_bcrypt(code, ch.code_hashed):
        await db.flush()
        return False

    ch.used_at = now
    await db.flush()
    return True


async def verify_recovery_code(db: AsyncSession, user: User, code: str) -> bool:
    """Verify a recovery code; if valid, removes that hash from the user's list.

    Returns True if accepted (and one code consumed), False otherwise.
    """
    code = code.strip().upper()
    hashes: list[str] = list(getattr(user, "mfa_recovery_codes_hashed", None) or [])
    matched_idx: Optional[int] = None
    for i, h in enumerate(hashes):
        if _check_bcrypt(code, h):
            matched_idx = i
            break
    if matched_idx is None:
        return False
    hashes.pop(matched_idx)
    user.mfa_recovery_codes_hashed = hashes
    await db.flush()
    return True


# ── Telegram link flow ───────────────────────────────────────────────────

async def init_link_telegram(db: AsyncSession, user: User) -> Tuple[str, datetime]:
    """Generate a one-time link token; store its sha256 hash + expiry on user.

    Returns (plaintext_token, expires_at) — frontend shows the token for the
    user to paste into the bot as `/start <token>`.
    """
    token = _gen_link_token()
    now = datetime.now(timezone.utc)
    user.telegram_link_token_hashed = _hash_sha256(token)
    user.telegram_link_token_expires_at = now + timedelta(minutes=LINK_TOKEN_TTL_MINUTES)
    await db.flush()
    return token, user.telegram_link_token_expires_at


async def confirm_link_telegram(
    db: AsyncSession, token: str, chat_id: int, username: Optional[str],
) -> Optional[User]:
    """Called by the bot worker on /start <token>.

    Looks up the user by token hash + non-expired + token still set.
    On success: sets telegram_chat_id_encrypted + username + linked_at,
    clears the token, optionally enables MFA if not already.

    Returns the User on success, None if token invalid/expired/already-used.
    """
    token = token.strip()
    if not token:
        return None
    h = _hash_sha256(token)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(User).where(
            and_(
                User.telegram_link_token_hashed == h,
                User.telegram_link_token_expires_at > now,
            )
        )
    )
    user: Optional[User] = result.scalar_one_or_none()
    if user is None:
        return None

    user.telegram_chat_id_encrypted = encrypt_int(chat_id)
    user.telegram_username = (username or "")[:64] or None
    user.telegram_linked_at = now
    user.telegram_link_token_hashed = None
    user.telegram_link_token_expires_at = None
    await db.flush()

    # Send confirmation back via outbox so the bot sees a delivery in its queue
    await enqueue_telegram_message(
        db, user.id, OutboxType.LINK_CONFIRMATION,
        payload={"email": user.email, "username": user.telegram_username},
    )
    return user


async def unlink_telegram(db: AsyncSession, user: User) -> None:
    """Wipe all Telegram-related fields. Does NOT disable MFA (user can still use recovery codes)."""
    user.telegram_chat_id_encrypted = None
    user.telegram_username = None
    user.telegram_linked_at = None
    user.telegram_link_token_hashed = None
    user.telegram_link_token_expires_at = None
    # If MFA method was telegram-only, disable MFA entirely
    if getattr(user, "mfa_method", None) == MfaMethod.TELEGRAM:
        user.mfa_enabled = False
        user.mfa_method = MfaMethod.NONE
    await db.flush()


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
        pref = UserTelegramPref(user_id=user_id, updated_at=datetime.now(timezone.utc))
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
    pref.updated_at = datetime.now(timezone.utc)
    await db.flush()
    return pref


def should_route_to_telegram(
    pref: Optional[UserTelegramPref], notification_type: str, severity: str = "normal",
) -> bool:
    """Decision: should we enqueue this notification to TG for this user?

    notification_type ∈ {assignment, mention, deadline, moderation, broadcast, system}
    severity ∈ {critical, high, normal, low}
    """
    if pref is None or not pref.enabled:
        return False

    type_map = {
        "assignment":  pref.type_assignments,
        "assignments": pref.type_assignments,
        "mention":     pref.type_mentions,
        "mentions":    pref.type_mentions,
        "deadline":    pref.type_deadlines,
        "deadlines":   pref.type_deadlines,
        "moderation":  pref.type_moderation,
        "broadcast":   pref.type_broadcasts,
        "broadcasts":  pref.type_broadcasts,
        "system":      pref.type_system,
    }
    if not type_map.get(notification_type, False):
        return False

    # Severity = critical bypasses quiet hours; everything else respects them
    if pref.quiet_hours_enabled and severity != "critical":
        if _in_quiet_hours(pref):
            return False
    return True


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
    codes = getattr(user, "mfa_recovery_codes_hashed", None) or []
    return {
        "enabled": bool(getattr(user, "mfa_enabled", False)),
        "method": method,
        "telegram_linked": bool(getattr(user, "telegram_chat_id_encrypted", None)),
        "telegram_username": getattr(user, "telegram_username", None),
        "telegram_linked_at": getattr(user, "telegram_linked_at", None),
        "recovery_codes_remaining": len(codes),
        "recovery_codes_total": RECOVERY_CODES_COUNT,
    }
