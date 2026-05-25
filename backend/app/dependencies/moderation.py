"""FastAPI DI factories for moderation_admin services."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.moderation_admin.query_service import ModerationQueryService
from app.services.moderation_admin.rules_service import ModerationRulesService


def get_moderation_query_service(uow: UowDep) -> ModerationQueryService:
    return ModerationQueryService(uow=uow)


def get_moderation_rules_service(uow: UowDep) -> ModerationRulesService:
    return ModerationRulesService(uow=uow)


ModerationQueryServiceDep = Annotated[ModerationQueryService, Depends(get_moderation_query_service)]
ModerationRulesServiceDep = Annotated[ModerationRulesService, Depends(get_moderation_rules_service)]
