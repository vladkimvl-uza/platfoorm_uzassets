from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

HEALTH_VALUES = {"on_track", "at_risk", "delayed", "blocked"}
ENTITY_TYPES = {"project", "task"}


class StatusUpdateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    entity_type: str
    entity_id: str
    body: str
    health: Optional[str] = None
    author_id: Optional[UUID] = None
    author_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class StatusUpdateCreate(BaseModel):
    entity_type: str
    entity_id: str
    body: str = Field(..., min_length=1, max_length=8000)
    health: Optional[str] = None


class StatusUpdateUpdate(BaseModel):
    body: Optional[str] = Field(None, min_length=1, max_length=8000)
    health: Optional[str] = None
