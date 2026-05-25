"""FastAPI DI factory for CreditScenarioService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.credit_scenario.service import CreditScenarioService


def get_credit_scenario_service(uow: UowDep) -> CreditScenarioService:
    return CreditScenarioService(uow=uow)


CreditScenarioServiceDep = Annotated[
    CreditScenarioService, Depends(get_credit_scenario_service)
]
