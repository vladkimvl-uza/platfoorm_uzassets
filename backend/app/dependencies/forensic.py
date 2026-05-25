"""FastAPI DI factory for ForensicService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.forensic.service import ForensicService


def get_forensic_service(uow: UowDep) -> ForensicService:
    return ForensicService(uow=uow)


ForensicServiceDep = Annotated[ForensicService, Depends(get_forensic_service)]
