"""FastAPI DI factory for DbAdminService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.db_admin_console.service import DbAdminService


def get_db_admin_service() -> DbAdminService:
    return DbAdminService()


DbAdminServiceDep = Annotated[DbAdminService, Depends(get_db_admin_service)]
