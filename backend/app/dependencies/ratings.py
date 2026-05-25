"""FastAPI DI factory for RatingsService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.ratings.service import RatingsService


def get_ratings_service(uow: UowDep) -> RatingsService:
    return RatingsService(uow=uow)


RatingsServiceDep = Annotated[RatingsService, Depends(get_ratings_service)]
