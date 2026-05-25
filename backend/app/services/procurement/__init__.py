"""Procurement analysis services — 10-layer template pilot (2026-05-25).

- `aggregate_service.py` — read-only `get_aggregate` (KPIs + rating + products).
- `editor_service.py` — per-closure update + bulk clear.
- `import_service.py` — xlsx bulk import (xarid format, 22 sheets).
- `_aggregators.py` — pure transform helpers (color/product/rating/kpis).
"""
from app.services.procurement.aggregate_service import ProcurementAggregateService
from app.services.procurement.editor_service import ProcurementEditorService
from app.services.procurement.import_service import ProcurementImportService

__all__ = [
    "ProcurementAggregateService",
    "ProcurementEditorService",
    "ProcurementImportService",
]
