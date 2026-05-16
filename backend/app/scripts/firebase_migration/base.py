"""Firebase migration framework.

Architecture:
  - FirebaseClient   — thin wrapper around firebase_admin.db
  - Migrator         — base class; subclasses implement plan() + apply()
  - MigrationContext — shared state (db session, dry_run flag, stats)
  - MigrationReport  — running totals + skip reasons + warnings

All migrators are idempotent — they upsert by deterministic keys (company.code,
financial.report (company_id, year, standard, report_type, quarter), etc.).
Re-running the migration produces the same result.
"""
from __future__ import annotations

import logging
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

import firebase_admin
from firebase_admin import credentials, db
from sqlalchemy.ext.asyncio import AsyncSession


log = logging.getLogger(__name__)

# =====================================================================
# Configuration
# =====================================================================

SERVICE_ACCOUNT = Path("/app/firebase-service-account.json")
DATABASE_URL    = "https://uza-projectsflow-default-rtdb.europe-west1.firebasedatabase.app/"


# =====================================================================
# Firebase client
# =====================================================================

class FirebaseClient:
    """Read-only wrapper around firebase_admin.db.

    Reuses a single app instance so re-init doesn't fail."""

    _initialized = False

    def __init__(self) -> None:
        if not self._initialized:
            if not SERVICE_ACCOUNT.is_file():
                raise SystemExit(
                    f"❌ Service-account ключ не найден: {SERVICE_ACCOUNT}\n"
                    "   Скачай его в Firebase Console → Project Settings → Service Accounts.\n"
                    "   Положи в backend/firebase-service-account.json."
                )
            cred = credentials.Certificate(str(SERVICE_ACCOUNT))
            firebase_admin.initialize_app(cred, {"databaseURL": DATABASE_URL})
            FirebaseClient._initialized = True

    def get(self, path: str) -> Any:
        return db.reference(path).get()

    def shallow_keys(self, path: str) -> list[str]:
        result = db.reference(path).get(shallow=True)
        if not result or not isinstance(result, dict):
            return []
        return sorted(result.keys())


# =====================================================================
# Report
# =====================================================================

@dataclass
class MigrationReport:
    """Running totals across all migrators."""
    created:  dict[str, int] = field(default_factory=lambda: defaultdict(int))
    updated:  dict[str, int] = field(default_factory=lambda: defaultdict(int))
    skipped:  dict[str, int] = field(default_factory=lambda: defaultdict(int))
    skip_reasons: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    warnings: list[str] = field(default_factory=list)
    errors:   list[str] = field(default_factory=list)

    def add_create(self, kind: str) -> None: self.created[kind] += 1
    def add_update(self, kind: str) -> None: self.updated[kind] += 1
    def add_skip(self, kind: str, reason: str) -> None:
        self.skipped[kind] += 1
        if len(self.skip_reasons[kind]) < 10:
            self.skip_reasons[kind].append(reason)
    def add_warning(self, msg: str) -> None: self.warnings.append(msg)
    def add_error(self, msg: str) -> None: self.errors.append(msg)

    def render(self) -> str:
        lines = ["", "=" * 60, "ОТЧЁТ О МИГРАЦИИ", "=" * 60]
        kinds = sorted(set(self.created) | set(self.updated) | set(self.skipped))
        if kinds:
            lines.append(f"\n{'РАЗДЕЛ':<28} {'СОЗДАНО':>10} {'ОБНОВЛЕНО':>10} {'ПРОПУЩЕНО':>10}")
            lines.append("-" * 60)
            for k in kinds:
                lines.append(f"{k:<28} {self.created[k]:>10} {self.updated[k]:>10} {self.skipped[k]:>10}")
        if self.skip_reasons:
            lines.append("\nПРИЧИНЫ ПРОПУСКОВ (первые 10 на раздел):")
            for k, reasons in self.skip_reasons.items():
                lines.append(f"  {k}:")
                for r in reasons:
                    lines.append(f"    - {r}")
        if self.warnings:
            lines.append("\nПРЕДУПРЕЖДЕНИЯ:")
            for w in self.warnings[:30]:
                lines.append(f"  ⚠ {w}")
        if self.errors:
            lines.append("\nОШИБКИ:")
            for e in self.errors[:30]:
                lines.append(f"  ✗ {e}")
        lines.append("")
        return "\n".join(lines)


# =====================================================================
# Context
# =====================================================================

@dataclass
class MigrationContext:
    fb: FirebaseClient
    db: AsyncSession
    dry_run: bool
    report: MigrationReport
    actor_id: Optional[str]      # uuid of the admin running the migration
    actor_email: Optional[str]   # email for audit


# =====================================================================
# Base migrator
# =====================================================================

class Migrator:
    """Subclass and implement `firebase_path` and `apply()`."""

    name: str = "<unnamed>"
    firebase_path: str = ""

    async def fetch(self, ctx: MigrationContext) -> Any:
        """Return the Firebase data; default = full path GET."""
        return ctx.fb.get(self.firebase_path)

    async def apply(self, ctx: MigrationContext) -> None:
        """Override in subclasses."""
        raise NotImplementedError

    async def run(self, ctx: MigrationContext) -> None:
        try:
            await self.apply(ctx)
        except Exception as e:
            log.exception("Migrator %s failed", self.name)
            ctx.report.add_error(f"{self.name}: {type(e).__name__}: {e}")


# =====================================================================
# Helpers used by migrators
# =====================================================================

def normalize_array(v: Any) -> list:
    """Firebase stores lists as objects {'0': x, '1': y, ...}. Normalize back."""
    if v is None:
        return []
    if isinstance(v, list):
        return v
    if isinstance(v, dict):
        keys = list(v.keys())
        if all(str(k).lstrip("-").isdigit() for k in keys):
            return [v[k] for k in sorted(keys, key=lambda x: int(x))]
        # Otherwise return dict values
        return list(v.values())
    return [v]


def safe_str(v: Any, max_len: int = 1024) -> Optional[str]:
    """Coerce to a string and truncate. Returns None for null/empty."""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s[:max_len]


def safe_int(v: Any) -> Optional[int]:
    """Coerce to int or None on failure."""
    if v is None:
        return None
    try:
        return int(float(str(v).replace(",", ".").replace(" ", "")))
    except (ValueError, TypeError):
        return None


def safe_decimal(v: Any):
    """Coerce to Decimal or None on failure."""
    from decimal import Decimal, InvalidOperation
    if v is None:
        return None
    try:
        return Decimal(str(v).replace(",", ".").replace(" ", "").replace(" ", ""))
    except (InvalidOperation, ValueError, TypeError):
        return None
