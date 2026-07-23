"""Value Opportunities service dependency."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.value.service import ValueService


def get_value_service(uow: UowDep) -> ValueService:
    return ValueService(uow=uow)


ValueServiceDep = Annotated[ValueService, Depends(get_value_service)]
