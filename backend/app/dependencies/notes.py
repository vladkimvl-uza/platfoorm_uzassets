"""FastAPI DI factory for NotesService."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.notes.service import NotesService


def get_notes_service(uow: UowDep) -> NotesService:
    return NotesService(uow=uow)


NotesServiceDep = Annotated[NotesService, Depends(get_notes_service)]
