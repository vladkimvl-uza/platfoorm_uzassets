"""FastAPI DI factory for PartnersService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.partners.service import PartnersService


def get_partners_service(uow: UowDep) -> PartnersService:
    return PartnersService(uow=uow)


PartnersServiceDep = Annotated[PartnersService, Depends(get_partners_service)]
