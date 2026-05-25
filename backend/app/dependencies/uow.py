"""UoW dependency. Каждый запрос получает свежий UnitOfWork, который
лениво открывает session при первом `async with`."""
from typing import Annotated

from fastapi import Depends

from app.database import AsyncSessionLocal
from app.uow.impl import UnitOfWork


def get_uow() -> UnitOfWork:
    return UnitOfWork(session_factory=AsyncSessionLocal)


UowDep = Annotated[UnitOfWork, Depends(get_uow)]
