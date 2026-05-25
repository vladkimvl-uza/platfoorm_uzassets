"""FastAPI DI factory for AdminBroadcastsService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.admin_broadcasts_admin.service import AdminBroadcastsService


def get_admin_broadcasts_service(uow: UowDep) -> AdminBroadcastsService:
    return AdminBroadcastsService(uow=uow)


AdminBroadcastsServiceDep = Annotated[
    AdminBroadcastsService, Depends(get_admin_broadcasts_service)
]
