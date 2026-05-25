"""FastAPI DI factory for UserSearchService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.user_search.service import UserSearchService


def get_user_search_service() -> UserSearchService:
    return UserSearchService()


UserSearchServiceDep = Annotated[
    UserSearchService, Depends(get_user_search_service)
]
