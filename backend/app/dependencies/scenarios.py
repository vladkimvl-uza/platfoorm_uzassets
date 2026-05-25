"""FastAPI DI factory for ScenariosService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.scenarios.service import ScenariosService


def get_scenarios_service(uow: UowDep) -> ScenariosService:
    return ScenariosService(uow=uow)


ScenariosServiceDep = Annotated[ScenariosService, Depends(get_scenarios_service)]
