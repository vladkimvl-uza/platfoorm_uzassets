"""Bootstrap CLI: create the platform's first user.

Usage (interactive):
    docker compose exec backend python -m app.scripts.create_user

Usage (non-interactive, e.g. from CI):
    docker compose exec backend python -m app.scripts.create_user \\
        --email v.kim@uz-assets.uz \\
        --full-name "Владимир Ким" \\
        --role admin \\
        --password 'Tashkent#Asset2026Strong'

If the email matches the configured `PLATFORM_OWNER_EMAIL`, the user is
created with `is_owner=True` automatically.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from sqlalchemy import select

from app.config import settings
from app.core import password as pw
from app.database import AsyncSessionLocal
from app.models.user import Role, User


def _clean(s: str | None) -> str | None:
    """Defensively strip Windows-codepage artefacts from input.

    PowerShell on Windows often delivers stdin/argv strings with lone-surrogate
    characters (e.g. '\\udcd0') when the terminal codepage isn't UTF-8. asyncpg
    refuses to send such strings to Postgres. We replace any non-encodable
    char with '?' and drop control characters to keep the script usable
    even from a misconfigured terminal.
    """
    if s is None:
        return None
    # Round-trip through utf-8 with 'replace' to drop lone surrogates
    cleaned = s.encode("utf-8", errors="replace").decode("utf-8")
    # Strip control chars except space/tab
    cleaned = "".join(ch for ch in cleaned if ch.isprintable() or ch in (" ", "\t"))
    # Trim
    return cleaned.strip() or None


async def _async_main(
    email: str,
    full_name: str | None,
    username: str | None,
    role_codes: list[str],
    plaintext_password: str,
    must_change: bool,
) -> int:
    # 0. Sanitize all string inputs
    email      = _clean(email)
    full_name  = _clean(full_name)
    username   = _clean(username)
    role_codes = [_clean(r) for r in role_codes if _clean(r)]
    # Password is NOT sanitized — we want to surface encoding issues as a
    # validation error rather than silently change what the user typed.

    if not email:
        return 1

    # Validate password is pure UTF-8 (not a lone surrogate from PowerShell)
    try:
        plaintext_password.encode("utf-8")
    except UnicodeEncodeError:
        return 1

    # 1. Validate password against policy
    try:
        pw.validate_password_policy(plaintext_password)
    except pw.PasswordPolicyError:
        return 1

    async with AsyncSessionLocal() as db:  # type: AsyncSession
        # 2. Check email uniqueness
        existing = await db.execute(select(User).where(User.email == email.lower()))
        if existing.scalar_one_or_none():
            return 2

        if username:
            existing_u = await db.execute(select(User).where(User.username == username))
            if existing_u.scalar_one_or_none():
                return 2

        # 3. Resolve roles
        if not role_codes:
            return 3

        roles_result = await db.execute(
            select(Role).where(Role.code.in_(role_codes))
        )
        roles = list(roles_result.scalars().all())
        found_codes = {r.code for r in roles}
        missing = [c for c in role_codes if c not in found_codes]
        if missing:
            return 4

        # 4. Create user
        is_owner = email.lower() == settings.PLATFORM_OWNER_EMAIL.lower()
        user = User(
            email=email.lower(),
            username=username,
            full_name=full_name,
            password_hash=pw.hash_password(plaintext_password),
            password_history=[],
            password_changed_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
            must_change_password=must_change,
            is_owner=is_owner,
            is_active=True,
            failed_login_attempts=0,
        )
        user.roles = roles
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return 0


def _interactive_prompt() -> tuple[str, str, str, list[str], str, bool]:
    email = input("Email:               ").strip()
    while "@" not in email or "." not in email:
        email = input("Email:               ").strip()

    full_name = input("ФИО (full name):     ").strip() or None
    username  = input("Username (опц.):     ").strip() or None

    roles_str = input("Роли:                ").strip()
    role_codes = [r.strip() for r in roles_str.split(",") if r.strip()]

    while True:
        p1 = getpass.getpass("Пароль (мин. 12, требуется верх/низ/цифра/симв.): ")
        p2 = getpass.getpass("Повтор пароля:       ")
        if p1 != p2:
            continue
        try:
            pw.validate_password_policy(p1)
            break
        except pw.PasswordPolicyError:
            pass

    must_change_input = input("\nПотребовать смену пароля при первом входе? [y/N]: ").strip().lower()
    must_change = must_change_input in ("y", "yes", "д", "да")

    return email, full_name, username, role_codes, p1, must_change


def main() -> int:
    p = argparse.ArgumentParser(
        prog="create_user",
        description="Create a UzAssets Platform user (interactive or via flags).",
    )
    p.add_argument("--email")
    p.add_argument("--full-name")
    p.add_argument("--username")
    p.add_argument("--role", action="append", default=[],
                   help="Role code (repeat for multiple). Example: --role admin")
    p.add_argument("--password", help="Plain password. If omitted, prompt.")
    p.add_argument("--no-must-change", action="store_true",
                   help="Don't force password change on first login.")
    args = p.parse_args()

    if args.email and args.password and args.role:
        # Non-interactive
        email      = args.email
        full_name  = args.full_name
        username   = args.username
        role_codes = args.role
        plaintext  = args.password
        must_change = not args.no_must_change
    else:
        if any([args.email, args.password, args.role]):
            pass
        email, full_name, username, role_codes, plaintext, must_change = _interactive_prompt()

    return asyncio.run(_async_main(email, full_name, username, role_codes, plaintext, must_change))


if __name__ == "__main__":
    sys.exit(main())
