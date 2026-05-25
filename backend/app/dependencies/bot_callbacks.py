"""FastAPI DI factory for BotCallbacksService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.bot_callbacks.service import BotCallbacksService


def get_bot_callbacks_service(uow: UowDep) -> BotCallbacksService:
    return BotCallbacksService(uow=uow)


BotCallbacksServiceDep = Annotated[
    BotCallbacksService, Depends(get_bot_callbacks_service)
]
