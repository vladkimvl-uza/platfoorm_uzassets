"""DB access for the bot (asyncpg pool, raw SQL вЂ” no ORM).

The backend uses SQLAlchemy 2.0 async; the bot deliberately uses asyncpg
directly for two reasons:
1. Fewer dependencies, faster startup
2. The bot only does a handful of queries вЂ” ORM overhead isn't worth it
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg

import config
import encryption

log = logging.getLogger("uza-bot.db")

_pool: Optional[asyncpg.Pool] = None


async def init_pool() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=config.DATABASE_URL,
        min_size=1,
        max_size=4,
        command_timeout=10,
    )
    log.info("DB pool initialized")


async def close_pool() -> None:
    if _pool:
        await _pool.close()


def _hash_sha256(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# User lookups
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

async def find_user_by_chat_id(chat_id: int) -> Optional[dict]:
    """Reverse-lookup: who owns this Telegram chat_id?

    Since chat_id is stored encrypted (no GIN index possible), we scan all
    users with non-null telegram_chat_id_encrypted and try to decrypt+match.
    For ~5-50 users this is fine; would need a hash column at >1000 users.
    """
    async with _pool.acquire() as c:
        rows = await c.fetch("""
            SELECT id, email, full_name, is_active, telegram_chat_id_encrypted, telegram_username
            FROM users
            WHERE telegram_chat_id_encrypted IS NOT NULL
        """)
    for row in rows:
        try:
            decrypted = encryption.decrypt_int(row["telegram_chat_id_encrypted"])
            if decrypted == chat_id:
                return dict(row)
        except Exception:
            continue
    return None


async def find_user_by_email(email: str) -> Optional[dict]:
    async with _pool.acquire() as c:
        row = await c.fetchrow("SELECT id, email, full_name, is_active FROM users WHERE email = $1", email)
    return dict(row) if row else None


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Link flow (from bot perspective: /start <token>)
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

async def lookup_user_by_link_token(token: str) -> Optional[dict]:
    """Pack 13.3: look up the user a link-token points to, WITHOUT committing
    the link. Bot uses this to render a confirmation card with name/email/role
    before the user taps "Это я".

    Returns {id, email, full_name, role_label} on success, None if invalid/expired.
    """
    token = (token or "").strip()
    if not token:
        return None
    h = _hash_sha256(token)
    now = datetime.now(timezone.utc)
    async with _pool.acquire() as c:
        row = await c.fetchrow("""
            SELECT u.id, u.email, u.full_name, u.is_owner,
                   (SELECT r.name FROM roles r
                    JOIN user_role ur ON ur.role_id = r.id
                    WHERE ur.user_id = u.id
                    ORDER BY r.id LIMIT 1) AS role_name
            FROM users u
            WHERE u.telegram_link_token_hashed = $1
              AND u.telegram_link_token_expires_at > $2
        """, h, now)
        if row is None:
            return None
        if row["is_owner"]:
            role_label = "Администратор платформы"
        else:
            tech = (row["role_name"] or "user").lower()
            role_label = {
                "admin":         "Администратор",
                "financier":     "Финансист",
                "department_head": "Руководитель отдела",
                "consultant":    "Консультант",
                "auditor":       "Аудитор",
                "viewer":        "Наблюдатель",
                "user":          "Пользователь",
            }.get(tech, row["role_name"] or "Пользователь")
        return {
            "id": row["id"],
            "email": row["email"],
            "full_name": row["full_name"] or row["email"],
            "role_label": role_label,
        }


async def confirm_link_telegram(
    token: str, chat_id: int, username: Optional[str],
) -> Optional[dict]:
    """Called after user taps "Это я" — commits the linkage.

    Returns user row dict on success, None on invalid/expired token.
    Same return shape as before for backward compat.
    """
    token = (token or "").strip()
    if not token:
        return None

    h = _hash_sha256(token)
    now = datetime.now(timezone.utc)
    chat_id_enc = encryption.encrypt_int(chat_id)
    username_clean = (username or "")[:64] or None

    async with _pool.acquire() as c:
        async with c.transaction():
            row = await c.fetchrow("""
                SELECT id, email, full_name
                FROM users
                WHERE telegram_link_token_hashed = $1
                  AND telegram_link_token_expires_at > $2
            """, h, now)
            if row is None:
                return None

            await c.execute("""
                UPDATE users
                SET telegram_chat_id_encrypted = $1,
                    telegram_username = $2,
                    telegram_linked_at = $3,
                    telegram_link_token_hashed = NULL,
                    telegram_link_token_expires_at = NULL
                WHERE id = $4
            """, chat_id_enc, username_clean, now, row["id"])

            await c.execute("""
                INSERT INTO telegram_outbox (user_id, type, status, payload, created_at)
                VALUES ($1, 'link_confirmation', 'pending',
                        $2::jsonb, $3)
            """, row["id"],
                 f'{{"email": "{row["email"]}", "username": {("null" if not username_clean else chr(34)+username_clean+chr(34))}}}',
                 now)

            return dict(row)


async def unlink_telegram_by_chat(chat_id: int) -> bool:
    """User typed /unlink вЂ” wipe their TG fields."""
    user = await find_user_by_chat_id(chat_id)
    if not user:
        return False
    async with _pool.acquire() as c:
        await c.execute("""
            UPDATE users
            SET telegram_chat_id_encrypted = NULL,
                telegram_username = NULL,
                telegram_linked_at = NULL,
                telegram_link_token_hashed = NULL,
                telegram_link_token_expires_at = NULL
            WHERE id = $1
        """, user["id"])
    return True


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Outbox
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

async def fetch_pending_outbox(limit: int = 10) -> list[dict]:
    """Pick up pending messages, locking rows so concurrent workers (future)
    can scale horizontally. SKIP LOCKED keeps it lock-free for the current row.
    """
    async with _pool.acquire() as c:
        rows = await c.fetch("""
            SELECT o.id, o.user_id, o.type::text AS type, o.payload, o.inline_buttons,
                   o.attempts, u.telegram_chat_id_encrypted, u.telegram_username, u.email
            FROM telegram_outbox o
            JOIN users u ON u.id = o.user_id
            WHERE o.status = 'pending'
              AND o.attempts < $2
            ORDER BY o.created_at
            LIMIT $1
            FOR UPDATE OF o SKIP LOCKED
        """, limit, config.OUTBOX_MAX_RETRIES)
    return [dict(r) for r in rows]


async def mark_outbox_sent(outbox_id, tg_message_id: Optional[int]) -> None:
    async with _pool.acquire() as c:
        await c.execute("""
            UPDATE telegram_outbox
            SET status = 'sent',
                delivered_at = $2,
                tg_message_id = $3,
                attempts = attempts + 1,
                attempted_at = $2,
                last_error = NULL
            WHERE id = $1
        """, outbox_id, datetime.now(timezone.utc), tg_message_id)


async def mark_outbox_failed(outbox_id, error: str, retry: bool = True) -> None:
    """Increment attempts; if hit retry limit, mark failed (no more attempts)."""
    async with _pool.acquire() as c:
        await c.execute("""
            UPDATE telegram_outbox
            SET status = CASE
                  WHEN attempts + 1 >= $3 THEN 'failed'::telegram_outbox_status_enum
                  ELSE 'pending'::telegram_outbox_status_enum
                END,
                attempts = attempts + 1,
                attempted_at = $2,
                last_error = $4
            WHERE id = $1
        """, outbox_id, datetime.now(timezone.utc), config.OUTBOX_MAX_RETRIES, error[:500])


async def mark_outbox_discarded(outbox_id, reason: str) -> None:
    """No retry вЂ” user has no chat_id, etc."""
    async with _pool.acquire() as c:
        await c.execute("""
            UPDATE telegram_outbox
            SET status = 'discarded',
                attempts = attempts + 1,
                attempted_at = $2,
                last_error = $3
            WHERE id = $1
        """, outbox_id, datetime.now(timezone.utc), reason[:500])


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Notification prefs (for quiet hours check in outbox worker)
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

async def get_user_pref(user_id) -> Optional[dict]:
    async with _pool.acquire() as c:
        row = await c.fetchrow("""
            SELECT enabled, type_assignments, type_mentions, type_deadlines,
                   type_moderation, type_broadcasts, type_system,
                   quiet_hours_enabled, quiet_hours_start, quiet_hours_end, timezone
            FROM user_telegram_pref WHERE user_id = $1
        """, user_id)
    return dict(row) if row else None


# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ
# Commands data helpers
# в”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђв”Ђ

async def get_recent_notifications(user_id, limit: int = 5) -> list[dict]:
    """For /status вЂ” recent unread notifications.

    Schema assumption: notifications table has (id, recipient_user_id, type, title,
    body, is_read, created_at, deep_link). If your schema differs, the bot will
    just say "РЅРµ СѓРґР°Р»РѕСЃСЊ Р·Р°РіСЂСѓР·РёС‚СЊ" and log the error.
    """
    async with _pool.acquire() as c:
        try:
            rows = await c.fetch("""
                SELECT id, type, title, body, is_read, created_at
                FROM notifications
                WHERE recipient_user_id = $1
                  AND is_read = false
                ORDER BY created_at DESC
                LIMIT $2
            """, user_id, limit)
            return [dict(r) for r in rows]
        except Exception as e:
            log.warning("get_recent_notifications failed: %s", e)
            return []


async def has_permission(user_id, permission_code: str) -> bool:
    """For /queue вЂ” check if user has moderation.review permission.

    Tries common RBAC v2 patterns; returns False if schema doesn't match.
    """
    async with _pool.acquire() as c:
        try:
            # Pattern 1: direct grant
            row = await c.fetchrow("""
                SELECT 1
                FROM user_permission_grant
                WHERE user_id = $1
                  AND permission_code = $2
                  AND grant_type = 'grant'
                LIMIT 1
            """, user_id, permission_code)
            if row:
                return True
            # Pattern 2: via role
            row = await c.fetchrow("""
                SELECT 1
                FROM users u
                JOIN user_role ur ON ur.user_id = u.id
                JOIN roles r ON r.id = ur.role_id
                JOIN role_permission rp ON rp.role_id = r.id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE u.id = $1 AND p.code = $2
                LIMIT 1
            """, user_id, permission_code)
            return row is not None
        except Exception as e:
            log.warning("permission check failed: %s", e)
            return False


async def get_moderation_queue(limit: int = 10) -> list[dict]:
    """For /queue command вЂ” pending moderation items."""
    async with _pool.acquire() as c:
        try:
            rows = await c.fetch("""
                SELECT m.id, m.module, m.entity_id, m.created_at,
                       u.email AS submitter_email, u.full_name AS submitter_name
                FROM moderation_submission m
                LEFT JOIN users u ON u.id = m.submitter_user_id
                WHERE m.status IN ('pending', 'under_review')
                ORDER BY m.created_at DESC
                LIMIT $1
            """, limit)
            return [dict(r) for r in rows]
        except Exception as e:
            log.warning("moderation queue fetch failed: %s", e)
            return []


async def get_user_sessions(user_id) -> list[dict]:
    """For /sessions command вЂ” active sessions of this user."""
    async with _pool.acquire() as c:
        try:
            rows = await c.fetch("""
                SELECT created_at, last_seen_at, ip_address, user_agent
                FROM user_sessions
                WHERE user_id = $1
                  AND (revoked_at IS NULL)
                ORDER BY last_seen_at DESC NULLS LAST, created_at DESC
                LIMIT 5
            """, user_id)
            return [dict(r) for r in rows]
        except Exception as e:
            log.warning("sessions fetch failed: %s", e)
            return []
