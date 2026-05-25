"""FastAPI DI factory for AiAdminService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.ai_admin.service import AiAdminService


def get_ai_admin_service(uow: UowDep) -> AiAdminService:
    return AiAdminService(uow=uow)


AiAdminServiceDep = Annotated[AiAdminService, Depends(get_ai_admin_service)]
