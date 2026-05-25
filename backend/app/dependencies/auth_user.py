"""FastAPI DI factory for AuthUserService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.auth_user.service import AuthUserService


def get_auth_user_service() -> AuthUserService:
    return AuthUserService()


AuthUserServiceDep = Annotated[AuthUserService, Depends(get_auth_user_service)]
