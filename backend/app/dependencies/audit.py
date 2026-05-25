"""FastAPI DI factory for AuditAdminService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.audit_admin.service import AuditAdminService


def get_audit_admin_service() -> AuditAdminService:
    return AuditAdminService()


AuditAdminServiceDep = Annotated[
    AuditAdminService, Depends(get_audit_admin_service)
]
