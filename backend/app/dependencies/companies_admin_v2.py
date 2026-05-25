"""FastAPI DI factory for CompaniesAdminV2Service."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.companies_admin_v2.service import CompaniesAdminV2Service


def get_companies_admin_v2_service(uow: UowDep) -> CompaniesAdminV2Service:
    return CompaniesAdminV2Service(uow=uow)


CompaniesAdminV2ServiceDep = Annotated[
    CompaniesAdminV2Service, Depends(get_companies_admin_v2_service)
]
