"""FastAPI DI factory for BpService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.bp.forecast_service import BpForecastService
from app.services.bp.service import BpService


def get_bp_service(uow: UowDep) -> BpService:
    return BpService(uow=uow)


def get_bp_forecast_service(uow: UowDep) -> BpForecastService:
    return BpForecastService(uow=uow)


BpServiceDep = Annotated[BpService, Depends(get_bp_service)]
BpForecastServiceDep = Annotated[BpForecastService, Depends(get_bp_forecast_service)]
