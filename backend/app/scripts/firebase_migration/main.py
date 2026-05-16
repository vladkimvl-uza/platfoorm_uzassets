"""Firebase → Postgres migration CLI.

Usage:
    # Step 1: dry run — shows what WOULD happen, no DB writes
    docker compose exec -e PYTHONPATH=/app backend python -m app.scripts.firebase_migration.main --dry-run

    # Step 2: real migration
    docker compose exec -e PYTHONPATH=/app backend python -m app.scripts.firebase_migration.main

    # Optional: only run specific migrators
    docker compose exec -e PYTHONPATH=/app backend python -m app.scripts.firebase_migration.main --only companies,financials --dry-run

The script is idempotent — re-running it produces the same result. Existing
records are updated by deterministic keys (companies.code, financial_reports
unique constraint, etc.).

Every migration session also writes one entry per migrator to audit_log via
the HMAC chain (so the operation is permanently recorded as tamper-evident).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit_chain import append_audit_entry
from app.database import AsyncSessionLocal
from app.models.user import User

from .base import (
    FirebaseClient, MigrationContext, MigrationReport,
)
from .migrators import ALL_MIGRATORS


log = logging.getLogger(__name__)


async def _resolve_actor(db: AsyncSession) -> tuple[Optional[str], Optional[str]]:
    """Find the platform owner to attribute the migration to."""
    result = await db.execute(
        select(User).where(User.email == settings.PLATFORM_OWNER_EMAIL.lower())
    )
    user = result.scalar_one_or_none()
    if user:
        return str(user.id), user.email
    # Fallback: any owner
    result = await db.execute(select(User).where(User.is_owner.is_(True)).limit(1))
    user = result.scalar_one_or_none()
    if user:
        return str(user.id), user.email
    return None, None


async def run_migration(dry_run: bool, only: Optional[set[str]]) -> int:
    print("=" * 60)
    print(f"Firebase → Postgres миграция  ({'DRY-RUN' if dry_run else 'РЕАЛЬНЫЙ ЗАПУСК'})")
    print("=" * 60)

    fb = FirebaseClient()
    print(f"✓ Подключился к Firebase")

    report = MigrationReport()

    async with AsyncSessionLocal() as db:
        actor_id, actor_email = await _resolve_actor(db)
        if actor_id:
            print(f"✓ Действую как: {actor_email}  (id={actor_id})")
        else:
            print(f"⚠ Не найден владелец платформы — миграция будет помечена как анонимная")
        print()

        ctx = MigrationContext(
            fb=fb, db=db,
            dry_run=dry_run,
            report=report,
            actor_id=actor_id,
            actor_email=actor_email,
        )

        # Audit: start of migration
        if not dry_run:
            await append_audit_entry(
                db,
                actor_id=actor_id,
                actor_email=actor_email,
                action="migration.firebase.start",
                entity_type="migration",
                notes="Firebase → Postgres bulk migration started",
            )

        for MigratorClass in ALL_MIGRATORS:
            mig = MigratorClass()
            if only and mig.name not in only:
                print(f"⊘ Пропускаю {mig.name} (не в списке --only)")
                continue
            print(f"▶ Запускаю мигратор: {mig.name}  ({mig.firebase_path})")
            await mig.run(ctx)

            if not dry_run:
                # Commit after each migrator so partial successes are durable
                await db.commit()
                # Audit per migrator
                await append_audit_entry(
                    db,
                    actor_id=actor_id,
                    actor_email=actor_email,
                    action=f"migration.firebase.{mig.name}",
                    entity_type="migration",
                    notes=(
                        f"created={report.created.get(mig.name, 0)}, "
                        f"updated={report.updated.get(mig.name, 0)}, "
                        f"skipped={report.skipped.get(mig.name, 0)}"
                    ),
                )
                await db.commit()

        # Audit: end
        if not dry_run:
            await append_audit_entry(
                db,
                actor_id=actor_id,
                actor_email=actor_email,
                action="migration.firebase.end",
                entity_type="migration",
                notes=(
                    f"created_total={sum(report.created.values())}, "
                    f"updated_total={sum(report.updated.values())}, "
                    f"skipped_total={sum(report.skipped.values())}, "
                    f"errors={len(report.errors)}"
                ),
            )
            await db.commit()

    print(report.render())

    if dry_run:
        print("ℹ Это был DRY-RUN — никаких изменений в БД не сделано.")
        print("  Если результат тебя устраивает — запусти БЕЗ --dry-run для реальной миграции.")
    else:
        print("✅ Миграция завершена. Все события записаны в audit_log с HMAC-цепочкой.")
        print(f"   Проверь HMAC-цепочку: SELECT verify_chain() in psql, или вручную через /system/audit/verify")

    return 1 if report.errors else 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="firebase_migrate",
        description="Migrate data from Firebase Realtime Database to Postgres.",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Plan only — no DB writes. Strongly recommended before real run.")
    p.add_argument("--only", default=None,
                   help="Comma-separated list of migrator names (e.g. companies,financials).")
    p.add_argument("--verbose", "-v", action="count", default=0,
                   help="Show debug output.")
    args = p.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    )

    only = set(args.only.split(",")) if args.only else None
    return asyncio.run(run_migration(dry_run=args.dry_run, only=only))


if __name__ == "__main__":
    sys.exit(main())
