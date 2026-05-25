"""FastAPI DI factory for BpService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.bp.service import BpService


def get_bp_service(uow: UowDep) -> BpService:
    return BpService(uow=uow)


BpServiceDep = Annotated[BpService, Depends(get_bp_service)]
