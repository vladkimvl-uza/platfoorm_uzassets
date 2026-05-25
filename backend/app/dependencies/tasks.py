"""Tasks service dependencies."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.tasks.editor_service import TasksEditorService
from app.services.tasks.query_service import TasksQueryService


def get_tasks_query_service(uow: UowDep) -> TasksQueryService:
    return TasksQueryService(uow=uow)


def get_tasks_editor_service(uow: UowDep) -> TasksEditorService:
    return TasksEditorService(uow=uow)


TasksQueryServiceDep = Annotated[TasksQueryService, Depends(get_tasks_query_service)]
TasksEditorServiceDep = Annotated[TasksEditorService, Depends(get_tasks_editor_service)]
