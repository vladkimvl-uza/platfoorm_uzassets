"""FastAPI DI factory for ElasticityService (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.elasticity.service import ElasticityService


def get_elasticity_service() -> ElasticityService:
    return ElasticityService()


ElasticityServiceDep = Annotated[
    ElasticityService, Depends(get_elasticity_service)
]
