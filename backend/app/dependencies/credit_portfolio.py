"""FastAPI DI factory for CreditPortfolioService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.credit_portfolio.service import CreditPortfolioService


def get_credit_portfolio_service(uow: UowDep) -> CreditPortfolioService:
    return CreditPortfolioService(uow=uow)


CreditPortfolioServiceDep = Annotated[
    CreditPortfolioService, Depends(get_credit_portfolio_service)
]
