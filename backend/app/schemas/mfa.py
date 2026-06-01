"""MFA pydantic schemas (Pack 13.0)."""
from datetime import datetime, time
from typing import Literal, Optional

from pydantic import BaseModel, Field

# ── Status / read schemas ────────────────────────────────────────────────

class MfaStatusOut(BaseModel):
    """GET /mfa/status — current user's MFA configuration."""
    enabled: bool
    method: Literal["none", "telegram", "totp", "both"]
    telegram_linked: bool
    telegram_username: Optional[str] = None
    telegram_linked_at: Optional[datetime] = None
    recovery_codes_remaining: int = 0
    recovery_codes_total: int = 0


# ── Enable / disable ─────────────────────────────────────────────────────

class MfaEnableIn(BaseModel):
    """POST /mfa/enable — request to enable 2FA."""
    method: Literal["telegram", "totp", "both"] = "telegram"


class MfaEnableOut(BaseModel):
    enabled: bool
    method: Literal["telegram", "totp", "both"]
    recovery_codes: list[str] = Field(
        default_factory=list,
        description="Plaintext recovery codes — shown ONCE, then only hashes are stored. 10 codes total.",
    )


class MfaDisableIn(BaseModel):
    """POST /mfa/disable — must confirm with current MFA code or recovery code."""
    confirm_code: str = Field(..., min_length=6, max_length=32)


# ── Telegram link flow ───────────────────────────────────────────────────

class MfaLinkTelegramOut(BaseModel):
    """POST /mfa/link-telegram — returns deep-link for user to open bot."""
    bot_username: str            # 'UzAssets_bot' (no @)
    deep_link: str               # 'https://t.me/UzAssets_bot?start=ABC123XYZ456'
    token: str                   # plaintext token (only this once)
    expires_at: datetime


class MfaUnlinkTelegramIn(BaseModel):
    """DELETE /mfa/unlink-telegram — must confirm to prevent accidental lockout."""
    confirm: bool = False


# ── Recovery codes ───────────────────────────────────────────────────────

class MfaRecoveryCodesOut(BaseModel):
    """POST /mfa/recovery-codes/regenerate — returns 10 fresh codes."""
    codes: list[str]


# ── Notification prefs (1:1 with user_telegram_pref table) ───────────────

class TelegramPrefIn(BaseModel):
    """PATCH /mfa/notification-prefs — partial update."""
    enabled: Optional[bool] = None
    type_assignments: Optional[bool] = None
    type_mentions: Optional[bool] = None
    type_deadlines: Optional[bool] = None
    type_moderation: Optional[bool] = None
    type_broadcasts: Optional[bool] = None
    type_system: Optional[bool] = None
    quiet_hours_enabled: Optional[bool] = None
    quiet_hours_start: Optional[time] = None
    quiet_hours_end: Optional[time] = None
    timezone: Optional[str] = Field(None, max_length=64)


class TelegramPrefOut(BaseModel):
    """GET /mfa/notification-prefs."""
    enabled: bool
    type_assignments: bool
    type_mentions: bool
    type_deadlines: bool
    type_moderation: bool
    type_broadcasts: bool
    type_system: bool
    quiet_hours_enabled: bool
    quiet_hours_start: time
    quiet_hours_end: time
    timezone: str


# ── Test message ─────────────────────────────────────────────────────────

class MfaTestNotificationOut(BaseModel):
    """POST /mfa/test-notification — enqueues a test message to user's TG."""
    enqueued: bool
    outbox_id: Optional[str] = None
    detail: Optional[str] = None
