"""FastAPI DI factory for FinancialsIndicatorsService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.financials_indicators.service import FinancialsIndicatorsService


def get_financials_indicators_service() -> FinancialsIndicatorsService:
    return FinancialsIndicatorsService()


FinancialsIndicatorsServiceDep = Annotated[
    FinancialsIndicatorsService, Depends(get_financials_indicators_service)
]
