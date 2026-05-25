"""FastAPI DI factory for FinModelService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.finmodel.service import FinModelService


def get_finmodel_service(uow: UowDep) -> FinModelService:
    return FinModelService(uow=uow)


FinModelServiceDep = Annotated[FinModelService, Depends(get_finmodel_service)]
