"""FastAPI DI factory for FinancialsReportsService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.financials_reports.service import FinancialsReportsService


def get_financials_reports_service() -> FinancialsReportsService:
    return FinancialsReportsService()


FinancialsReportsServiceDep = Annotated[
    FinancialsReportsService, Depends(get_financials_reports_service)
]
