"""FastAPI DI factory for ProductionService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.production.service import ProductionService


def get_production_service(uow: UowDep) -> ProductionService:
    return ProductionService(uow=uow)


ProductionServiceDep = Annotated[ProductionService, Depends(get_production_service)]
