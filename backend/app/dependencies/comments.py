"""FastAPI DI factory for CommentsService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.comments.service import CommentsService


def get_comments_service(uow: UowDep) -> CommentsService:
    return CommentsService(uow=uow)


CommentsServiceDep = Annotated[CommentsService, Depends(get_comments_service)]
