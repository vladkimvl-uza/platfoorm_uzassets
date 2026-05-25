"""FastAPI DI factory for ExecDashboardService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.exec_dashboard.service import ExecDashboardService


def get_exec_dashboard_service(uow: UowDep) -> ExecDashboardService:
    return ExecDashboardService(uow=uow)


ExecDashboardServiceDep = Annotated[
    ExecDashboardService, Depends(get_exec_dashboard_service)
]
