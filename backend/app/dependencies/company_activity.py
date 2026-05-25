"""FastAPI DI factory for CompanyActivityService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.company_activity.service import CompanyActivityService


def get_company_activity_service() -> CompanyActivityService:
    return CompanyActivityService()


CompanyActivityServiceDep = Annotated[
    CompanyActivityService, Depends(get_company_activity_service)
]
