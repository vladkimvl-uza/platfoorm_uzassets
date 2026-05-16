"""Refresh task/project statuses and monolith-specific fields from Firebase.

Why this exists:
  TasksMigrator skips items whose legacy_id is already in the DB. So when we
  later expanded STATUS_MAP to include quarterly/monthly/ongoing and started
  capturing quarters/consultant/economic_effect/direction into `extra`, the
  ALREADY-MIGRATED tasks did not pick up those changes — they kept their old
  default `status="new"` and empty `extra`.

  Re-running the full migrator with --apply would do nothing (skip-dup).
  This script does an in-place UPDATE for matched tasks/projects only.

Usage:
  python -m app.scripts.firebase_migration.refresh_statuses
  python -m app.scripts.firebase_migration.refresh_statuses --dry-run

Match key: tasks.legacy_id == firebase item.id.
Updates ONLY the fields that the original migrator now handles differently:
  - status            (via STATUS_MAP)
  - extra.quarters
  - extra.consultant
  - extra.consultant_comment
  - extra.economic_effect
  - extra.direction
Other fields (title, deadline, assignee, ...) are left untouched — assume
the user may have edited them in our UI since the last import.
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.project import Project
from app.models.task import Task
from app.scripts.firebase_migration.base import FirebaseClient, normalize_array, safe_str
from app.scripts.firebase_migration.migrators import TasksMigrator


def _resolve_status(raw: Any) -> str | None:
    """Map a raw Firebase status to our canonical value or None if unrecognised."""
    if not raw:
        return None
    s = str(raw).strip().lower()
    return TasksMigrator.STATUS_MAP.get(s)


def _build_extra_overrides(item: dict, current_extra: dict | None) -> tuple[dict, list[str]]:
    """Return (new_extra, changes_list). Merges monolith-specific fields into existing extra."""
    extra = dict(current_extra or {})
    changes: list[str] = []

    # quarters: only meaningful for quarterly status — but mirror exactly what Firebase has
    qs = item.get("quarters")
    if isinstance(qs, dict):
        if extra.get("quarters") != qs:
            extra["quarters"] = qs
            changes.append("quarters")

    cons = item.get("consultant")
    if cons is not None and cons != extra.get("consultant"):
        extra["consultant"] = cons
        changes.append("consultant")

    cc = safe_str(item.get("consultantComment"), 4000)
    if cc and extra.get("consultant_comment") != cc:
        extra["consultant_comment"] = cc
        changes.append("consultant_comment")

    ee = item.get("economicEffect")
    if isinstance(ee, dict) and extra.get("economic_effect") != ee:
        extra["economic_effect"] = ee
        changes.append("economic_effect")

    direction = safe_str(item.get("direction"), 128)
    if direction and extra.get("direction") != direction:
        extra["direction"] = direction
        changes.append("direction")

    return extra, changes


async def refresh(db: AsyncSession, fb: FirebaseClient, dry_run: bool) -> dict:
    """Walk /pf/tasks; for each item, find DB task/project by legacy_id and update."""
    raw = fb.get("/pf/tasks")
    items = normalize_array(raw)
    if not items:
        print("  ! /pf/tasks is empty in Firebase — nothing to refresh")
        return {}

    # Index DB rows by legacy_id for fast lookup
    t_q = await db.execute(select(Task).where(Task.legacy_id.is_not(None)))
    tasks_by_id: dict[str, Task] = {t.legacy_id: t for t in t_q.scalars().all()}
    p_q = await db.execute(select(Project).where(Project.legacy_id.is_not(None)))
    projs_by_id: dict[str, Project] = {p.legacy_id: p for p in p_q.scalars().all()}

    print(f"  ▶ Firebase items: {len(items)}; DB tasks: {len(tasks_by_id)}; DB projects: {len(projs_by_id)}")

    stats = {
        "matched_task": 0, "matched_project": 0,
        "status_changed": 0, "extra_changed": 0,
        "no_change": 0, "unmatched_in_db": 0, "skipped_bad": 0,
    }
    samples_status: list[str] = []
    samples_extra: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            stats["skipped_bad"] += 1
            continue
        legacy_id = safe_str(item.get("id"), 64)
        if not legacy_id:
            stats["skipped_bad"] += 1
            continue

        target = tasks_by_id.get(legacy_id) or projs_by_id.get(legacy_id)
        if not target:
            stats["unmatched_in_db"] += 1
            continue

        is_task = isinstance(target, Task)
        if is_task: stats["matched_task"] += 1
        else:       stats["matched_project"] += 1

        changed_fields: list[str] = []

        # Status update
        new_status = _resolve_status(item.get("status"))
        if new_status and new_status != target.status:
            old = target.status
            if not dry_run:
                target.status = new_status
            changed_fields.append(f"status: {old}→{new_status}")
            stats["status_changed"] += 1

        # Extra merge
        new_extra, extra_changes = _build_extra_overrides(item, target.extra)
        if extra_changes:
            if not dry_run:
                target.extra = new_extra
            changed_fields.append(f"extra: +{','.join(extra_changes)}")
            stats["extra_changed"] += 1

        if not changed_fields:
            stats["no_change"] += 1
            continue

        # Sample logging — show first few of each kind
        kind = "task" if is_task else "project"
        if "status:" in (changed_fields[0] if changed_fields else "") and len(samples_status) < 8:
            samples_status.append(f"  · {kind} legacy={legacy_id!r}: {' | '.join(changed_fields)}")
        elif len(samples_extra) < 5:
            samples_extra.append(f"  · {kind} legacy={legacy_id!r}: {' | '.join(changed_fields)}")

    if not dry_run:
        await db.commit()

    return {**stats, "samples_status": samples_status, "samples_extra": samples_extra}


async def main():
    parser = argparse.ArgumentParser(description="Refresh task/project statuses and monolith fields from Firebase")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args()

    fb = FirebaseClient()
    print(f"{'DRY-RUN: ' if args.dry_run else ''}Refreshing tasks/projects from Firebase…")

    async with AsyncSessionLocal() as db:
        stats = await refresh(db, fb, dry_run=args.dry_run)

    print()
    print("=" * 60)
    print("Summary:")
    for k, v in stats.items():
        if k.startswith("samples_"):
            continue
        print(f"  {k:>20}: {v}")
    if stats.get("samples_status"):
        print("\nStatus changes (first 8):")
        for s in stats["samples_status"]:
            print(s)
    if stats.get("samples_extra"):
        print("\nExtra-only changes (first 5):")
        for s in stats["samples_extra"]:
            print(s)


if __name__ == "__main__":
    asyncio.run(main())
