"""FastAPI DI factory for NotificationsQueryService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.notifications_admin.service import NotificationsQueryService


def get_notifications_query_service(uow: UowDep) -> NotificationsQueryService:
    return NotificationsQueryService(uow=uow)


NotificationsQueryServiceDep = Annotated[
    NotificationsQueryService, Depends(get_notifications_query_service)
]
