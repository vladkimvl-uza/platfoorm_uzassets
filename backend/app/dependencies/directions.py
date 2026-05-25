"""FastAPI DI factory for DirectionsService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.directions.service import DirectionsService


def get_directions_service() -> DirectionsService:
    return DirectionsService()


DirectionsServiceDep = Annotated[
    DirectionsService, Depends(get_directions_service)
]
