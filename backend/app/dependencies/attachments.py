"""FastAPI DI factory for AttachmentsService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.attachments.service import AttachmentsService


def get_attachments_service(uow: UowDep) -> AttachmentsService:
    return AttachmentsService(uow=uow)


AttachmentsServiceDep = Annotated[
    AttachmentsService, Depends(get_attachments_service)
]
