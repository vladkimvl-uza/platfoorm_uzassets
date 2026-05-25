"""FastAPI DI factories for Projects services."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.projects.editor_service import ProjectsEditorService
from app.services.projects.query_service import ProjectsQueryService


def get_projects_query_service(uow: UowDep) -> ProjectsQueryService:
    return ProjectsQueryService(uow=uow)


def get_projects_editor_service(uow: UowDep) -> ProjectsEditorService:
    return ProjectsEditorService(uow=uow)


ProjectsQueryServiceDep = Annotated[ProjectsQueryService, Depends(get_projects_query_service)]
ProjectsEditorServiceDep = Annotated[ProjectsEditorService, Depends(get_projects_editor_service)]
