"""FastAPI DI factory for RbacV3Service (stateless)."""
from typing import Annotated

from fastapi import Depends

from app.services.rbac_v3.service import RbacV3Service


def get_rbac_v3_service() -> RbacV3Service:
    return RbacV3Service()


RbacV3ServiceDep = Annotated[RbacV3Service, Depends(get_rbac_v3_service)]
