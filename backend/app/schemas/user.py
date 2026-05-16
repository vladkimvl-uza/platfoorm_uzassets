"""Pydantic schemas for user CRUD (admin endpoints)."""
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserCreate(BaseModel):
    email: EmailStr
    username: Optional[str] = Field(None, min_length=3, max_length=255)
    full_name: Optional[str] = Field(None, max_length=255)
    password: str = Field(..., min_length=8, max_length=256)

    role_codes: List[str] = Field(default_factory=list)
    organization_id: Optional[UUID] = None
    department: Optional[str] = Field(None, max_length=128)
    job_title: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=32)

    must_change_password: bool = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    role_codes: Optional[List[str]] = None
    organization_id: Optional[UUID] = None
    department: Optional[str] = None
    job_title: Optional[str] = None
    phone: Optional[str] = None
    must_change_password: Optional[bool] = None


class UserDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    username: Optional[str]
    full_name: Optional[str]
    is_active: bool
    is_owner: bool
    must_change_password: bool
    failed_login_attempts: int
    locked_until: Optional[datetime]
    last_login_at: Optional[datetime]
    last_login_ip: Optional[str]
    organization_id: Optional[UUID]
    department: Optional[str]
    job_title: Optional[str]
    phone: Optional[str]
    roles: List[str]
    created_at: datetime
    updated_at: datetime
