"""Procurement editor service — per-closure update + bulk clear (admin)."""
from __future__ import annotations

import statistics
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, status as http_status

from app.schemas.procurement_analysis import ClosureRow  # noqa: F401  (имеется в маршруте)
from app.uow.ports import UnitOfWorkABC


class ProcurementEditorService:
    def __init__(self, uow: UnitOfWorkABC) -> None:
        self.uow = uow

    async def update_closure(
        self,
        closure_id: UUID,
        patch: dict[str, Any],
        *,
        allowed_company_ids: Optional[list[UUID]] = None,
    ) -> dict[str, Any]:
        """Update single closure + recompute median for affected product_codes.

        `patch` keys: unit_price, volume, product_code, product_name,
        supplier_name, is_dirty, dirty_reason (all optional, only non-None applied).
        `allowed_company_ids=None` → unrestricted (admin); иначе ограничение по scope.
        """
        async with self.uow:
            row = await self.uow.procurement.get_closure(closure_id)
            if row is None:
                raise HTTPException(
                    http_status.HTTP_404_NOT_FOUND, "Closure not found",
                )

            if allowed_company_ids is not None and row.company_id not in allowed_company_ids:
                raise HTTPException(
                    http_status.HTTP_403_FORBIDDEN, "No access to this company",
                )

            old_pcode = row.product_code
            changed_price = False

            if patch.get("unit_price") is not None:
                row.unit_price = Decimal(str(patch["unit_price"]))
                changed_price = True
            if patch.get("volume") is not None:
                row.volume = Decimal(str(patch["volume"]))
                if row.unit_price:
                    row.total_amount = Decimal(row.unit_price) * Decimal(str(patch["volume"]))
            if patch.get("product_code") is not None:
                row.product_code = patch["product_code"]
            if patch.get("product_name") is not None:
                row.product_name = patch["product_name"]
            if patch.get("supplier_name") is not None:
                row.supplier_name = patch["supplier_name"]
            if patch.get("is_dirty") is not None:
                row.is_dirty = patch["is_dirty"]
                row.is_clean = not patch["is_dirty"]
            if patch.get("dirty_reason") is not None:
                row.dirty_reason = patch["dirty_reason"]

            # Recompute median for both old + new product_code (если код менялся
            # или цена) — siblings получают свежие market_avg/deviation_pct.
            affected_codes = {c for c in (old_pcode, row.product_code) if c}
            recomputed = 0
            if changed_price or patch.get("product_code") is not None:
                for pcode in affected_codes:
                    sibs = await self.uow.procurement.list_closures_by_product(pcode)
                    prices = [float(s.unit_price) for s in sibs if s.unit_price]
                    if not prices:
                        continue
                    med = float(statistics.median(prices))
                    for s in sibs:
                        if s.unit_price and med > 0:
                            s.market_avg = Decimal(str(med))
                            s.deviation_pct = (s.unit_price - Decimal(str(med))) / Decimal(str(med)) * 100
                            recomputed += 1

            await self.uow.commit()
            await self.uow.procurement.refresh(row)

            return {
                "ok": True,
                "id": str(row.id),
                "unit_price": float(row.unit_price) if row.unit_price else None,
                "market_avg": float(row.market_avg) if row.market_avg else None,
                "deviation_pct": float(row.deviation_pct) if row.deviation_pct else None,
                "siblings_recomputed": recomputed,
            }

    async def clear_closures(
        self,
        *,
        year: Optional[int] = None,
        source: Optional[str] = None,
    ) -> dict[str, Any]:
        """Bulk delete closures filtered by year/source. Requires admin scope
        (route проверяет has_unrestricted_view)."""
        if year is None and not source:
            raise HTTPException(
                http_status.HTTP_400_BAD_REQUEST,
                "Provide ?year= and/or ?source=",
            )
        async with self.uow:
            cleared = await self.uow.procurement.clear_filtered(year=year, source=source)
        return {"ok": True, "cleared": cleared, "year": year, "source": source}
