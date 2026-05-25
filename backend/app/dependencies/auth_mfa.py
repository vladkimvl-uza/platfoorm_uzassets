"""FastAPI DI factory for AuthMfaService (stateless singleton)."""
from typing import Annotated

from fastapi import Depends

from app.services.auth_mfa.service import AuthMfaService


def get_auth_mfa_service() -> AuthMfaService:
    return AuthMfaService()


AuthMfaServiceDep = Annotated[AuthMfaService, Depends(get_auth_mfa_service)]
