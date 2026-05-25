"""FastAPI DI factories for Companies + Sectors services."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.companies.service import CompaniesService, SectorsService


def get_companies_service(uow: UowDep) -> CompaniesService:
    return CompaniesService(uow=uow)


def get_sectors_service(uow: UowDep) -> SectorsService:
    return SectorsService(uow=uow)


CompaniesServiceDep = Annotated[CompaniesService, Depends(get_companies_service)]
SectorsServiceDep = Annotated[SectorsService, Depends(get_sectors_service)]
