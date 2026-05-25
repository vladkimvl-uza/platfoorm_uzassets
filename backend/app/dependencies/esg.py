"""FastAPI DI factories for ESG services."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.esg.editor_service import ESGCompanyService, ESGEditorService
from app.services.esg.overview_service import ESGOverviewService


def get_esg_overview_service(uow: UowDep) -> ESGOverviewService:
    return ESGOverviewService(uow=uow)


def get_esg_company_service(uow: UowDep) -> ESGCompanyService:
    return ESGCompanyService(uow=uow)


def get_esg_editor_service(uow: UowDep) -> ESGEditorService:
    return ESGEditorService(uow=uow)


ESGOverviewServiceDep = Annotated[ESGOverviewService, Depends(get_esg_overview_service)]
ESGCompanyServiceDep = Annotated[ESGCompanyService, Depends(get_esg_company_service)]
ESGEditorServiceDep = Annotated[ESGEditorService, Depends(get_esg_editor_service)]
