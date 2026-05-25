"""FastAPI DI factory for FinancialsNsbuService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.financials_nsbu.service import FinancialsNsbuService


def get_financials_nsbu_service() -> FinancialsNsbuService:
    return FinancialsNsbuService()


FinancialsNsbuServiceDep = Annotated[
    FinancialsNsbuService, Depends(get_financials_nsbu_service)
]
