"""Procurement service dependencies."""
from typing import Annotated

from fastapi import Depends

from app.dependencies.uow import UowDep
from app.services.procurement.aggregate_service import ProcurementAggregateService
from app.services.procurement.editor_service import ProcurementEditorService
from app.services.procurement.import_service import ProcurementImportService


def get_pa_aggregate_service(uow: UowDep) -> ProcurementAggregateService:
    return ProcurementAggregateService(uow=uow)


def get_pa_editor_service(uow: UowDep) -> ProcurementEditorService:
    return ProcurementEditorService(uow=uow)


def get_pa_import_service(uow: UowDep) -> ProcurementImportService:
    return ProcurementImportService(uow=uow)


PaAggregateServiceDep = Annotated[ProcurementAggregateService, Depends(get_pa_aggregate_service)]
PaEditorServiceDep    = Annotated[ProcurementEditorService,    Depends(get_pa_editor_service)]
PaImportServiceDep    = Annotated[ProcurementImportService,    Depends(get_pa_import_service)]
