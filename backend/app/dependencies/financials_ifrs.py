"""FastAPI DI factory for FinancialsIfrsService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.financials_ifrs.service import FinancialsIfrsService


def get_financials_ifrs_service() -> FinancialsIfrsService:
    return FinancialsIfrsService()


FinancialsIfrsServiceDep = Annotated[
    FinancialsIfrsService, Depends(get_financials_ifrs_service)
]
