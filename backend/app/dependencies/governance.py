"""FastAPI DI factory for GovernanceService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.governance.service import GovernanceService


def get_governance_service(uow: UowDep) -> GovernanceService:
    return GovernanceService(uow=uow)


GovernanceServiceDep = Annotated[GovernanceService, Depends(get_governance_service)]
