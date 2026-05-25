"""FastAPI DI factory for SystemConfigService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.system_config.service import SystemConfigService


def get_system_config_service(uow: UowDep) -> SystemConfigService:
    return SystemConfigService(uow=uow)


SystemConfigServiceDep = Annotated[SystemConfigService, Depends(get_system_config_service)]
