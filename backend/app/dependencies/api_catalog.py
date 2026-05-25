"""FastAPI DI factory for ApiCatalogService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.api_catalog.service import ApiCatalogService


def get_api_catalog_service(uow: UowDep) -> ApiCatalogService:
    return ApiCatalogService(uow=uow)


ApiCatalogServiceDep = Annotated[ApiCatalogService, Depends(get_api_catalog_service)]
