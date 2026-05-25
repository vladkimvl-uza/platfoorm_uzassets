"""FastAPI DI factory for TlsAdminService (no DB)."""
from typing import Annotated

from fastapi import Depends

from app.services.tls_admin.service import TlsAdminService


def get_tls_admin_service() -> TlsAdminService:
    return TlsAdminService()


TlsAdminServiceDep = Annotated[TlsAdminService, Depends(get_tls_admin_service)]
