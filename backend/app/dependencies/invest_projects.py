"""FastAPI DI factory for InvestProjectsService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.invest_projects.service import InvestProjectsService


def get_invest_projects_service() -> InvestProjectsService:
    return InvestProjectsService()


InvestProjectsServiceDep = Annotated[
    InvestProjectsService, Depends(get_invest_projects_service)
]
