"""FastAPI DI factory for ForgotPasswordService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.forgot_password.service import ForgotPasswordService


def get_forgot_password_service() -> ForgotPasswordService:
    return ForgotPasswordService()


ForgotPasswordServiceDep = Annotated[
    ForgotPasswordService, Depends(get_forgot_password_service)
]
