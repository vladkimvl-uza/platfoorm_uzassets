"""FastAPI DI factory for DashboardService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.dashboard.service import DashboardService


def get_dashboard_service(uow: UowDep) -> DashboardService:
    return DashboardService(uow=uow)


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
