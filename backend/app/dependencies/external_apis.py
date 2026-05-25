"""FastAPI DI factory for ExternalApisService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.external_apis.service import ExternalApisService


def get_external_apis_service(uow: UowDep) -> ExternalApisService:
    return ExternalApisService(uow=uow)


ExternalApisServiceDep = Annotated[ExternalApisService, Depends(get_external_apis_service)]
