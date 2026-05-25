"""FastAPI DI factory for FinancialsPortfolioService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.financials_portfolio.service import FinancialsPortfolioService


def get_financials_portfolio_service() -> FinancialsPortfolioService:
    return FinancialsPortfolioService()


FinancialsPortfolioServiceDep = Annotated[
    FinancialsPortfolioService, Depends(get_financials_portfolio_service)
]
