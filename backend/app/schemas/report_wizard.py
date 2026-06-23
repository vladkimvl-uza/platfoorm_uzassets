"""Report wizard config schemas — сохранённый «Мастер отчёта»."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ReportWizardSave(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class ReportWizardResponse(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)
    updated_at: Optional[datetime] = None
    updated_by_name: Optional[str] = None
