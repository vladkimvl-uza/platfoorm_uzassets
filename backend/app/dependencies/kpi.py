"""KPI service dependencies."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.kpi.editor_service import KpiEditorService
from app.services.kpi.forecast_service import KpiForecastService
from app.services.kpi.query_service import KpiQueryService


def get_kpi_query_service(uow: UowDep) -> KpiQueryService:
    return KpiQueryService(uow=uow)


def get_kpi_editor_service(uow: UowDep) -> KpiEditorService:
    return KpiEditorService(uow=uow)


def get_kpi_forecast_service(uow: UowDep) -> KpiForecastService:
    return KpiForecastService(uow=uow)


KpiQueryServiceDep = Annotated[KpiQueryService, Depends(get_kpi_query_service)]
KpiEditorServiceDep = Annotated[KpiEditorService, Depends(get_kpi_editor_service)]
KpiForecastServiceDep = Annotated[KpiForecastService, Depends(get_kpi_forecast_service)]
