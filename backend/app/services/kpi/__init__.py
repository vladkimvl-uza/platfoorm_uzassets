"""KPI service-layer — use-cases для KPI-модуля.

- `query_service.py` — read-only сценарии (lists, summary, attention, comments).
- `editor_service.py` — мутации (replace_year, delete_year, comment upsert, templates).
"""
from app.services.kpi.editor_service import KpiEditorService
from app.services.kpi.query_service import KpiQueryService

__all__ = ["KpiQueryService", "KpiEditorService"]
