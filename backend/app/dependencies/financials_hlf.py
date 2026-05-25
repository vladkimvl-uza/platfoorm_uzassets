"""FastAPI DI factory for FinancialsHlfService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.financials_hlf.service import FinancialsHlfService


def get_financials_hlf_service() -> FinancialsHlfService:
    return FinancialsHlfService()


FinancialsHlfServiceDep = Annotated[
    FinancialsHlfService, Depends(get_financials_hlf_service)
]
