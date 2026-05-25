"""FastAPI DI factory for ConsultantsService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.consultants.service import ConsultantsService


def get_consultants_service(uow: UowDep) -> ConsultantsService:
    return ConsultantsService(uow=uow)


ConsultantsServiceDep = Annotated[ConsultantsService, Depends(get_consultants_service)]
