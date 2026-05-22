"""Editor optimistic-lock token helper (Pack 153).

Bulk editors (KPI / BP / financials) save many rows at once. Per-row ETags
don't fit — instead each editor uses a *scope token*: a hash derived from
the max(updated_at) of all rows in that scope (e.g. (company_id, year)).

Flow:
  1. Editor GET endpoint returns rows + `editor_token` in the response.
  2. Frontend stores the token, sends it back on PUT as `expected_token`
     in the payload (or `If-Match` header).
  3. Backend re-computes the current token; if it differs from
     `expected_token`, returns 409 "Conflict — another editor saved while
     you were working. Please reload to see their changes."
  4. If frontend sends no token at all → legacy path, no check.
     New code should always pass it.

Choice: scope token, not per-row, because:
  - Editor UI loads all rows for (company, year) together;
  - A conflict means "someone else touched this slice" — that's enough
    granularity for the user-facing reload prompt;
  - Avoids tracking N row-versions on the frontend.

The token is opaque — clients should treat it as a string blob.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# 64-zero placeholder — used when the scope is empty (no rows yet).
EMPTY_TOKEN = "0" * 16


def token_from_timestamps(timestamps: Iterable[Optional[datetime]]) -> str:
    """Derive a stable 16-hex token from a set of updated_at values.

    Hashes the ISO representation (microsecond precision) of each non-None
    timestamp, sorted to be order-independent. SHA-1 truncated to 16 hex
    chars — collisions are astronomically unlikely at editor scope size,
    and 16 chars keeps the wire payload tiny.
    """
    valid = sorted(t.isoformat() for t in timestamps if t is not None)
    if not valid:
        return EMPTY_TOKEN
    h = hashlib.sha1("|".join(valid).encode("utf-8")).hexdigest()
    return h[:16]


async def compute_kpi_editor_token(db: AsyncSession, *, company_id, year: int) -> str:
    """Token for KPI editor scope = (company, year) over KpiManager + KpiIndicator."""
    from app.models.bp_kpi import KpiManager, KpiIndicator
    mgr_max = (await db.execute(
        select(func.max(KpiManager.updated_at))
        .where(KpiManager.company_id == company_id)
        .where(KpiManager.year == year)
    )).scalar()
    ind_max = (await db.execute(
        select(func.max(KpiIndicator.updated_at))
        .join(KpiManager, KpiManager.id == KpiIndicator.manager_id)
        .where(KpiManager.company_id == company_id)
        .where(KpiManager.year == year)
    )).scalar()
    return token_from_timestamps([mgr_max, ind_max])


async def compute_bp_editor_token(db: AsyncSession, *, company_id, year: int) -> str:
    """Token for BP editor scope = (company, year) over BpRecord."""
    from app.models.bp_kpi import BpRecord
    mx = (await db.execute(
        select(func.max(BpRecord.updated_at))
        .where(BpRecord.company_id == company_id)
        .where(BpRecord.year == year)
    )).scalar()
    return token_from_timestamps([mx])


async def compute_financials_editor_token(
    db: AsyncSession, *, company_id, year: int, standard: str | None = None,
) -> str:
    """Token for financials editor scope = (company, year[, standard]) over FinancialLine.

    Walks Reports → Lines because FinancialLine doesn't carry year directly.
    """
    from app.models.financial import FinancialReport, FinancialLine
    q = (
        select(func.max(FinancialLine.updated_at))
        .join(FinancialReport, FinancialReport.id == FinancialLine.report_id)
        .where(FinancialReport.company_id == company_id)
        .where(FinancialReport.year == year)
    )
    if standard:
        q = q.where(FinancialReport.standard == standard)
    mx = (await db.execute(q)).scalar()
    return token_from_timestamps([mx])


# ─── Conflict signaling ───────────────────────────────────────────────

from app.core.exceptions import ConflictError


class EditorConflict(ConflictError):
    """Raised when the caller's expected_token does not match the current
    scope token — i.e. another editor saved while this one was working.

    Inherits from `ConflictError` (409) so the global error_handler turns
    it into a uniform JSON response automatically — no per-route catch
    needed. The frontend reads `error == "EditorConflict"` and shows a
    "Reload to see latest changes" prompt.
    """

    status_code = 409
    error_code = "EditorConflict"

    def __init__(self, scope: str, expected: str, current: str):
        self.scope = scope
        self.expected = expected
        self.current = current
        super().__init__(
            "Кто-то другой сохранил изменения в этом разделе пока вы редактировали. "
            "Перезагрузите страницу, чтобы увидеть актуальные данные.",
            extra={"scope": scope, "current_token": current},
        )


def check_editor_token(
    *,
    scope_name: str,
    expected_token: Optional[str],
    current_token: str,
) -> None:
    """Raise EditorConflict if expected_token was provided AND differs from current.

    If expected_token is None, the call is allowed (legacy clients). New
    frontends MUST send the token to get the protection.
    """
    if expected_token is None or expected_token == "":
        return
    if expected_token != current_token:
        raise EditorConflict(scope_name, expected_token, current_token)
