"""FastAPI DI factory for FinancialsDetailedService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.financials_detailed.service import FinancialsDetailedService


def get_financials_detailed_service() -> FinancialsDetailedService:
    return FinancialsDetailedService()


FinancialsDetailedServiceDep = Annotated[
    FinancialsDetailedService, Depends(get_financials_detailed_service)
]
