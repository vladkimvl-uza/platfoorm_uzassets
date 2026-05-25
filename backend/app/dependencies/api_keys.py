"""FastAPI DI factory for ApiKeysAdminService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.api_keys_admin.service import ApiKeysAdminService


def get_api_keys_service(uow: UowDep) -> ApiKeysAdminService:
    return ApiKeysAdminService(uow=uow)


ApiKeysServiceDep = Annotated[ApiKeysAdminService, Depends(get_api_keys_service)]
