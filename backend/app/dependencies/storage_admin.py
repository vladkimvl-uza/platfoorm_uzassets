"""FastAPI DI factory for StorageAdminService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.storage_admin.service import StorageAdminService


def get_storage_admin_service() -> StorageAdminService:
    return StorageAdminService()


StorageAdminServiceDep = Annotated[
    StorageAdminService, Depends(get_storage_admin_service)
]
