"""FastAPI DI factory for MfaUserService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.mfa_user.service import MfaUserService


def get_mfa_user_service() -> MfaUserService:
    return MfaUserService()


MfaUserServiceDep = Annotated[MfaUserService, Depends(get_mfa_user_service)]
