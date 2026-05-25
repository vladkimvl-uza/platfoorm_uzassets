"""FastAPI DI factory for AdminMfaService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.admin_mfa.service import AdminMfaService


def get_admin_mfa_service() -> AdminMfaService:
    return AdminMfaService()


AdminMfaServiceDep = Annotated[AdminMfaService, Depends(get_admin_mfa_service)]
