"""FastAPI DI factory for CompanyLibraryService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.company_library.service import CompanyLibraryService


def get_company_library_service(uow: UowDep) -> CompanyLibraryService:
    return CompanyLibraryService(uow=uow)


CompanyLibraryServiceDep = Annotated[
    CompanyLibraryService, Depends(get_company_library_service)
]
